"""案例 CRUD 服务（分类 ID 驱动）。"""

from datetime import datetime, date

from sqlalchemy import or_

from models_rev.Case import Case
from models_rev.CaseImage import CaseImage
from models_rev.User import User
from models_rev.db import get_session
from services_rev.CatalogService import (
    _names_map, get_field_layout_by_id, validate_catalog,
)
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
    layout = get_field_layout_by_id(data.case_type_id)
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
    case.editor_in_charge = data.editor_in_charge


def create_draft(data: CaseInput, owner_id: int) -> int:
    if not validate_catalog(data.book_id, data.section_id, data.case_type_id, data.subject_id):
        raise ValidationError("分类组合非法")
    _validate_required(data)

    now = datetime.utcnow()
    case = Case(
        book_id=data.book_id, section_id=data.section_id,
        case_type_id=data.case_type_id, subject_id=data.subject_id,
        status="草稿", upload_time=now, update_time=now, created_by_id=owner_id,
    )
    _apply_fields(case, data)

    with get_session() as s:
        s.add(case)
        s.flush()
        if not case.editor_in_charge:
            operator = s.query(User).filter_by(id=owner_id).first()
            case.editor_in_charge = operator.display_name if operator else str(owner_id)
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

        if not validate_catalog(data.book_id, data.section_id, data.case_type_id, data.subject_id):
            raise ValidationError("分类组合非法")
        _validate_required(data)

        case.book_id = data.book_id
        case.section_id = data.section_id
        case.case_type_id = data.case_type_id
        case.subject_id = data.subject_id
        _apply_fields(case, data)
        case.update_time = datetime.utcnow()

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
        if case.status == "待总编审核":
            return True
        if case.status not in ("草稿", "已退回"):
            raise StateTransitionError(f"当前状态 {case.status} 不可提交审核")

        layout = get_field_layout_by_id(case.case_type_id)
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
    book_id=None, section_id=None, case_type_id=None, subject_id=None,
    keyword=None, status_set=None, owner_id=None,
    sort_by="update_time", date_from=None, date_to=None,
    page=1, page_size=20,
):
    with get_session() as s:
        q = s.query(Case)
        if book_id:
            q = q.filter(Case.book_id == book_id)
        if section_id:
            q = q.filter(Case.section_id == section_id)
        if case_type_id:
            q = q.filter(Case.case_type_id == case_type_id)
        if subject_id:
            q = q.filter(Case.subject_id == subject_id)
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
        book_ids = {c.book_id for c in rows}
        section_ids = {c.section_id for c in rows}
        case_type_ids = {c.case_type_id for c in rows}
        subject_ids = {c.subject_id for c in rows}
        names = _names_map(book_ids, section_ids, case_type_ids, subject_ids)

        summaries = []
        for c in rows:
            creator = s.query(User).filter_by(id=c.created_by_id).first()
            reviewer = s.query(User).filter_by(id=c.reviewer_id).first() if c.reviewer_id else None
            title_sum = (c.title or c.content or c.content_before or "")[:60]
            summaries.append(CaseSummary(
                id=c.id,
                book_id=c.book_id, section_id=c.section_id,
                case_type_id=c.case_type_id, subject_id=c.subject_id,
                book=names["book"].get(c.book_id, ""), section=names["section"].get(c.section_id, ""),
                case_type=names["case_type"].get(c.case_type_id, ""), subject=names["subject"].get(c.subject_id, ""),
                title_summary=title_sum, status=c.status,
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
        layout = get_field_layout_by_id(c.case_type_id)
        fields = {}
        for spec in layout:
            fields[spec.name] = {
                "label": spec.label,
                "value": getattr(c, spec.name) or "",
            }
        images = [img.path for img in s.query(CaseImage).filter_by(case_id=c.id).order_by(CaseImage.uploaded_at).all()]
        creator = s.query(User).filter_by(id=c.created_by_id).first()
        reviewer = s.query(User).filter_by(id=c.reviewer_id).first() if c.reviewer_id else None
        names = _names_map({c.book_id}, {c.section_id}, {c.case_type_id}, {c.subject_id})
        return CaseDetail(
            id=c.id,
            book_id=c.book_id, section_id=c.section_id,
            case_type_id=c.case_type_id, subject_id=c.subject_id,
            book=names["book"].get(c.book_id, ""), section=names["section"].get(c.section_id, ""),
            case_type=names["case_type"].get(c.case_type_id, ""), subject=names["subject"].get(c.subject_id, ""),
            fields=fields, image_paths=images, status=c.status,
            reject_comment=c.reject_comment, review_time=c.review_time,
            upload_time=c.upload_time, update_time=c.update_time, review_at=c.review_at,
            creator_display_name=creator.display_name if creator else "",
            reviewer_display_name=reviewer.display_name if reviewer else None,
            editor_in_charge=c.editor_in_charge or "",
        )


def get_case_raw(case_id: int):
    with get_session() as s:
        c = s.query(Case).filter_by(id=case_id).first()
        if not c:
            return None
        images = [img.path for img in s.query(CaseImage).filter_by(case_id=c.id).order_by(CaseImage.uploaded_at).all()]
        return {
            "id": c.id, "book_id": c.book_id, "section_id": c.section_id,
            "case_type_id": c.case_type_id, "subject_id": c.subject_id,
            "title": c.title or "", "content_before": c.content_before or "",
            "content_after": c.content_after or "", "modify_reason": c.modify_reason or "",
            "why_modify": c.why_modify or "", "modify_note": c.modify_note or "",
            "content": c.content or "", "analysis": c.analysis or "",
            "why_good": c.why_good or "",
            "review_time": c.review_time, "status": c.status,
            "reject_comment": c.reject_comment, "update_time": c.update_time,
            "editor_in_charge": c.editor_in_charge or "",
            "image_paths": images,
        }
