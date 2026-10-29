"""[已废弃] Category 模型：通用父子树分类节点，自引用 parent_id。

已被四级独立实体 Book/Section/CaseType/Subject 取代，不再被 init_db 导入，
新数据库不会创建 categories 表。保留此文件仅供旧库迁移参考。
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index

from models_rev.db import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True, index=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_fixed = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_cat_parent", "parent_id", "is_deleted"),
    )
