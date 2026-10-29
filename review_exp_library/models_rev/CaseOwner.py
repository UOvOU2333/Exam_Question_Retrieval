"""Case 负责人多对多关联表。"""

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint

from models_rev.db import Base


class CaseOwner(Base):
    __tablename__ = "case_owners"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_owner"),)
