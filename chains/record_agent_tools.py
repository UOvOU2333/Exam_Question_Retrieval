"""录题 Agent 工具集（9 个工具 schema + 执行函数）。

安全核心约束——禁直写机制：
  本模块禁止 import / 调用任何写库服务层函数：
    - question_services.create_question
    - question_services.update_question
    - note_services.create_question_note
  工具执行仅生成草稿（存 session_state），不直接写数据库。
  写库仅由页面确认提交时调用服务层（草稿→确认→服务层三段式）。

只允许 import 只读服务：
    - question_services.get_question_by_id（校验目标题目存在）
    - question_services.get_question_by_no_and_paper / search_by_content_similarity（匹配候选）
    - note_services.has_rubric_note / get_note_type_by_name（去重检查）

工具清单（9 个）：
  录题工具（6）：
    create_question_draft     创建题目草稿
    update_question_draft     修改题目草稿（保存修改前快照）
    add_note_draft            添加备注草稿（目标为已入库题目ID）
    add_note_to_draft         为草稿添加备注（目标为草稿ID，随草稿一并提交）
    insert_table_fragment     插入表格片段
    insert_question_image     插入题目内图片（校验 file_id 归属）
  PDF 工具（3）：
    pdf_upload_and_split      PDF 上传多题识别拆分
    pdf_match_rubric          PDF 评分细则匹配
    pdf_preview_fragment      预览 PDF 原文片段
"""
from dataclasses import dataclass
from typing import Optional
import re

# 只读服务（禁直写：不 import create_question / update_question / create_question_note）
from services.question_services import (
    get_question_by_id,
    get_question_by_no_and_paper,
    search_by_content_similarity,
)
from services.note_services import has_rubric_note, get_note_type_by_name
from services.log_services import record_log
from tools.exam_type_utils import KNOWLEDGE_MODULES, QUESTION_TYPES
from chains.record_agent_drafts import (
    DraftStore,
    UndoStack,
    SessionImageGallery,
    SessionPdfLibrary,
    PdfFragmentStore,
    MatchDraftStore,
)
from chains.pdf_parser import (
    parse_pdf,
    detect_question_answer_partition,
    split_rubrics_by_question_no,
    split_questions_by_boundary,
    PdfParseError,
)
from chains.rubric_matcher import (
    match_rubric_batch,
    CandidateTooLargeError,
    CONFIDENCE_THRESHOLD,
)

# 草稿/题目 ID 解析（消歧）
_CN_NUM_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(s):
    """中文数字或阿拉伯数字字符串转整数，不支持复合（十一等）。"""
    if s.isdigit():
        return int(s)
    return _CN_NUM_MAP.get(s)


def _parse_target_ref(value):
    """解析目标引用，区分草稿ID 与题目ID。

    返回 (kind, payload)：
      - ("draft", N)     草稿ID（N 为整数序号）
      - ("question", N)  题目ID（N 为整数）
      - ("ambiguous", value) 无法判定
    """
    if value is None:
        return ("ambiguous", value)
    if isinstance(value, int):
        return ("question", value)
    s = str(value).strip()
    m = re.match(r"^draft-(\d+)$", s)
    if m:
        return ("draft", int(m.group(1)))
    m = re.match(r"^草稿([一二三四五六七八九十\d]+)$", s)
    if m:
        n = _cn_to_int(m.group(1))
        if n is not None:
            return ("draft", n)
    m = re.match(r"^第([一二三四五六七八九十\d]+)份草稿$", s)
    if m:
        n = _cn_to_int(m.group(1))
        if n is not None:
            return ("draft", n)
    if s.isdigit():
        return ("question", int(s))
    return ("ambiguous", value)


# 工具名白名单
RECORD_AGENT_TOOL_NAMES = {
    "create_question_draft",
    "update_question_draft",
    "add_note_draft",
    "add_note_to_draft",
    "insert_table_fragment",
    "insert_question_image",
    "pdf_upload_and_split",
    "pdf_match_rubric",
    "pdf_preview_fragment",
}


