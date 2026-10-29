"""CaseType 模型（案例类型实体，隶属板块）。"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index

from models_rev.db import Base


class CaseType(Base):
    __tablename__ = "case_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    layout_key = Column(String(32), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_ct_section_sort", "section_id", "sort_order", "is_deleted"),
    )
