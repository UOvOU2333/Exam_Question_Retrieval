"""
试卷类型工具：判断卷种是否属于"新教材"。
新教材规则：
- 2025年及以后：全部卷种均为新教材
- 2024年：仅下列卷种为新教材
  真题：新课标卷、全国甲卷、北京卷、天津卷、山东卷、浙江首考、浙江高考、江苏卷、河北卷、广东卷、湖南卷、湖北卷、福建卷、重庆卷、东北卷、江西卷、安徽卷、广西卷、甘肃卷、海南卷、贵州卷、上海卷
  官方模拟题：九省联考安徽卷、九省联考甘肃卷、九省联考广西卷、九省联考贵州卷、九省联考吉林、黑龙江卷、九省联考河南卷、九省联考江西卷、九省联考新疆卷、云南调研考试、贵州适应性测试、陕西省抽测
- 2023年：仅下列卷种为新教材
  真题：新课标卷、北京卷、天津卷、山东卷、海南卷、浙江首考、浙江高考、江苏卷、河北卷、广东卷、湖南卷、湖北卷、福建卷、东北卷、重庆卷、上海卷
  官方模拟题：四省联考
- 2022年：仅下列卷种为新教材
  真题：山东卷、东北卷、海南卷、北京卷、天津卷、上海卷
  官方模拟题：海南适应性测试
- 2022年以前：均不是新教材
"""

from typing import Optional

# 2022年新教材卷种（不含年份前缀）
NEW_TEXTBOOK_2022 = {
    "山东卷", "东北卷", "海南卷", "北京卷", "天津卷", "上海卷",
    "海南适应性测试",
}

# 2023年新教材卷种（不含年份前缀）
NEW_TEXTBOOK_2023 = {
    "新课标卷", "北京卷", "天津卷", "山东卷", "海南卷",
    "浙江首考", "浙江高考", "江苏卷", "河北卷", "广东卷",
    "湖南卷", "湖北卷", "福建卷", "东北卷", "重庆卷", "上海卷",
    "四省联考",
}

# 2024年新教材卷种（不含年份前缀）
NEW_TEXTBOOK_2024 = {
    "新课标卷", "全国甲卷", "北京卷", "天津卷", "山东卷",
    "浙江首考", "浙江高考", "江苏卷", "河北卷", "广东卷",
    "湖南卷", "湖北卷", "福建卷", "重庆卷", "东北卷",
    "江西卷", "安徽卷", "广西卷", "甘肃卷", "海南卷",
    "贵州卷", "上海卷",
    "九省联考安徽卷", "九省联考甘肃卷", "九省联考广西卷",
    "九省联考贵州卷", "九省联考吉林、黑龙江卷", "九省联考河南卷",
    "九省联考江西卷", "九省联考新疆卷",
    "云南调研考试", "贵州适应性测试", "陕西省抽测",
}

# 按年份索引
NEW_TEXTBOOK_BY_YEAR = {
    2022: NEW_TEXTBOOK_2022,
    2023: NEW_TEXTBOOK_2023,
    2024: NEW_TEXTBOOK_2024,
}


def is_new_textbook(year: Optional[int], paper_type: Optional[str]) -> bool:
    """
    判断给定的年份和卷种是否属于"新教材"。

    规则：
    - year >= 2025: 全部为新教材，直接返回 True
    - year < 2022: 都不是新教材，直接返回 False
    - year 在 2022-2024 之间: 检查 paper_type 是否在对应年份的已知列表中

    Args:
        year: 年份（可为 None）
        paper_type: 卷种名称（可为 None），可能包含年份前缀如 "2022山东卷"

    Returns:
        bool: 是否为新教材
    """
    if year is None:
        return False

    # 2025年及以后：全部是新教材
    if year >= 2025:
        return True

    # 2022年以前：不是新教材
    if year < 2022:
        return False

    # 2022-2024年：需检查卷种是否在已知列表中
    if paper_type is None:
        return False

    known_set = NEW_TEXTBOOK_BY_YEAR.get(year)
    if known_set is None:
        return False

    # 去除可能的年份前缀进行匹配（如 "2022山东卷" -> "山东卷"）
    cleaned_type = paper_type.strip()
    # 尝试去掉形如 "2022" 的四位年份前缀
    year_prefix = str(year)
    if cleaned_type.startswith(year_prefix):
        cleaned_type = cleaned_type[len(year_prefix):]

    return cleaned_type in known_set