@dataclass
class RecordToolContext:
    """工具执行上下文，传递用户信息与各存储句柄。"""
    user_id: int
    user_role: str
    session_id: str
    draft_store: DraftStore
    undo_stack: UndoStack
    image_gallery: SessionImageGallery
    pdf_library: SessionPdfLibrary
    fragment_store: PdfFragmentStore
    match_store: MatchDraftStore
    # PDF 本地缓存路径映射：file_id -> local_path
    pdf_local_paths: Optional[dict] = None


# ========== 工具 Schema（OpenAI function calling 格式）==========
RECORD_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_question_draft",
            "description": "创建一道新题目的草稿。草稿不会直接写入数据库，需用户在页面确认后才提交。返回草稿ID与预览。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "题目正文（Markdown）"},
                    "answer": {"type": "string", "description": "答案"},
                    "analysis": {"type": "string", "description": "解析"},
                    "source": {"type": "string", "description": "题目来源"},
                    "analysis_source": {"type": "string", "description": "解析来源"},
                    "year": {"type": "string", "description": "年份，如 2024"},
                    "paper_type": {"type": "string", "description": "卷种，如 浙江首考"},
                    "question_no": {"type": "string", "description": "题号"},
                    "question_type": {"type": "string", "enum": QUESTION_TYPES, "description": "题型，必须从已有类型中选择"},
                    "knowledge_modules": {"type": "string", "description": "知识模块，逗号分隔，只能用以下合法值：%s。不得编造新值。" % "、".join(KNOWLEDGE_MODULES)},
                },
                "required": ["content", "answer", "year", "paper_type", "question_no"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_question_draft",
            "description": "生成修改已有题目的草稿。会保存修改前快照供撤销。草稿不直接写库，需用户确认后提交。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_question_id": {"type": "integer", "description": "要修改的题目ID"},
                    "content": {"type": "string", "description": "新的题目正文"},
                    "answer": {"type": "string", "description": "新的答案"},
                    "analysis": {"type": "string", "description": "新的解析"},
                    "source": {"type": "string", "description": "新的来源"},
                    "analysis_source": {"type": "string", "description": "新的解析来源"},
                    "year": {"type": "string", "description": "年份"},
                    "paper_type": {"type": "string", "description": "卷种"},
                    "question_no": {"type": "string", "description": "题号"},
                    "question_type": {"type": "string", "enum": QUESTION_TYPES, "description": "题型，必须从已有类型中选择"},
                    "knowledge_modules": {"type": "string", "description": "知识模块，逗号分隔，只能用以下合法值：%s" % "、".join(KNOWLEDGE_MODULES)},
                },
                "required": ["target_question_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note_draft",
            "description": "为指定题目生成添加备注的草稿。type_name 必须匹配备注类型表已有类型（如'评分细则'），不可编造。不直接写库，需用户确认后提交。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_question_id": {"type": "integer", "description": "目标题目ID"},
                    "type_name": {"type": "string", "description": "备注类型名称，必须匹配备注类型表已有类型（如'评分细则'、'其他版本解析'等），不可编造新类型"},
                    "content": {"type": "string", "description": "备注内容（Markdown）"},
                },
                "required": ["target_question_id", "type_name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note_to_draft",
            "description": "为指定草稿添加备注。备注随草稿一并提交（不单独成草稿，不直接写库）。target_draft_id 必须是 draft-N 格式。给已入库题目加备注请用 add_note_draft。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_draft_id": {"type": "string", "description": "目标草稿ID（draft-N 格式）"},
                    "type_name": {"type": "string", "description": "备注类型名称，必须匹配备注类型表已有类型，不可编造新类型"},
                    "content": {"type": "string", "description": "备注内容（Markdown）"},
                },
                "required": ["target_draft_id", "type_name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_table_fragment",
            "description": "生成 Markdown 表格片段，可插入到题目的正文/答案/解析中。返回片段ID与Markdown文本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "markdown_text": {"type": "string", "description": "Markdown 表格文本"},
                    "target_field": {"type": "string", "enum": ["content", "answer", "analysis"], "description": "要插入到的字段"},
                },
                "required": ["markdown_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_question_image",
            "description": "在题目中插入图片。file_id 必须是当前会话已上传的图片（会校验归属）。返回 Markdown 图片语法片段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "已上传图片的 file_id"},
                    "target_field": {"type": "string", "enum": ["content", "answer", "analysis"], "description": "要插入到的字段"},
                    "anchor": {"type": "string", "enum": ["append", "replace", "at_line"], "description": "插入方式：追加/替换/指定行"},
                },
                "required": ["file_id", "target_field"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_upload_and_split",
            "description": "确认 PDF 已上传并返回每页图片 file_id 列表。PDF 每页已渲染为图片上传 Files API，你在对话中能直接看到每页图片。请用视觉能力逐页识别题目，对每道题调用 create_question_draft 生成草稿。不依赖本地文本解析。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "已上传 PDF 的 file_id（local-pdf-xxx）"},
                    "mode": {"type": "string", "enum": ["multi_question", "rubric_match"], "description": "模式：多题识别 / 评分细则匹配（互斥）"},
                },
                "required": ["file_id", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_match_rubric",
            "description": "将评分细则匹配到题库已有题目，生成匹配草稿。rubrics 由你用视觉能力从 PDF 答案区图片中识别后传入（题号+细则文本），工具做相似度匹配。已有细则的跳过，低置信度高亮。不直接写库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "已上传大 PDF 的 file_id（local-pdf-xxx）"},
                    "rubrics": {
                        "type": "array",
                        "description": "你从 PDF 答案区图片视觉识别出的评分细则列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_no": {"type": "string", "description": "题号"},
                                "content": {"type": "string", "description": "评分细则全文"},
                            },
                        },
                    },
                    "rubric_type_name": {"type": "string", "description": "评分细则备注类型名称，默认'评分细则'"},
                },
                "required": ["file_id", "rubrics"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_preview_fragment",
            "description": "预览指定 PDF 原文片段的文本/表格，供与识别草稿对照。",
            "parameters": {
                "type": "object",
                "properties": {
                    "fragment_id": {"type": "string", "description": "片段ID（pdf-frag-N）"},
                },
                "required": ["fragment_id"],
            },
        },
    },
]


