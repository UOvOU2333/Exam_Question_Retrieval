"""案例 CRUD 服务。"""

from datetime import datetime, date

from sqlalchemy import or_, select

from models_rev.Case import Case
from models_rev.CaseImage import CaseImage
from models_rev.User import User
from models_rev.db import get_session
from services_rev.CatalogService import get_field_layout, validate_catalog
from services_rev.LogService import record as log_record
from utils_rev.dto import CaseInput, CaseSummary, CaseDetail
from utils_rev.exceptions import (
    ValidationError, PermissionError, StateTransitionError,
    ConcurrentUpdateError, NotFoundError,
)
from utils_rev.permissions import is_chief

_TEXT_FIELDS = (
    "title", "content_before", "content_after", "modify_reason",
    "why_modify", "modify_note", "content", "analysis", "why_good",
)


def _validate_required(data: CaseInput):
    layout = get_field_layout(data.case_type)
    values = {
        "title": data.title, "content_before": data.content_before,
        "content_after": data.content_after, "modify_reason": data.modify_reason,
        "why_modify": data.why_modify, "modify_note": data.modify_note,
        "content": data.content, "analysis": data.analysis, "why_good": data.why_good,
    }
    missing = []
    for spec in layout:
        if spec.required:
            val = values.get(spec.name)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(spec.label)
    if missing:
        raise ValidationError(f"以下必填字段缺失: {', '.join(missing)}")
    if data.review_time is None:
        raise ValidationError("审稿时间为必填项")


def _apply_fields(case: Case, data: CaseInput):
    case.title = data.title
    case.content_before = data.content_before
    case.content_after = data.content_after
    case.modify_reason = data.modify_reason
    case.why_modify = data.why_modify
    case.modify_note = data.modify_note
    case.content = data.content
    case.analysis = data.analysis
    case.why_good = data.why_good
    case.review_time = data.review_time
    case.source_draft = data.source_draft


def create_draft(data: CaseInput, owner_id: int) -> int:
    if not validate_catalog(data.book, data.section, data.case_type, data.subject):
        raise ValidationError("分类组合非法")
    _validate_required(data)

    now = datetime.utcnow()
    case = Case(
        book=data.book, section=data.section, case_type=data.case_type, subject=data.subject,
        status="草稿", upload_time=now, update_time=now, created_by_id=owner_id,
    )
    _apply_fields(case, data)

    with get_session() as s:
        s.add(case)
        s.flush()
        for p in data.image_paths:
            s.add(CaseImage(case_id=case.id, path=p, uploaded_at=now))
        operator = s.query(User).filter_by(id=owner_id).first()
        log_record(operator.display_name if operator else str(owner_id),
                   case.id, "创建", session=s)
        return case.id


def update_case(case_id: int, data: CaseInput, editor_id: int, loaded_updated_at) -> bool:
    with get_session() as s:
        case = s.query(Case).filter_by(id=case_id).first()
        if not case:
            raise NotFoundError("案例不存在")

        is_owner = case.created_by_id == editor_id
        editor = s.query(User).filter_by(id=editor_id).first()
        chief = is_chief(editor.role if editor else None)
        if not (is_owner or chief):
            raise PermissionError("仅本人或总编可编辑")

        if loaded_updated_at is not None:
            loaded = loaded_updated_at
            if hasattr(loaded, "to_pydatetime"):
                loaded = loaded.to_pydatetime()
            current = case.update_time
            if hasattr(current, "to_pydatetime"):
                current = current.to_pydatetime()
            if loaded != current:
                raise ConcurrentUpdateError("该案例已被他人更新，请刷新后重试")

        if not validate_catalog(data.book, data.section, data.case_type, data.subject):
            raise ValidationError("分类组合非法")
        _validate_required(data)

        case.book = data.book
        case.section = data.section
        case.case_type = data.case_type
        case.subject = data.subject
        _apply_fields(case, data)
        case.update_time = datetime.utcnow()

        if case.status == "已发布":
            case.status = "待总编审核"
            case.reviewer_id = None
            case.review_at = None

        if data.image_paths:
            s.query(CaseImage).filter_by(case_id=case.id).delete()
            now = datetime.utcnow()
            for p in data.image_paths:
                s.add(CaseImage(case_id=case.id, path=p, uploaded_at=now))

        op_name = editor.display_name if editor else str(editor_id)
        log_record(op_name, case.id, "修改", session=s)
        return True


def submit_for_review(case_id: int, editor_id: int) -> bool:
    with get_session() as s:
        case = s.query(Case).filter_by(id=case_id).first()
        if not case:
            raise NotFoundError("案例不存在")
        if case.status not in ("草稿", "已退回"):
            raise StateTransitionError(f"当前状态 {case.status} 不可提交审核")

        layout = get_field_layout(case.case_type)
        values = {f: getattr(case, f) for f in _TEXT_FIELDS}
        missing = [spec.label for spec in layout if spec.required and not (values.get(spec.name) or "").strip()]
        if missing:
            raise ValidationError(f"提交前请补全: {', '.join(missing)}")
        if case.review_time is None:
            raise ValidationError("审稿时间为必填项")

        case.status = "待总编审核"
        case.update_time = datetime.utcnow()
        case.reject_comment = None

        editor = s.query(User).filter_by(id=editor_id).first()
        log_record(editor.display_name if editor else str(editor_id),
                   case.id, "提交审核", session=s)
        return True