def get_new_textbook_sql_condition(year_param: str = "year", paper_type_param: str = "paper_type") -> str:
    """
    生成用于 SQL 查询的"新教材"筛选条件。

    该条件可直接嵌入 WHERE 子句中，用于从数据库中筛选出新教材的题目。
    数据库中的 paper_type 可能包含年份前缀（如 "2024新课标卷"）或不包含（如 "新课标卷"），
    因此使用 LIKE 模糊匹配以兼容两种情况。

    Args:
        year_param: SQL 中年份列的别名/名称
        paper_type_param: SQL 中卷种列的别名/名称

    Returns:
        str: 完整的 SQL 条件字符串（带括号），可直接用于 WHERE ... AND {condition}
    """
    conditions = []

    # 2025年及以后：全部
    conditions.append(f"{year_param} >= 2025")

    # 2024年：特定卷种
    for pt in sorted(NEW_TEXTBOOK_2024):
        # LIKE 匹配：卷种可以带或不带年份前缀
        conditions.append(
            f"({year_param} = 2024 AND {paper_type_param} LIKE '%{pt}')"
        )

    # 2023年：特定卷种
    for pt in sorted(NEW_TEXTBOOK_2023):
        conditions.append(
            f"({year_param} = 2023 AND {paper_type_param} LIKE '%{pt}')"
        )

    # 2022年：特定卷种
    for pt in sorted(NEW_TEXTBOOK_2022):
        conditions.append(
            f"({year_param} = 2022 AND {paper_type_param} LIKE '%{pt}')"
        )

    return "(" + " OR ".join(conditions) + ")"


# =====================
# 知识模块与题型
# =====================

KNOWLEDGE_MODULES = [
    "必修一", "必修二", "必修三", "必修四",
    "选必一", "选必二", "选必三",
]

QUESTION_TYPES = ["单项选择题", "不定项选择题", "填空题", "缺项选择题", "非选择题", "判断题"]


def detect_question_type(content, answer, question_no=None):
    """
    根据题目内容、答案、题号自动检测题型。

    返回:
        QUESTION_TYPES 中的题型 / None(无法确定，待人工)
    """
    if answer is None:
        answer = ""
    answer_stripped = answer.strip()

    # 明确的题型标识优先于答案形式；不定项、缺项也可能只有一个正确选项。
    if content:
        for question_type in QUESTION_TYPES:
            if content.strip().startswith(question_type) or content.strip().startswith(f"【{question_type}】"):
                return question_type

    # 判断题特征：答案为 T / F（不区分大小写）
    if answer_stripped and len(answer_stripped) == 1 and answer_stripped.upper() in ("T", "F"):
        return "判断题"

    # 单字母答案预填单项；多字母答案无法可靠区分具体选择题类型。
    if answer_stripped and len(answer_stripped) <= 4 and all(c in "ABCDabcd" for c in answer_stripped):
        return "单项选择题" if len(answer_stripped) == 1 else None

    # 非选择题特征：答案较长（>10 字符）
    if len(answer_stripped) > 10:
        return "非选择题"

    # 题号为中文数字（一、二、三…）通常是非选择题
    if question_no and question_no.strip() in ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十"):
        return "非选择题"

    # 题目以"阅读材料"开头通常是非选择题
    if content and content.strip().startswith("阅读材料"):
        return "非选择题"

    # 答案含换行 / 评分表 / "分" 字通常是非选择题
    if answer_stripped and ("\n" in answer_stripped or "|" in answer_stripped or "分" in answer_stripped):
        return "非选择题"

    # 无法确定
    return None


def knowledge_modules_to_str(modules):
    """将知识模块列表转为逗号分隔的存储字符串。

    兼容传入逗号分隔字符串（草稿 snapshot 里存的是字符串），
    避免把字符串按字符逐个 join 导致知识模块损坏。
    """
    if not modules:
        return ""
    if isinstance(modules, str):
        return ",".join(m.strip() for m in modules.split(",") if m.strip())
    return ",".join(modules)


def str_to_knowledge_modules(s):
    """将存储的逗号分隔字符串转为列表。"""
    if not s:
        return []
    return [m for m in s.split(",") if m.strip()]
