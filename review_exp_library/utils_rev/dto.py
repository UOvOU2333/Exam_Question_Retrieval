"""数据传输对象。"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class CaseInput:
    book_id: int
    section_id: int
    case_type_id: int
    subject_id: int
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
    editor_in_charge: Optional[str] = None
    created_by_id: Optional[int] = None
    owner_ids: List[int] = field(default_factory=list)
    image_paths: List[str] = field(default_factory=list)


@dataclass
class CaseSummary:
    id: int
    book_id: int
    section_id: int
    case_type_id: int
    subject_id: int
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
    submitter_name: Optional[str] = None
    owner_names: str = ""


@dataclass
class CaseDetail:
    id: int
    book_id: int
    section_id: int
    case_type_id: int
    subject_id: int
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
    editor_in_charge: Optional[str] = None
    owner_names: str = ""
    submitter_display_name: Optional[str] = None


@dataclass
class DeleteResult:
    success: bool
    deleted_images: List[str]
    failed_images: List[str]


@dataclass
class ImportResult:
    total: int
    imported: int
    skipped: int
    images_restored: int
    skipped_details: List[str] = field(default_factory=list)


@dataclass
class Member:
    id: int
    username: str
    display_name: str
    role: str
    is_deleted: bool


@dataclass
class CategoryNode:
    """[已废弃] 被 BookNode/SectionNode/CaseTypeNode/SubjectNode 取代，保留仅供旧代码兼容。"""
    id: int
    name: str
    parent_id: Optional[int]
    sort_order: int
    is_fixed: bool
    is_deleted: bool
    children: List["CategoryNode"] = field(default_factory=list)


@dataclass
class BookNode:
    id: int
    name: str
    sort_order: int
    is_deleted: bool


@dataclass
class SectionNode:
    id: int
    name: str
    sort_order: int
    is_deleted: bool


@dataclass
class CaseTypeNode:
    id: int
    section_id: int
    name: str
    sort_order: int
    is_deleted: bool


@dataclass
class SubjectNode:
    id: int
    name: str
    sort_order: int
    is_deleted: bool
