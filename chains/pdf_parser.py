"""PDF 解析适配层（封装 pdfplumber）。

为录题 Agent 工具集提供统一 PDF 解析接口：
  - 多题识别模式：提取每页文本/表格/图片引用，按题号边界拆分
  - 评分细则匹配模式：识别题目区/答案区分界，按题号切分评分细则

降级策略（PdfParseError）：
  - pdfplumber 未安装/导入失败 → "PDF 解析依赖缺失"
  - 扫描件（无文本） → "无可提取文本"
  - 加密 PDF → "PDF 加密或受保护"
  - 格式异常 → 异常消息
  - 解析超时 → 终止解析

PDF 解析失败降级预案：
  - pdfplumber 未安装/导入失败 → 提示管理员安装依赖，中止 PDF 流程，不影响图片录题与权限管理
  - 解析失败（扫描件/加密/格式异常） → 抛 PdfParseError → 调用方触发降级为整段文本草稿 → 写 pdf_parse_degrade 日志
  - 分区识别失败 → 提示用户手动指定分界页码或降级为整段文本
  - 图片提取失败 → 片段 image_refs 为空，原文对照预览仅展示文本与表格
  - 解析超时（>30s 或大 PDF >180s） → 终止解析，不生成草稿，提示用户拆分文件
"""
import re

# 解析超时（秒）
PDF_PARSE_TIMEOUT = 30
BIG_PDF_PARSE_TIMEOUT = 180
# 不限制解析页数（仅受 PDF 文件大小与超时约束）；保留常量便于需要时临时收紧
PDF_MAX_PAGES = None

# 题号正则（匹配 "1." "1、" "第1题" "题1" 等）
QUESTION_NO_PATTERN = re.compile(
    r"(?:第\s*([0-9]+)\s*题|题\s*([0-9]+)|([0-9]+)\s*[\.、．])"
)

# 答案/评分细则区章节标题关键词
ANSWER_SECTION_KEYWORDS = [
    "答案", "参考答案", "评分细则", "评分标准", "解析",
    "答案及解析", "答案与解析", "参考答案及解析",
]


class PdfParseError(Exception):
    """PDF 解析异常，触发降级。"""
    pass


def _import_pdfplumber():
    """延迟导入 pdfplumber，失败抛 PdfParseError。"""
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        raise PdfParseError("PDF 解析依赖缺失（pdfplumber 未安装）")


def _table_to_markdown(table):
    """将 pdfplumber 提取的表格转为 Markdown 表格字符串。"""
    if not table or not isinstance(table, list):
        return ""
    rows = []
    for row in table:
        if not row:
            continue
        cells = [str(c).replace("\n", " ").strip() if c is not None else "" for c in row]
        rows.append("| " + " | ".join(cells) + " |")
    if len(rows) < 2:
        return ""
    # 第二行加分隔符
    sep = "| " + " | ".join(["---"] * (rows[0].count("|") - 1)) + " |"
    return rows[0] + "\n" + sep + "\n" + "\n".join(rows[1:])


def parse_pdf(file_path, mode="multi_question"):
    """解析 PDF，提取每页文本/表格/图片引用。

    Args:
        file_path: PDF 文件本地路径
        mode: 'multi_question' 多题识别 / 'rubric_match' 评分细则匹配

    Returns:
        dict: {'pages': [{'page_no', 'text', 'tables', 'image_refs'}], 'page_count': int}

    Raises:
        PdfParseError: 解析失败（依赖缺失/扫描件/加密/格式异常）
    """
    pdfplumber = _import_pdfplumber()
    try:
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) == 0:
                raise PdfParseError("PDF 无页面")
            pages = []
            total_text = []
            pages_iter = pdf.pages if PDF_MAX_PAGES is None else pdf.pages[:PDF_MAX_PAGES]
            for i, page in enumerate(pages_iter):
                try:
                    text = page.extract_text(layout=True) or ""
                except Exception:
                    text = ""
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                try:
                    images = page.images or []
                except Exception:
                    images = []
                table_markdowns = [_table_to_markdown(t) for t in tables if t]
                pages.append({
                    "page_no": i + 1,
                    "text": text,
                    "tables": table_markdowns,
                    "image_refs": [{"x0": im.get("x0"), "y0": im.get("y0"),
                                    "x1": im.get("x1"), "y1": im.get("y1")}
                                   for im in images],
                })
                total_text.append(text)
            # 扫描件检测：所有页文本为空
            if not any(t.strip() for t in total_text):
                raise PdfParseError("无可提取文本（可能是扫描件）")
            return {"pages": pages, "page_count": len(pdf.pages)}
    except PdfParseError:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "encrypt" in msg or "password" in msg or "protected" in msg:
            raise PdfParseError("PDF 加密或受保护")
        raise PdfParseError("PDF 解析失败: %s" % e)