# ========== 工具执行函数 ==========
def _validate_question_type(val):
    """校验题型，非法值置空。返回 (cleaned, warning)。"""
    if not val or val in QUESTION_TYPES:
        return val, ""
    return None, "题型'%s'不在合法值内，已置空。合法题型：%s" % (val, "、".join(QUESTION_TYPES))


def _validate_knowledge_modules(val):
    """校验知识模块，按逗号拆分过滤非法项。返回 (cleaned_str, warning)。"""
    if not val:
        return val, ""
    parts = [p.strip() for p in val.split(",") if p.strip()]
    valid = [p for p in parts if p in KNOWLEDGE_MODULES]
    invalid = [p for p in parts if p not in KNOWLEDGE_MODULES]
    cleaned = ",".join(valid)
    warn = ""
    if invalid:
        warn = "知识模块非法值已过滤：%s。合法值：%s" % ("、".join(invalid), "、".join(KNOWLEDGE_MODULES))
    return cleaned, warn


# 题目开头题号模式：1. / 1、 / 1． / 第1题 / 题1 等
_LEADING_QNO_PATTERN = re.compile(
    r"^\s*(?:第\s*\d+\s*题\s*[.、．。:]?\s*|题\s*\d+\s*[.、．。:]?\s*|\d+\s*[.、．]\s*)"
)
# 选择题类型集合
_CHOICE_TYPES = {"单项选择题", "不定项选择题", "缺项选择题"}
# 空括号模式（题干只需保留一个）
_EMPTY_PAREN_PATTERN = re.compile(r"[（(]\s*[）)]")
# 选项起始行：行首 A. / B. / C. / D.（允许前导空白）
_OPTION_LINE_START_PATTERN = re.compile(r"(?m)^[ \t　]*(?=[A-D][\.．、])")
# 行内选项标记，避免匹配英文单词中的字母
_OPTION_MARKER_PATTERN = re.compile(r"(?<![A-Za-z])([A-D])[\.．、]")
# 组合型选项内容：仅由序号 ①-⑧ 与空白组成
_SERIAL_OPTION_PATTERN = re.compile(r"^[\s①②③④⑤⑥⑦⑧]+$")


