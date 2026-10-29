"""归档、恢复、删除、备份服务。"""

import io
import json
import os
import zipfile
from datetime import datetime, date

from models_rev.Case import Case
from models_rev.CaseImage import CaseImage
from models_rev.User import User
from models_rev.db import get_session
from services_rev.ImageService import cleanup_images
from services_rev.LogService import record as log_record
from utils_rev.config import BASE_DIR, IMAGE_DIR, IMAGE_REL_PREFIX
from utils_rev.dto import DeleteResult, ImportResult
from utils_rev.exceptions import StateTransitionError, NotFoundError, ValidationError


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
    from services_rev.CatalogService import _names_map
    with get_session() as s:
        rows = s.query(Case).filter_by(status="已归档").order_by(Case.update_time.desc()).all()
        from utils_rev.dto import CaseSummary
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
                book=names.get(c.book_id, ""), section=names.get(c.section_id, ""),
                case_type=names.get(c.case_type_id, ""), subject=names.get(c.subject_id, ""),
                title_summary=title_sum, status=c.status,
                review_time=c.review_time, upload_time=c.upload_time,
                update_time=c.update_time,
                display_name=creator.display_name if creator else "",
            ))
        return out


def backup_export() -> bytes:
    with get_session() as s:
        cases = s.query(Case).all()
        from services_rev.CatalogService import _names_map
        book_ids, section_ids, case_type_ids, subject_ids = set(), set(), set(), set()
        for c in cases:
            book_ids.add(c.book_id); section_ids.add(c.section_id)
            case_type_ids.add(c.case_type_id); subject_ids.add(c.subject_id)
        names = _names_map(book_ids, section_ids, case_type_ids, subject_ids)
        data = []
        for c in cases:
            creator = s.query(User).filter_by(id=c.created_by_id).first()
            reviewer = s.query(User).filter_by(id=c.reviewer_id).first() if c.reviewer_id else None
            imgs = [img.path for img in s.query(CaseImage).filter_by(case_id=c.id).all()]
            data.append({
                "id": c.id,
                "book": names.get(c.book_id, ""),
                "section": names.get(c.section_id, ""),
                "case_type": names.get(c.case_type_id, ""),
                "subject": names.get(c.subject_id, ""),
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


def _parse_dt(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None


def backup_import(zip_bytes: bytes, operator_id: int) -> ImportResult:
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    except zipfile.BadZipFile:
        raise ValidationError("无效的备份文件（无法解压）")

    if "cases.json" not in zf.namelist():
        zf.close()
        raise ValidationError("备份文件缺少 cases.json")

    try:
        data = json.loads(zf.read("cases.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        zf.close()
        raise ValidationError("cases.json 解析失败")

    if not isinstance(data, list):
        zf.close()
        raise ValidationError("cases.json 格式不正确")

    image_blobs = {}
    for name in zf.namelist():
        if name == "cases.json" or name.endswith("/"):
            continue
        image_blobs[name] = zf.read(name)
    zf.close()

    with get_session() as s:
        from models_rev.Book import Book
        from models_rev.Section import Section
        from models_rev.CaseType import CaseType
        from models_rev.Subject import Subject

        def _find_catalog(book_name, section_name, ct_name, sub_name):
            b = s.query(Book).filter_by(name=book_name, is_deleted=False).first()
            if not b:
                return None
            sec = s.query(Section).filter_by(name=section_name, is_deleted=False).first()
            if not sec:
                return None
            ct = s.query(CaseType).filter_by(name=ct_name, section_id=sec.id, is_deleted=False).first()
            if not ct:
                return None
            sub = s.query(Subject).filter_by(name=sub_name, is_deleted=False).first()
            if not sub:
                return None
            return b.id, sec.id, ct.id, sub.id

        def _find_user(display_name):
            if not display_name:
                return None
            u = s.query(User).filter_by(display_name=display_name, is_deleted=False).first()
            return u.id if u else None

        total = len(data)
        imported = 0
        skipped = 0
        images_restored = 0
        skipped_details = []

        for item in data:
            catalog = _find_catalog(
                item.get("book"), item.get("section"),
                item.get("case_type"), item.get("subject"),
            )
            if not catalog:
                skipped += 1
                skipped_details.append(
                    f"#{item.get('id', '?')} 分类缺失: "
                    f"{item.get('book')}/{item.get('section')}/{item.get('case_type')}/{item.get('subject')}"
                )
                continue

            book_id, section_id, ct_id, sub_id = catalog
            creator_id = _find_user(item.get("creator")) or operator_id
            reviewer_id = _find_user(item.get("reviewer"))

            case = Case(
                book_id=book_id, section_id=section_id,
                case_type_id=ct_id, subject_id=sub_id,
                title=item.get("title"),
                content_before=item.get("content_before"),
                content_after=item.get("content_after"),
                modify_reason=item.get("modify_reason"),
                why_modify=item.get("why_modify"),
                modify_note=item.get("modify_note"),
                content=item.get("content"),
                analysis=item.get("analysis"),
                why_good=item.get("why_good"),
                status=item.get("status") or "草稿",
                reject_comment=item.get("reject_comment"),
                review_time=_parse_date(item.get("review_time")),
                upload_time=_parse_dt(item.get("upload_time")) or datetime.utcnow(),
                update_time=_parse_dt(item.get("update_time")) or datetime.utcnow(),
                review_at=_parse_dt(item.get("review_at")),
                created_by_id=creator_id,
                reviewer_id=reviewer_id,
            )
            s.add(case)
            s.flush()

            for rel in item.get("images", []) or []:
                blob = image_blobs.get(rel)
                filename = os.path.basename(rel)
                target_rel = f"{IMAGE_REL_PREFIX}/{filename}"
                target_abs = IMAGE_DIR / filename
                if blob is not None:
                    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
                    if not target_abs.exists():
                        target_abs.write_bytes(blob)
                        images_restored += 1
                s.add(CaseImage(case_id=case.id, path=target_rel))

            imported += 1

        op = s.query(User).filter_by(id=operator_id).first()
        log_record(
            op.display_name if op else str(operator_id), None, "恢复备份",
            detail=f"导入 {imported}/{total} 条，跳过 {skipped} 条",
            session=s,
        )

    return ImportResult(
        total=total, imported=imported, skipped=skipped,
        images_restored=images_restored, skipped_details=skipped_details,
    )
