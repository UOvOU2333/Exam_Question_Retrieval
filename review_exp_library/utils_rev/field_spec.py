"""字段规格数据类。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    required: bool
    applicable: bool = True