def _split_inline_options(block):
    """把挤在同一行的 A/B/C/D 选项拆成每项一行。

    组合型选项（每项仅由 ①②③④ 组成）保持一行，符合政治题排版习惯。
    """
    normalized = []
    for line in block.split("\n"):
        matches = list(_OPTION_MARKER_PATTERN.finditer(line))
        if [m.group(1) for m in matches] != ["A", "B", "C", "D"]:
            normalized.append(line)
            continue
        parts = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
            parts.append(line[m.start():end].strip())
        contents = [p[2:].strip(" \t　") for p in parts]
        if all(_SERIAL_OPTION_PATTERN.match(c) for c in contents if c):
            normalized.append(" ".join(parts))
        else:
            normalized.extend(parts)
    return "\n".join(normalized)


def _normalize_question_content(content, question_type):
    """题目正文格式规范化。

    1. 去掉开头的题号（题号应放在 question_no 字段，不写进正文）
    2. 选择题：题干保留一个空括号"（ ）"，选项行末尾多余的括号删除
    3. 选择题：普通选项每项独占一行，组合型选项保持一行

    返回规范化后的 content。
    """
    if not content:
        return content
    # 去开头题号
    cleaned = _LEADING_QNO_PATTERN.sub("", content, count=1)
    if question_type not in _CHOICE_TYPES:
        return cleaned

    option_start = _OPTION_LINE_START_PATTERN.search(cleaned)
    if not option_start:
        # 无选项区：在正文末尾补空括号
        if not _EMPTY_PAREN_PATTERN.search(cleaned):
            cleaned = cleaned.rstrip() + "（ ）"
        return cleaned

    stem = cleaned[:option_start.start()].rstrip()
    block = re.sub(
        r"[ \t　]*[（(]\s*[）)][ \t　]*$", "", cleaned[option_start.start():], flags=re.MULTILINE
    )
    # 空括号只属于题干，先删选项行末尾误加的括号再拆分选项
    block = _split_inline_options(block)
    block = "\n".join(line.rstrip() for line in block.split("\n")).strip("\n")
    if not _EMPTY_PAREN_PATTERN.search(stem):
        stem = stem + "（ ）"
    return stem + "\n" + block


def _execute_create_question_draft(args, ctx):
    """创建题目草稿。禁直写：不调用 create_question。"""
    required = ["content", "answer", "year", "paper_type", "question_no"]
    for f in required:
        if not args.get(f):
            return "缺少必填字段: %s" % f
    # 校验题型与知识模块（Agent 无权创建新类型，只能匹配已有合法值）
    qt, qt_warn = _validate_question_type(args.get("question_type", ""))
    km, km_warn = _validate_knowledge_modules(args.get("knowledge_modules", ""))
    warnings = [w for w in (qt_warn, km_warn) if w]
    # 题目正文格式规范化：去开头题号、选择题补全角括号
    normalized_content = _normalize_question_content(args.get("content", ""), qt or "")
    snapshot = {
        "content": normalized_content,
        "answer": args.get("answer", ""),
        "analysis": args.get("analysis", ""),
        "source": args.get("source", ""),
        "analysis_source": args.get("analysis_source", ""),
        "year": args.get("year", ""),
        "paper_type": args.get("paper_type", ""),
        "question_no": args.get("question_no", ""),
        "question_type": qt or "",
        "knowledge_modules": km,
    }
    draft_id = ctx.draft_store.add("create_question", snapshot)
    if draft_id is None:
        return "草稿数已达上限（%d），请先确认或丢弃部分草稿" % 20
    record_log(
        operator="agent:%s" % ctx.user_id,
        case_id=None,
        action="draft_create",
        detail={"draft_id": draft_id, "draft_type": "create_question"},
        session_id=ctx.session_id,
    )
    preview = _preview_snapshot(snapshot)
    warn_prefix = ("；".join(warnings) + "\n\n") if warnings else ""
    return "已创建草稿 %s，待用户确认后提交。\n\n%s%s" % (draft_id, warn_prefix, preview)


