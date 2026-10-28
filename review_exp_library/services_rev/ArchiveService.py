"""归档、恢复、删除、备份服务。"""

import io
import json
import os
import zipfile
from datetime import datetime

from models_rev.Case import Case
from models_rev.CaseImage import CaseImage
from models_rev.User import User
from models_rev.db import get_session
from services_rev.ImageService import cleanup_images
from services_rev.LogService import record as log_record
from utils_rev.config import BASE_DIR
from utils_rev.dto import DeleteResult
from utils_rev.exceptions import StateTransitionError, NotFoundError


def archive(case_id: int, operator_id: int) -> bool:
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            raise NotFoundError("案例不存在")
        if c.status != "已发布":
            raise StateTransitionError(f"当前状态 {c.status} 不可归档")
        c.status = "已归档"
        c.update_time = datetime.utcnow()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id), case_id, "归档", session=s)
        return True


def restore(case_id: int, operator_id: int) -> bool:
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            raise NotFoundError("案例不存在")
        if c.status != "已归档":
            raise StateTransitionError(f"当前状态 {c.status} 不可恢复")
        c.status = "已发布"
        c.update_time = datetime.utcnow()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id), case_id, "恢复", session=s)
        return True


def delete_case(case_id: int, operator_id: int) -> DeleteResult:
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            raise NotFoundError("案例不存在")
        img_paths = [img.path for img in s.query(CaseImage).filter_by(case_id=case_id).all()]
        op = s.query(User).filter_by(id=operator_id).first()
        op_name = op.display_name if op else str(operator_id)
        log_record(op_name, case_id, "删除", session=s)
        s.query(CaseImage).filter_by(case_id=case_id).delete()
        s.query(Case).filter_by(id=case_id).delete()

    abs_paths = [str(BASE_DIR / p) for p in img_paths]
    succ, fail = cleanup_images(abs_paths)
    return DeleteResult(success=True, deleted_images=succ, failed_images=fail)


def list_archived():
    with get_session() as s:
        rows = s.query(Case).filter_by(status="已归档").order_by(Case.update_time.desc()).all()
        from utils_rev.dto import CaseSummary
        out = []
        for c in rows:
            creator = s.query(User).filter_by(id=c.created_by_id).first()
            title_sum = (c.title or c.content or c.content_before or "")[:60]
            out.append(CaseSummary(
                id=c.id, book=c.book, section=c.section, case_type=c.case_type,
                subject=c.subject, title_summary=title_sum, status=c.status,
                review_time=c.review_time, upload_time=c.upload_time,
                update_time=c.update_time,
                display_name=creator.display_name if creator else "",
            ))
        return out


def backup_export() -> bytes:
    with get_session() as s:
        cases = s.query(Case).all()
        data = []
        for c in cases:
            creator = s.query(User).filter_by(id=c.created_by_id).first()
            reviewer = s.query(User).filter_by(id=c.reviewer_id).first() if c.reviewer_id else None
            imgs = [img.path for img in s.query(CaseImage).filter_by(case_id=c.id).all()]
            data.append({
                "id": c.id, "book": c.book, "section": c.section,
                "case_type": c.case_type, "subject": c.subject,
                "title": c.title, "content_before": c.content_before,
                "content_after": c.content_after, "modify_reason": c.modify_reason,
                "why_modify": c.why_modify, "modify_note": c.modify_note,
                "content": c.content, "analysis": c.analysis, "why_good": c.why_good,
                "status": c.status, "reject_comment": c.reject_comment,
                "review_time": str(c.review_time) if c.review_time else None,
                "upload_time": str(c.upload_time) if c.upload_time else None,
                "update_time": str(c.update_time) if c.update_time else None,
                "review_at": str(c.review_at) if c.review_at else None,
                "creator": creator.display_name if creator else None,
                "reviewer": reviewer.display_name if reviewer else None,
                "images": imgs,
            })
        op = s.query(User).filter_by(role="chief").first()
        log_record(op.display_name if op else "chief", None, "备份", session=s)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("cases.json", json.dumps(data, ensure_ascii=False, indent=2))
        for c in data:
            for rel in c["images"]:
                abs_p = str(BASE_DIR / rel)
                if os.path.exists(abs_p):
                    zf.write(abs_p, arcname=rel)
    return buf.getvalue()
