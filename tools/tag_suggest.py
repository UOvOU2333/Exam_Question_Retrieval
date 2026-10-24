"""
知识模块标签推荐（方案B：记忆文件/标签画像）。

核心思路：
- 内置一份基于教材结构的高质量模块画像（DEFAULT_MODULE_PROFILE），开箱即用。
- 可选的 data/knowledge_module_profile.json 用于增强/覆盖内置画像（由 build_tag_profile.py 离线生成）。
- 单题推荐 / 批量回填均只喂「画像 + 题目」，不喂样本，省 token。

命令行批量回填：
  python tools/tag_suggest.py              # 回填 knowledge_modules 为空的题目
  python tools/tag_suggest.py --force      # 重新标注所有题目（覆盖）
  python tools/tag_suggest.py --dry-run    # 试运行，不写库
"""
import json
import os
import sqlite3
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.exam_type_utils import KNOWLEDGE_MODULES, knowledge_modules_to_str

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
PROFILE_PATH = "data/knowledge_module_profile.json"
BATCH_SIZE = 8
DB_PATH = "data/questions.db"
CONTENT_TRUNCATE = 600

DEFAULT_MODULE_PROFILE = {
    "必修一": {
        "title": "中国特色社会主义",
        "outline": [
            "第一课 社会主义从空想到科学到实践的发展",
            "第二课 只有社会主义才能救中国",
            "第三课 只有中国特色社会主义才能发展中国",
            "第四课 只有坚持和发展中国特色社会主义才能实现中华民族伟大复兴",
        ],
        "themes": ["改革开放", "社会主义制度", "中国特色社会主义道路",
                   "新时代", "四个自信", "党的领导", "共同富裕"],
        "description": (
            "围绕中国特色社会主义的开创、坚持与发展。涉及改革开放历程与意义、"
            "社会主义制度的确立、新时代的内涵与主要矛盾、四个自信、党的领导、"
            "共同富裕与中国式现代化。常见时间线题、意义/原因类题。"
        ),
    },
    "必修二": {
        "title": "经济与社会",
        "outline": [
            "第一课 我国的生产资料所有制",
            "第二课 我国的社会主义市场经济体制",
            "第三课 我国的经济发展",
            "第四课 我国的个人收入分配与社会保障",
        ],
        "themes": ["市场经济", "基本经济制度", "宏观调控", "收入分配",
                   "社会保障", "新发展理念", "高质量发展", "供给侧结构性改革",
                   "乡村振兴", "对外开放", "经济全球化"],
        "description": (
            "围绕我国经济体制与经济发展。涉及市场与政府的关系、基本经济制度、"
            "宏观调控与市场失灵、收入分配公平、社会保障、新发展理念"
            "（创新协调绿色开放共享）、高质量发展、供给侧结构性改革、"
            "乡村振兴、经济全球化与对外开放。"
        ),
    },
    "必修三": {
        "title": "政治与法治",
        "outline": [
            "第一课 历史和人民的选择",
            "第二课 中国共产党的领导",
            "第三课 人民当家作主",
            "第四课 全面依法治国",
        ],
        "themes": ["党的领导", "人民当家作主", "全面依法治国", "国家机构",
                   "基层群众自治", "人民代表大会制度", "统一战线",
                   "民族区域自治", "法治政府", "全过程人民民主"],
        "description": (
            "围绕党的领导、人民当家作主、依法治国三者有机统一。涉及人民代表大会制度、"
            "国家机构职权与关系、基层群众自治制度、统一战线、民族区域自治、"
            "全面依法治国、法治政府与法治社会、全过程人民民主。"
        ),
    },
    "必修四": {
        "title": "哲学与文化",
        "outline": [
            "第一课 时代精神的精华",
            "第二课 探究世界的本质",
            "第三课 把握世界的规律",
            "第四课 探索认识的奥秘",
            "第五课 寻觅社会的真谛",
            "第六课 实现人生的价值",
            "第七课 继承发展中华优秀传统文化",
            "第八课 学习借鉴外来文化的有益成果",
            "第九课 发展中国特色社会主义文化",
        ],
        "themes": ["唯物论", "认识论", "辩证法", "历史唯物主义",
                   "价值观", "价值判断与选择", "文化传承", "文化创新",
                   "中华优秀传统文化", "社会存在与社会意识"],
        "description": (
            "围绕马克思主义哲学与文化。涉及唯物论（物质意识规律）、认识论"
            "（实践认识真理）、辩证法（联系发展矛盾量变质变否定之否定）、"
            "历史唯物主义（社会存在社会意识、生产力生产关系经济基础上层建筑）、"
            "价值观与价值判断选择、文化的传承创新、中华优秀传统文化、文化自信。"
        ),
    },
    "选必一": {
        "title": "当代国际政治与经济",
        "outline": [
            "第一课 各具特色的国家与国际组织",
            "第二课 世界多极化",
            "第三课 经济全球化",
            "第四课 中国的外交",
        ],
        "themes": ["国际关系", "世界多极化", "经济全球化", "国际组织",
                   "联合国", "世界贸易组织", "主权国家", "外交政策",
                   "多边主义", "全球治理"],
        "description": (
            "围绕当代国际政治与经济格局。涉及世界多极化趋势、经济全球化利弊与走向、"
            "国际组织（联合国/世贸组织/欧盟等）的作用、主权国家的权利义务、"
            "我国的外交政策与人类命运共同体、多边主义与全球治理。"
        ),
    },
    "选必二": {
        "title": "法律与生活",
        "outline": [
            "第一课 民事权利与义务",
            "第二课 合同与生活",
            "第三课 就业与创业",
            "第四课 家庭与婚姻",
            "第五课 法律与侵权责任",
            "第六课 纠纷解决方式",
        ],
        "themes": ["民事权利与义务", "合同", "婚姻家庭", "劳动就业",
                   "侵权责任", "物权", "知识产权", "纠纷解决",
                   "调解", "仲裁", "诉讼"],
        "description": (
            "围绕民事法律与日常生活。涉及民事权利能力与行为能力、合同的订立履行违约、"
            "婚姻家庭法律关系、劳动就业权利与劳动合同、侵权责任与归责原则、"
            "物权与知识产权、纠纷解决方式（调解仲裁诉讼）。"
        ),
    },
    "选必三": {
        "title": "逻辑与思维",
        "outline": [
            "第一课 科学思维与逻辑思维",
            "第二课 概念与判断",
            "第三课 推理与演绎推理",
            "第四课 逻辑思维的基本规律",
            "第五课 辩证思维的方法",
            "第六课 创新思维的方法",
        ],
        "themes": ["形式逻辑", "辩证思维", "创新思维", "概念", "判断",
                   "推理", "三段论", "同一律", "矛盾律", "排中律",
                   "质量互变", "联想思维", "发散思维"],
        "description": (
            "围绕逻辑思维与创新思维。涉及形式逻辑（概念判断推理、三段论、"
            "逻辑基本规律：同一律矛盾律排中律）、辩证思维（分析综合、质量互变）、"
            "创新思维（联想发散聚合逆向）、科学思维与思维定势的突破。"
        ),
    },
}