def _execute_update_question_draft(args, ctx):
    """修改题目草稿。禁直写：不调用 update_question。只读 get_question_by_id 校验目标存在并取快照。"""
    target_id = args.get("target_question_id")
    if not target_id:
        return "缺少 target_question_id"
    _kind, _payload = _parse_target_ref(target_id)
    if _kind == "draft":
        return ("draft-%d 是草稿ID，不能作为题目ID 使用。"
                "若要给草稿加备注请用 add_note_to_draft 工具。") % _payload
    q = get_question_by_id(target_id)
    if not q:
        return "未找到ID为 %s 的题目" % target_id
    if q["isInRecycleBin"] == 1:
        return "题目ID %s 已在回收站，不可修改" % target_id
    # 保存修改前快照（只读）
    snapshot_before = {
        "content": q["content"], "answer": q["answer"], "analysis": q["analysis"],
        "source": q["source"], "analysis_source": q["analysis_source"],
        "year": q["year"], "paper_type": q["paper_type"], "question_no": q["question_no"],
        "question_type": q["question_type"], "knowledge_modules": q["knowledge_modules"],
    }
    # 合并修改字段
    snapshot_after = dict(snapshot_before)
    for k in snapshot_after:
        if args.get(k) is not None:
            snapshot_after[k] = args[k]
    # 校验题型与知识模块（Agent 无权创建新类型）
    qt, qt_warn = _validate_question_type(snapshot_after.get("question_type", ""))
    km, km_warn = _validate_knowledge_modules(snapshot_after.get("knowledge_modules", ""))
    snapshot_after["question_type"] = qt or ""
    snapshot_after["knowledge_modules"] = km
    # 正文被修改时按同一规范规范化
    if args.get("content") is not None:
        snapshot_after["content"] = _normalize_question_content(
            snapshot_after.get("content", ""), snapshot_after.get("question_type", "")
        )
    warnings = [w for w in (qt_warn, km_warn) if w]
    draft_id = ctx.draft_store.add(
        "update_question",
        snapshot_after,
        target_question_id=target_id,
        snapshot_before=snapshot_before,
    )
    if draft_id is None:
        return "草稿数已达上限，请先确认或丢弃部分草稿"
    record_log(
        operator="agent:%s" % ctx.user_id,
        case_id=target_id,
        action="draft_create",
        detail={"draft_id": draft_id, "draft_type": "update_question"},
        session_id=ctx.session_id,
    )
    warn_suffix = ("\n\n" + "；".join(warnings)) if warnings else ""
    return "已创建修改草稿 %s（目标题目 %s），待用户确认后提交。%s" % (draft_id, target_id, warn_suffix)


