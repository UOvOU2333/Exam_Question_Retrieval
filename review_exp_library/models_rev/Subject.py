"""Subject 模型（学科实体，全局独立）。"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index

from models_rev.db import Base


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_sub_sort", "sort_order", "is_deleted"),
    )
