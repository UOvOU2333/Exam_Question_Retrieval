"""Book 模型（书名实体，独立全局）。"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index

from models_rev.db import Base


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_book_sort", "sort_order", "is_deleted"),
    )