def _execute_add_note_draft(args, ctx):
    """添加备注草稿。禁直写：不调用 create_question_note。

    type_name 必须匹配备注类型表已有类型（Agent 无权创建新备注类型），
    找不到则返回可用类型列表提示 LLM。
    """
    target_id = args.get("target_question_id")
    type_name = args.get("type_name")
    content = args.get("content")
    if not all([target_id, type_name, content]):
        return "缺少必填字段 target_question_id/type_name/content"
    _kind, _payload = _parse_target_ref(target_id)
    if _kind == "draft":
        return ("draft-%d 是草稿ID，不能作为题目ID 使用。"
                "给草稿加备注请用 add_note_to_draft 工具。") % _payload
    if _kind == "question" and ctx.draft_store.get("draft-%d" % _payload):
        return ("目标为题目ID %s，但当前草稿区存在草稿 draft-%s，请确认意图："
                "给草稿加备注用 add_note_to_draft，给题目加备注请明确继续。") % (_payload, _payload)
    q = get_question_by_id(target_id)
    if not q:
        return "未找到ID为 %s 的题目" % target_id
    if q["isInRecycleBin"] == 1:
        return "题目ID %s 已在回收站" % target_id
    # 匹配备注类型（Agent 无权创建新类型，只能用已有类型）
    note_type = get_note_type_by_name(type_name)
    if not note_type:
        return ("备注类型'%s'不存在，不可编造新类型。请使用已有备注类型。"
                "可用类型请通过检索确认。") % type_name
    type_id = note_type["id"]
    snapshot = {
        "target_question_id": target_id,
        "type_id": type_id,
        "type_name": type_name,
        "content": content,
    }
    draft_id = ctx.draft_store.add("add_note", snapshot, target_question_id=target_id)
    if draft_id is None:
        return "草稿数已达上限，请先确认或丢弃部分草稿"
    record_log(
        operator="agent:%s" % ctx.user_id,
        case_id=target_id,
        action="draft_create",
        detail={"draft_id": draft_id, "draft_type": "add_note", "type_name": type_name},
        session_id=ctx.session_id,
    )
    return "已创建备注草稿 %s（题目 %s，类型'%s'），待用户确认后提交。" % (draft_id, target_id, type_name)


def _execute_add_note_to_draft(args, ctx):
    """为草稿添加备注（追加到 snapshot.notes，随草稿一并提交）。

    禁直写：仅调 draft_store.update_snapshot，不 import/调用 create_question_note。
    """
    target_draft_id = args.get("target_draft_id")
    type_name = args.get("type_name")
    content = args.get("content")
    if not all([target_draft_id, type_name, content]):
        return "缺少必填字段 target_draft_id/type_name/content"
    kind, payload = _parse_target_ref(target_draft_id)
    if kind != "draft":
        return ("target_draft_id 必须是草稿ID（draft-N 格式），当前传入'%s'。"
                "给已入库题目加备注请用 add_note_draft 工具。") % target_draft_id
    draft_id = "draft-%d" % payload
    d = ctx.draft_store.get(draft_id)
    if not d:
        return "草稿 %s 不存在或已提交/丢弃" % draft_id
    if d.get("status") != "pending":
        return "草稿 %s 已提交/丢弃，不可再添加备注" % draft_id
    if d.get("draft_type") == "add_note":
        return "备注草稿 %s 不能再叠加备注" % draft_id
    note_type = get_note_type_by_name(type_name)
    if not note_type:
        return "备注类型'%s'不存在，不可编造新类型。请使用已有备注类型。" % type_name
    snapshot = d.get("snapshot_after", {}) or {}
    notes = list(snapshot.get("notes", []))
    notes.append({
        "type_id": note_type["id"],
        "type_name": type_name,
        "content": content,
    })
    ctx.draft_store.update_snapshot(draft_id, {"notes": notes})
    record_log(
        operator="agent:%s" % ctx.user_id,
        case_id=d.get("target_question_id"),
        action="draft_create",
        detail={"draft_id": draft_id, "draft_type": "add_note_to_draft", "type_name": type_name},
        session_id=ctx.session_id,
    )
    return "已为草稿 %s 添加备注（类型'%s'），随草稿提交时一并写入。" % (draft_id, type_name)


def _execute_insert_table_fragment(args, ctx):
    """生成表格片段，返回片段ID与Markdown。"""
    md = args.get("markdown_text", "")
    if not md:
        return "缺少 markdown_text"
    target_field = args.get("target_field", "content")
    # 用草稿区存片段（draft_type=table_fragment，不占正式草稿名额语义但复用存储）
    frag_id = ctx.fragment_store.add(
        source_file_id=None,
        page_range="table",
        text_content=md,
        table_markdown=md,
        region=target_field,
    )
    return "表格片段 %s 已生成，可粘贴到 %s 字段：\n\n%s" % (frag_id, target_field, md)