def _get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("deepseek_api_key")
    except Exception:
        pass
    return _read_key_from_secrets_file()


def _read_key_from_secrets_file():
    secrets_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".streamlit", "secrets.toml",
    )
    if not os.path.exists(secrets_path):
        return None
    try:
        with open(secrets_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("deepseek_api_key") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def load_profile():
    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_MODULE_PROFILE


def _build_profile_text(profile):
    lines = []
    for module in KNOWLEDGE_MODULES:
        info = profile.get(module, {})
        title = info.get("title", "")
        desc = info.get("description", "")
        themes = info.get("themes", [])
        outline = info.get("outline", [])
        themes_str = "、".join(themes) if themes else ""
        lines.append(f"【{module}】{title}")
        if outline:
            lines.append("  教材结构：" + "；".join(outline))
        if themes_str:
            lines.append(f"  关键主题：{themes_str}")
        if desc:
            lines.append(f"  特征：{desc}")
    return "\n".join(lines)


def _normalize_modules(raw_modules):
    result = []
    for m in raw_modules:
        if not isinstance(m, str):
            continue
        for km in KNOWLEDGE_MODULES:
            if km in m:
                if km not in result:
                    result.append(km)
                break
    return result


def _build_system_prompt(profile_text, batch=False):
    prompt = (
        "你是高中政治学科专家。根据题目内容判断它属于哪些知识模块（可多选）。\n\n"
        f"知识模块画像：\n{profile_text}\n\n"
        "判断要求：\n"
        "- 根据题目考查的核心知识点判断，一道题可能涉及 1-3 个模块。\n"
        "- 优先选最贴切的模块，不要勉强归类。\n"
        "- 如果题目跨模块（如用哲学分析经济现象），可多选。\n"
        "- modules 里只填模块编号（如\"必修一\"、\"选必三\"），不要带教材名后缀。\n"
        "- 严格依据画像中的模块编号，不要编造不存在的模块。\n"
    )
    if batch:
        prompt += (
            "- 你将收到多道题目，对每道题分别判断。\n"
            '- 返回JSON：{"results": [{"id": 题目ID, "modules": ["模块名"], "reason": "简述"}]}\n'
        )
    else:
        prompt += '- 返回JSON：{"modules": ["模块名"], "reason": "简述判断依据"}\n'
    return prompt


def _call_deepseek(messages, api_key=None, base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL, timeout=60):
    key = api_key or _get_api_key()
    if not key:
        return None, "未配置 DeepSeek API Key"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as e:
        return None, f"网络请求失败: {e}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"], None
    except (ValueError, KeyError, IndexError) as e:
        return None, f"解析响应失败: {e}"


