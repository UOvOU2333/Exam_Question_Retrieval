"""数据传输对象。"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class CaseInput:
    book: str
    section: str
    case_type: str
    subject: str
    title: Optional[str] = None
    content_before: Optional[str] = None
    content_after: Optional[str] = None
    modify_reason: Optional[str] = None
    why_modify: Optional[str] = None
    modify_note: Optional[str] = None
    content: Optional[str] = None
    analysis: Optional[str] = None
    why_good: Optional[str] = None
    review_time: Optional[date] = None
    source_draft: Optional[str] = None
    image_paths: List[str] = field(default_factory=list)


@dataclass
class CaseSummary:
    id: int
    book: str
    section: str
    case_type: str
    subject: str
    title_summary: str
    status: str
    review_time: Optional[date]
    upload_time: datetime
    update_time: datetime
    display_name: str
    reviewer_name: Optional[str] = None


@dataclass
class CaseDetail:
    id: int
    book: str
    section: str
    case_type: str
    subject: str
    fields: dict
    image_paths: List[str]
    status: str
    reject_comment: Optional[str]
    review_time: Optional[date]
    upload_time: datetime
    update_time: datetime
    review_at: Optional[datetime]
    creator_display_name: str
    reviewer_display_name: Optional[str]


@dataclass
class DeleteResult:
    success: bool
    deleted_images: List[str]
    failed_images: List[str]


@dataclass
class Member:
    id: int
    username: str
    display_name: str
    role: str
    is_deleted: bool