def _execute_insert_question_image(args, ctx):
    """插入题目内图片，校验 file_id 归属当前会话。与对话 AI 识别图像入口区分开。"""
    file_id = args.get("file_id")
    if not file_id:
        return "缺少 file_id"
    if not ctx.image_gallery.contains(file_id):
        return "file_id %s 不属于当前会话，请先在图片上传区上传" % file_id
    target_field = args.get("target_field", "content")
    anchor = args.get("anchor", "append")
    # 生成 Markdown 图片语法（路径用 file_id 占位，渲染时由页面替换为本地缓存路径）
    md_img = "![image](file_id:%s)" % file_id
    return "图片片段已生成（插入到 %s，方式 %s）：\n\n%s" % (target_field, anchor, md_img)


def _execute_pdf_upload_and_split(args, ctx):
    """PDF 多题识别拆分。页面图片已上传 Files API，LLM 视觉识别后调 create_question_draft。"""
    file_id = args.get("file_id")
    mode = args.get("mode", "multi_question")
    if not file_id:
        return "缺少 file_id"
    if not ctx.pdf_library.contains(file_id):
        return "PDF file_id %s 不属于当前会话" % file_id
    page_file_ids = ctx.pdf_library.get_page_file_ids(file_id)
    if not page_file_ids:
        return "PDF %s 无页面图片，请重新上传" % file_id
    record_log(
        operator="agent:%s" % ctx.user_id,
        case_id=None,
        action="pdf_split",
        detail={"file_id": file_id, "page_count": len(page_file_ids)},
        session_id=ctx.session_id,
    )
    if mode != "multi_question":
        return "mode=rubric_match 请使用 pdf_match_rubric 工具"
    return (
        "PDF %s 已上传 %d 页图片（file_id: %s）。"
        "请用视觉能力逐页识别题目，对每道题调用 create_question_draft 生成草稿。"
    ) % (file_id, len(page_file_ids), ", ".join(page_file_ids))


def _execute_pdf_match_rubric(args, ctx):
    """评分细则匹配。LLM 视觉识别细则后提供 rubrics 列表，工具做相似度匹配。禁直写。"""
    file_id = args.get("file_id")
    if not file_id:
        return "缺少 file_id"
    if not ctx.pdf_library.contains(file_id):
        return "PDF file_id %s 不属于当前会话" % file_id
    rubrics = args.get("rubrics") or []
    if not rubrics:
        return ("缺少 rubrics 参数。请用视觉能力识别 PDF 答案区的评分细则，"
                "按题号切分后以 rubrics=[{\"question_no\":\"1\",\"content\":\"...\"}] 传入。")
    rubric_type_name = args.get("rubric_type_name", "评分细则")
    record_log(
        operator="agent:%s" % ctx.user_id,
        case_id=None,
        action="rubric_split",
        detail={"file_id": file_id, "rubric_count": len(rubrics)},
        session_id=ctx.session_id,
    )

    # 检索候选题目：按题号 + 题干关键词
    candidates = []
    for r in rubrics:
        qno = r.get("question_no")
        if qno:
            candidates.extend(get_question_by_no_and_paper(qno))
        # 题干关键词补充候选
        kw = (r.get("content") or "")[:20]
        if kw:
            candidates.extend(search_by_content_similarity(kw, limit=200))
    # 去重
    seen = set()
    uniq_candidates = []
    for c in candidates:
        if c["questionID"] not in seen:
            seen.add(c["questionID"])
            uniq_candidates.append(c)

    # 获取评分细则类型 ID
    rubric_type = get_note_type_by_name(rubric_type_name)
    rubric_type_id = rubric_type["id"] if rubric_type else None

    try:
        match_results = match_rubric_batch(
            rubrics, uniq_candidates, rubric_type_id or 0,
            has_rubric_check=has_rubric_note if rubric_type_id else None,
        )
    except CandidateTooLargeError as e:
        return "候选题目过多: %s" % e

    # 生成匹配草稿
    match_ids = []
    for mr in match_results:
        r = mr["rubric"]
        mid = ctx.match_store.add(
            source_file_id=file_id,
            rubric_content=r.get("content", ""),
            rubric_question_no=r.get("question_no"),
            rubric_knowledge=r.get("knowledge"),
            matched_question_id=mr["matched_question_id"],
            match_features=mr["features"],
            confidence=mr["confidence"],
            note_type_id=rubric_type_id,
        )
        ctx.match_store.update_status(mid, mr["status"])
        match_ids.append(mid)

    record_log(
        operator="agent:%s" % ctx.user_id,
        case_id=None,
        action="rubric_match",
        detail={"file_id": file_id, "match_count": len(match_ids),
                "skipped": sum(1 for m in match_results if m["status"] == "skipped"),
                "low_conf": sum(1 for m in match_results if m["status"] == "low_confidence")},
        session_id=ctx.session_id,
    )
    return ("评分细则匹配完成，生成 %d 份匹配草稿：%s。"
            "请在匹配确认 UI 查看，确认后批量提交。") % (len(match_ids), ", ".join(match_ids))


