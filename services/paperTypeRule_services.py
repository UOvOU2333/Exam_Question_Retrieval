import json
import os

RULES_FILE = "data/paper_type_change_rules.json"

_DEFAULT_RULES = [
    {"id": 1, "from_year": 2026, "from_paper": "东北卷", "to_year": 2026, "to_paper": "黑吉辽蒙卷"},
    {"id": 2, "from_year": 2025, "from_paper": "东北卷", "to_year": 2025, "to_paper": "黑吉辽蒙卷"},
    {"id": 3, "from_year": 2024, "from_paper": "东北卷", "to_year": 2024, "to_paper": "黑吉辽卷"},
    {"id": 4, "from_year": 2023, "from_paper": "东北卷", "to_year": 2023, "to_paper": "辽宁卷"},
    {"id": 5, "from_year": 2022, "from_paper": "东北卷", "to_year": 2022, "to_paper": "辽宁卷"},
    {"id": 6, "from_year": 2021, "from_paper": "东北卷", "to_year": 2021, "to_paper": "辽宁卷"},
    {"id": 7, "from_year": 2025, "from_paper": "西北卷", "to_year": 2025, "to_paper": "陕晋青宁卷"},
    {"id": 8, "from_year": 2026, "from_paper": "西北卷", "to_year": 2026, "to_paper": "陕晋青宁卷"},
]


def _load():
    if not os.path.exists(RULES_FILE):
        _save(_DEFAULT_RULES)
        return list(_DEFAULT_RULES)
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(rules):
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def get_rules():
    """返回全部规则，每条含 id/from_year/from_paper/to_year/to_paper"""
    return _load()


def add_rule(from_year, from_paper, to_year, to_paper):
    rules = _load()
    next_id = max((r["id"] for r in rules), default=0) + 1
    rules.append({
        "id": next_id,
        "from_year": from_year,
        "from_paper": from_paper,
        "to_year": to_year,
        "to_paper": to_paper,
    })
    _save(rules)


def delete_rule(rule_id):
    rules = _load()
    rules = [r for r in rules if r["id"] != rule_id]
    _save(rules)
