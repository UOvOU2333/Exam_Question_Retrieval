"""固定分类体系服务：书名/板块/案例类型/学科与字段布局。"""

from utils_rev.field_spec import FieldSpec

BOOKS = [
    "《大题必备·材料词》",
    "《必刷100讲》",
    "《最后十课》",
    "《解题大师》",
]

SECTIONS = ["审稿问题汇总", "审稿优秀案例"]

SECTION_PROBLEM = "审稿问题汇总"
SECTION_EXCELLENT = "审稿优秀案例"

CASE_TYPES_BY_SECTION = {
    SECTION_PROBLEM: ["知识类问题", "解析类问题"],
    SECTION_EXCELLENT: ["知识类优秀案例", "解析类优秀案例"],
}

SUBJECTS = [
    "必修一中特",
    "必修二经济",
    "必修三政法",
    "必修四哲文",
    "选必一国政经",
    "选必二法律",
    "选必三逻辑",
]

_FIELD_LABELS = {
    "title": "题目",
    "content_before": "修改前",
    "content_after": "修改后",
    "modify_reason": "修改理由和注意事项",
    "why_modify": "为什么这样改",
    "modify_note": "修改注意事项",
    "content": "内容",
    "analysis": "解析",
    "why_good": "为什么好",
}

_LAYOUTS = {
    "知识类问题": [
        FieldSpec("content_before", "修改前", True),
        FieldSpec("content_after", "修改后", True),
        FieldSpec("modify_reason", "修改理由和注意事项", True),
    ],
    "解析类问题": [
        FieldSpec("title", "题目", True),
        FieldSpec("content_before", "修改前", True),
        FieldSpec("content_after", "修改后", True),
        FieldSpec("why_modify", "为什么这样改", True),
        FieldSpec("modify_note", "修改注意事项", True),
    ],
    "知识类优秀案例": [
        FieldSpec("content", "内容", True),
        FieldSpec("why_good", "为什么好", True),
    ],
    "解析类优秀案例": [
        FieldSpec("title", "题目", True),
        FieldSpec("analysis", "解析", True),
        FieldSpec("why_good", "为什么好", True),
    ],
}


def get_books():
    return list(BOOKS)


def get_sections(book=None):
    return list(SECTIONS)


def get_case_types(section):
    return list(CASE_TYPES_BY_SECTION.get(section, []))


def get_subjects():
    return list(SUBJECTS)


def get_field_layout(case_type):
    if case_type not in _LAYOUTS:
        raise ValueError(f"非法案例类型: {case_type}")
    return [FieldSpec(f.name, f.label, f.required, f.applicable) for f in _LAYOUTS[case_type]]


def get_field_label(name):
    return _FIELD_LABELS.get(name, name)


def validate_catalog(book, section, case_type, subject):
    if book not in BOOKS:
        return False
    if section not in SECTIONS:
        return False
    if case_type not in CASE_TYPES_BY_SECTION.get(section, []):
        return False
    if subject not in SUBJECTS:
        return False
    return True