def _execute_pdf_preview_fragment(args, ctx):
    """预览 PDF 原文片段。"""
    frag_id = args.get("fragment_id")
    if not frag_id:
        return "缺少 fragment_id"
    frag = ctx.fragment_store.get(frag_id)
    if not frag:
        return "未找到片段 %s" % frag_id
    parts = ["片段ID: %s" % frag_id, "页码范围: %s" % frag.get("page_range", ""),
             "题号提示: %s" % (frag.get("question_no_hint") or "无")]
    if frag.get("table_markdown"):
        parts.append("表格:\n%s" % frag["table_markdown"])
    parts.append("文本:\n%s" % frag.get("text_content", ""))
    return "\n\n".join(parts)


# ========== 工具分发 ==========
def _execute_record_tool(name, args, ctx):
    """工具执行分发。禁直写：所有执行函数均不写库。"""
    if name not in RECORD_AGENT_TOOL_NAMES:
        return "未知工具或非录题 Agent 工具: %s" % name
    try:
        if name == "create_question_draft":
            return _execute_create_question_draft(args, ctx)
        if name == "update_question_draft":
            return _execute_update_question_draft(args, ctx)
        if name == "add_note_draft":
            return _execute_add_note_draft(args, ctx)
        if name == "add_note_to_draft":
            return _execute_add_note_to_draft(args, ctx)
        if name == "insert_table_fragment":
            return _execute_insert_table_fragment(args, ctx)
        if name == "insert_question_image":
            return _execute_insert_question_image(args, ctx)
        if name == "pdf_upload_and_split":
            return _execute_pdf_upload_and_split(args, ctx)
        if name == "pdf_match_rubric":
            return _execute_pdf_match_rubric(args, ctx)
        if name == "pdf_preview_fragment":
            return _execute_pdf_preview_fragment(args, ctx)
        return "未知工具: %s" % name
    except Exception as e:
        return "工具执行出错(%s): %s" % (name, e)


def _preview_snapshot(snapshot):
    """生成草稿预览文本。"""
    lines = []
    for k, v in snapshot.items():
        if v:
            label = {"content": "题目", "answer": "答案", "analysis": "解析",
                     "source": "来源", "analysis_source": "解析来源",
                     "year": "年份", "paper_type": "卷种", "question_no": "题号",
                     "question_type": "题型", "knowledge_modules": "知识模块"}.get(k, k)
            val = str(v)[:200]
            lines.append("**%s**: %s" % (label, val))
    return "\n".join(lines) if lines else "（空草稿）"