def delete_own_draft(case_id: int, editor_id: int) -> bool:
    with get_session() as s:
        case = s.query(Case).filter_by(id=case_id).first()
        if not case:
            raise NotFoundError("案例不存在")
        if case.created_by_id != editor_id:
            raise PermissionError("仅本人可删除草稿")
        if case.status != "草稿":
            raise StateTransitionError("仅草稿可自行删除，已提交请联系总编")

        img_paths = [img.path for img in s.query(CaseImage).filter_by(case_id=case.id).all()]
        editor = s.query(User).filter_by(id=editor_id).first()
        op_name = editor.display_name if editor else str(editor_id)
        log_record(op_name, case.id, "删除", session=s)
        s.query(CaseImage).filter_by(case_id=case.id).delete()
        s.query(Case).filter_by(id=case_id).delete()

    from services_rev.ImageService import cleanup_images
    cleanup_images([_abs(p) for p in img_paths])
    return True


def _abs(rel_path: str) -> str:
    from utils_rev.config import BASE_DIR
    return str(BASE_DIR / rel_path)


def list_cases(
    book=None, section=None, case_type=None, subject=None,
    keyword=None, status_set=None, owner_id=None,
    sort_by="update_time", date_from=None, date_to=None,
    page=1, page_size=20,
):
    with get_session() as s:
        q = s.query(Case)
        if book:
            q = q.filter(Case.book == book)
        if section:
            q = q.filter(Case.section == section)
        if case_type:
            q = q.filter(Case.case_type == case_type)
        if subject:
            q = q.filter(Case.subject == subject)
        if status_set:
            q = q.filter(Case.status.in_(status_set))
        if owner_id is not None:
            q = q.filter(Case.created_by_id == owner_id)
        if keyword:
            kw = f"%{keyword}%"
            q = q.filter(or_(
                Case.title.like(kw), Case.content_before.like(kw),
                Case.content_after.like(kw), Case.modify_reason.like(kw),
                Case.why_modify.like(kw), Case.modify_note.like(kw),
                Case.content.like(kw), Case.analysis.like(kw), Case.why_good.like(kw),
            ))
        if date_from:
            q = q.filter(Case.review_time >= date_from)
        if date_to:
            q = q.filter(Case.review_time <= date_to)

        total = q.count()

        sort_col = {
            "update_time": Case.update_time,
            "upload_time": Case.upload_time,
            "review_time": Case.review_time,
        }.get(sort_by, Case.update_time)
        q = q.order_by(sort_col.desc())

        if page_size:
            q = q.offset((page - 1) * page_size).limit(page_size)

        rows = q.all()
        summaries = []
        for c in rows:
            creator = s.query(User).filter_by(id=c.created_by_id).first()
            reviewer = s.query(User).filter_by(id=c.reviewer_id).first() if c.reviewer_id else None
            title_sum = (c.title or c.content or c.content_before or "")[:60]
            summaries.append(CaseSummary(
                id=c.id, book=c.book, section=c.section, case_type=c.case_type,
                subject=c.subject, title_summary=title_sum, status=c.status,
                review_time=c.review_time, upload_time=c.upload_time,
                update_time=c.update_time,
                display_name=creator.display_name if creator else "",
                reviewer_name=reviewer.display_name if reviewer else None,
            ))
        return summaries, total


def get_case_detail(case_id: int):
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            return None
        layout = get_field_layout(c.case_type)
        fields = {}
        for spec in layout:
            fields[spec.name] = {
                "label": spec.label,
                "value": getattr(c, spec.name) or "",
            }
        images = [img.path for img in s.query(CaseImage).filter_by(case_id=c.id).order_by(CaseImage.uploaded_at).all()]
        creator = s.query(User).filter_by(id=c.created_by_id).first()
        reviewer = s.query(User).filter_by(id=c.reviewer_id).first() if c.reviewer_id else None
        return CaseDetail(
            id=c.id, book=c.book, section=c.section, case_type=c.case_type, subject=c.subject,
            fields=fields, image_paths=images, status=c.status,
            reject_comment=c.reject_comment, review_time=c.review_time,
            upload_time=c.upload_time, update_time=c.update_time, review_at=c.review_at,
            creator_display_name=creator.display_name if creator else "",
            reviewer_display_name=reviewer.display_name if reviewer else None,
        )


def get_case_raw(case_id: int):
    """供表单预填使用，返回原始字段字典。"""
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            return None
        images = [img.path for img in s.query(CaseImage).filter_by(case_id=c.id).order_by(CaseImage.uploaded_at).all()]
        return {
            "id": c.id, "book": c.book, "section": c.section,
            "case_type": c.case_type, "subject": c.subject,
            "title": c.title or "", "content_before": c.content_before or "",
            "content_after": c.content_after or "", "modify_reason": c.modify_reason or "",
            "why_modify": c.why_modify or "", "modify_note": c.modify_note or "",
            "content": c.content or "", "analysis": c.analysis or "",
            "why_good": c.why_good or "",
            "review_time": c.review_time, "status": c.status,
            "reject_comment": c.reject_comment, "update_time": c.update_time,
            "image_paths": images,
        }
