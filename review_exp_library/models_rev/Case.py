"""Case 模型。"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Index, Date
)
from sqlalchemy.orm import relationship

from models_rev.db import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, autoincrement=True)

    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False, index=True)
    case_type_id = Column(Integer, ForeignKey("case_types.id"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)

    title = Column(Text)
    content_before = Column(Text)
    content_after = Column(Text)
    modify_reason = Column(Text)
    why_modify = Column(Text)
    modify_note = Column(Text)
    content = Column(Text)
    analysis = Column(Text)
    why_good = Column(Text)

    status = Column(String(16), nullable=False, default="草稿")
    reject_comment = Column(Text)
    source_draft = Column(Text)

    review_time = Column(Date)
    upload_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    update_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    review_at = Column(DateTime)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    images = relationship(
        "CaseImage",
        backref="case",
        cascade="all, delete-orphan",
        order_by="CaseImage.uploaded_at",
    )
    creator = relationship("User", foreign_keys=[created_by_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    book = relationship("Book", foreign_keys=[book_id])
    section = relationship("Section", foreign_keys=[section_id])
    case_type = relationship("CaseType", foreign_keys=[case_type_id])
    subject = relationship("Subject", foreign_keys=[subject_id])

    __table_args__ = (
        Index("idx_catalog_status", "book_id", "section_id", "case_type_id", "subject_id", "status"),
        Index("idx_status", "status"),
        Index("idx_update_time", "update_time"),
        Index("idx_upload_time", "upload_time"),
        Index("idx_review_time", "review_time"),
    )
