"""审核流转服务。"""

from datetime import datetime

from models_rev.Case import Case
from models_rev.User import User
from models_rev.db import get_session
from services_rev.LogService import record as log_record
from utils_rev.dto import CaseSummary
from utils_rev.exceptions import StateTransitionError, ValidationError, NotFoundError


def list_pending_review():
    from services_rev.CatalogService import _names_map
    with get_session() as s:
        rows = s.query(Case).filter_by(status="待总编审核").order_by(Case.update_time.desc()).all()
        book_ids, section_ids, case_type_ids, subject_ids = set(), set(), set(), set()
        for c in rows:
            book_ids.add(c.book_id); section_ids.add(c.section_id)
            case_type_ids.add(c.case_type_id); subject_ids.add(c.subject_id)
        names = _names_map(book_ids, section_ids, case_type_ids, subject_ids)
        out = []
        for c in rows:
            creator = s.query(User).filter_by(id=c.created_by_id).first()
            title_sum = (c.title or c.content or c.content_before or "")[:60]
            out.append(CaseSummary(
                id=c.id,
                book_id=c.book_id, section_id=c.section_id,
                case_type_id=c.case_type_id, subject_id=c.subject_id,
                book=names["book"].get(c.book_id, ""), section=names["section"].get(c.section_id, ""),
                case_type=names["case_type"].get(c.case_type_id, ""), subject=names["subject"].get(c.subject_id, ""),
                title_summary=title_sum, status=c.status,
                review_time=c.review_time, upload_time=c.upload_time,
                update_time=c.update_time,
                display_name=creator.display_name if creator else "",
            ))
        return out


def publish(case_id: int, reviewer_id: int) -> bool:
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            raise NotFoundError("案例不存在")
        if c.status != "待总编审核":
            raise StateTransitionError(f"当前状态 {c.status} 不可发布")
        c.status = "已发布"
        c.reviewer_id = reviewer_id
        c.review_at = datetime.utcnow()
        c.update_time = datetime.utcnow()
        reviewer = s.query(User).filter_by(id=reviewer_id).first()
        log_record(reviewer.display_name if reviewer else str(reviewer_id),
                   case_id, "发布", session=s)
        return True


def reject(case_id: int, reviewer_id: int, comment: str) -> bool:
    if not comment or not comment.strip():
        raise ValidationError("退回须填写补充意见")
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            raise NotFoundError("案例不存在")
        if c.status != "待总编审核":
            raise StateTransitionError(f"当前状态 {c.status} 不可退回")
        c.status = "已退回"
        c.reject_comment = comment.strip()
        c.reviewer_id = reviewer_id
        c.review_at = datetime.utcnow()
        c.update_time = datetime.utcnow()
        reviewer = s.query(User).filter_by(id=reviewer_id).first()
        log_record(reviewer.display_name if reviewer else str(reviewer_id),
                   case_id, "退回", detail=comment.strip()[:200], session=s)
        return True