def suggest_knowledge_modules(content, answer="", analysis="",
                              api_key=None, base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL):
    """
    单题推荐知识模块。
    返回: (modules: list[str], reason: str)
    """
    if not content or not content.strip():
        return [], "题目内容为空"

    profile = load_profile()
    profile_text = _build_profile_text(profile)

    question_text = f"【题目】{content[:CONTENT_TRUNCATE]}"
    if answer and answer.strip():
        question_text += f"\n【答案】{answer[:200]}"
    if analysis and analysis.strip():
        question_text += f"\n【解析】{analysis[:300]}"

    messages = [
        {"role": "system", "content": _build_system_prompt(profile_text)},
        {"role": "user", "content": f"请判断以下题目属于哪些知识模块：\n\n{question_text}"},
    ]

    raw, err = _call_deepseek(messages, api_key, base_url, model)
    if err:
        return [], err

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return [], f"返回非JSON: {raw[:200]}"

    modules = _normalize_modules(result.get("modules", []))
    reason = result.get("reason", "")
    return modules, reason


def _suggest_batch(batch, api_key=None, base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL):
    """
    批量推荐（内部）。batch: list[sqlite3.Row] 或 list[dict]。
    返回: list[(modules, reason)] 与 batch 等长。
    """
    if not batch:
        return []

    profile = load_profile()
    profile_text = _build_profile_text(profile)

    parts = []
    for idx, row in enumerate(batch):
        qid = row["questionID"] if isinstance(row, (sqlite3.Row, dict)) else row[0]
        content = (row["content"] or "")[:CONTENT_TRUNCATE]
        parts.append(f"--- 题目{idx + 1}（ID={qid}）---\n{content}")
    questions_text = "\n\n".join(parts)

    messages = [
        {"role": "system", "content": _build_system_prompt(profile_text, batch=True)},
        {"role": "user", "content": f"请判断以下 {len(batch)} 道题目各自属于哪些知识模块：\n\n{questions_text}"},
    ]

    raw, err = _call_deepseek(messages, api_key, base_url, model, timeout=90)
    if err:
        return [([], err)] * len(batch)

    try:
        data = json.loads(raw)
        results_list = data.get("results", [])
    except json.JSONDecodeError:
        return [([], f"返回非JSON: {raw[:200]}")] * len(batch)

    id_to_result = {}
    for item in results_list:
        qid = item.get("id")
        modules = _normalize_modules(item.get("modules", []))
        reason = item.get("reason", "")
        id_to_result[qid] = (modules, reason)

    out = []
    for row in batch:
        qid = row["questionID"] if isinstance(row, (sqlite3.Row, dict)) else row[0]
        out.append(id_to_result.get(qid, ([], "未返回")))
    return out


def backfill_knowledge_modules(force=False, dry_run=False, batch_size=BATCH_SIZE,
                               db_path=DB_PATH, api_key=None,
                               base_url=DEFAULT_BASE_URL, model=DEFAULT_MODEL):
    """
    批量回填知识模块标签。
    force=False: 仅处理 knowledge_modules 为空的题目。
    force=True: 重新标注所有题目。
    dry_run=True: 只输出不写库。
    返回: dict stats
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if force:
        cur.execute(
            "SELECT questionID, content, answer, analysis FROM questions "
            "WHERE isInRecycleBin = 0"
        )
        print("模式: --force（重新标注所有题目）")
    else:
        cur.execute(
            "SELECT questionID, content, answer, analysis FROM questions "
            "WHERE isInRecycleBin = 0 "
            "AND (knowledge_modules IS NULL OR knowledge_modules = '')"
        )
        print("模式: 仅回填知识模块为空的题目")

    rows = cur.fetchall()
    total = len(rows)
    print(f"待处理题目：{total} 道" + ("（dry-run，不写库）" if dry_run else ""))

    if total == 0:
        conn.close()
        return {"total": 0, "success": 0, "empty": 0}

    stats = {"total": total, "success": 0, "empty": 0}

    for i in range(0, total, batch_size):
        batch = rows[i:i + batch_size]
        results = _suggest_batch(batch, api_key, base_url, model)

        for row, (modules, reason) in zip(batch, results):
            qid = row["questionID"]
            if modules:
                if not dry_run:
                    km_str = knowledge_modules_to_str(modules)
                    cur.execute(
                        "UPDATE questions SET knowledge_modules = ? WHERE questionID = ?",
                        (km_str, qid),
                    )
                stats["success"] += 1
                print(f"  [{qid}] -> {modules}  ({reason[:50]})")
            else:
                stats["empty"] += 1
                print(f"  [{qid}] -> 无法判定  ({reason[:50]})")

        if not dry_run:
            conn.commit()
        done = min(i + batch_size, total)
        print(f"进度：{done}/{total}")

    conn.close()
    print(f"\n完成：成功标注 {stats['success']} / 空判定 {stats['empty']} / 共 {total}")
    return stats


if __name__ == "__main__":
    import sys
    _force = "--force" in sys.argv
    _dry = "--dry-run" in sys.argv
    backfill_knowledge_modules(force=_force, dry_run=_dry)