def extract_text_by_page(file_path):
    """按页提取纯文本列表。"""
    result = parse_pdf(file_path)
    return [p["text"] for p in result["pages"]]


def detect_question_answer_partition(pages):
    """识别题目区与答案/评分细则区分界页码。

    依据：
      1. 章节标题关键词（"答案"/"评分细则"/"参考答案" 等）
      2. 题号循环重启（题号从 1 重新开始）

    Args:
        pages: parse_pdf 返回的 pages 列表

    Returns:
        tuple[int, int] | None: (题目区末页, 答案区首页)；无法识别返回 None
    """
    # 1. 按章节标题关键词识别
    for idx, page in enumerate(pages):
        text = page.get("text", "")
        if not text:
            continue
        # 检查页首 200 字符内是否含答案区关键词
        head = text[:200]
        for kw in ANSWER_SECTION_KEYWORDS:
            if kw in head:
                if idx == 0:
                    continue
                return (pages[idx - 1]["page_no"], page["page_no"])

    # 2. 按题号循环重启识别
    last_question_no = 0
    for idx, page in enumerate(pages):
        text = page.get("text", "")
        if not text:
            continue
        nos = _find_question_nos(text)
        if not nos:
            continue
        first_no = nos[0]
        # 题号从 1 重新开始，且之前已有题号
        if first_no == 1 and last_question_no > 1 and idx > 0:
            return (pages[idx - 1]["page_no"], page["page_no"])
        if nos:
            last_question_no = max(last_question_no, nos[-1])

    return None


def _find_question_nos(text):
    """从文本中提取所有题号。"""
    nos = []
    for m in QUESTION_NO_PATTERN.finditer(text):
        for g in m.groups():
            if g:
                nos.append(int(g))
                break
    return nos


def split_rubrics_by_question_no(rubric_pages):
    """按题号边界切分答案区为多条独立细则。

    Args:
        rubric_pages: list[dict]，答案区每页 {'page_no', 'text', ...}

    Returns:
        list[dict]: [{'question_no': str, 'content': str, 'knowledge': str | None}]
    """
    # 合并答案区全文，保留题号标记
    full_text = "\n".join(p.get("text", "") for p in rubric_pages)
    if not full_text.strip():
        return []

    # 按题号正则切分
    matches = list(QUESTION_NO_PATTERN.finditer(full_text))
    if not matches:
        # 无题号，整体作为一条
        return [{"question_no": None, "content": full_text.strip(), "knowledge": None}]

    rubrics = []
    for i, m in enumerate(matches):
        # 提取题号
        qno = None
        for g in m.groups():
            if g:
                qno = g
                break
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()
        if content:
            rubrics.append({
                "question_no": qno,
                "content": content,
                "knowledge": None,
            })
    return rubrics


def split_questions_by_boundary(pages):
    """多题识别模式：按题号边界切分题目区为多道独立题目文本。

    Args:
        pages: parse_pdf 返回的 pages 列表

    Returns:
        list[dict]: [{'question_no': str | None, 'content': str, 'tables': list[str], 'page_range': str}]
    """
    full_text = "\n".join(p.get("text", "") for p in pages)
    matches = list(QUESTION_NO_PATTERN.finditer(full_text))

    if not matches:
        # 无题号边界，整体作为一道题（降级由调用方处理）
        return [{
            "question_no": None,
            "content": full_text.strip(),
            "tables": [],
            "page_range": "1-%d" % len(pages),
        }]

    questions = []
    for i, m in enumerate(matches):
        qno = None
        for g in m.groups():
            if g:
                qno = g
                break
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()
        if content:
            questions.append({
                "question_no": qno,
                "content": content,
                "tables": [],
                "page_range": "1-%d" % len(pages),
            })
    return questions
