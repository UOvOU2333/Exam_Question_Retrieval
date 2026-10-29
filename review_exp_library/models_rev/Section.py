"""Section 模型（板块实体，全局共享不隶属书）。"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index

from models_rev.db import Base


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_section_sort", "sort_order", "is_deleted"),
    )
