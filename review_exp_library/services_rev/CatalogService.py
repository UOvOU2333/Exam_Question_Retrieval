"""分类体系服务：四级独立实体（Book/Section/CaseType/Subject）管理 + 固定字段布局。"""

from datetime import datetime
from typing import Optional

from models_rev.Book import Book
from models_rev.Section import Section
from models_rev.CaseType import CaseType
from models_rev.Subject import Subject
from models_rev.Case import Case
from models_rev.db import get_session
from utils_rev.dto import BookNode, SectionNode, CaseTypeNode, SubjectNode
from utils_rev.exceptions import ValidationError, NotFoundError
from utils_rev.field_spec import FieldSpec

_FIELD_LABELS = {
    "title": "题目",
    "content_before": "修改前",
    "content_after": "修改后",
    "modify_reason": "修改理由和注意事项",
    "why_modify": "为什么这样改",
    "modify_note": "修改注意事项",
    "content": "内容",
    "analysis": "解析",
    "why_good": "为什么好",
}

_LAYOUTS = {
    "知识类": [
        FieldSpec("content_before", "修改前", True),
        FieldSpec("content_after", "修改后", True),
        FieldSpec("modify_reason", "修改理由和注意事项", True),
    ],
    "解析类": [
        FieldSpec("title", "题目", True),
        FieldSpec("content_before", "修改前", True),
        FieldSpec("content_after", "修改后", True),
        FieldSpec("why_modify", "为什么这样改", True),
        FieldSpec("modify_note", "修改注意事项", True),
    ],
    "知识类优秀案例": [
        FieldSpec("content", "内容", True),
        FieldSpec("why_good", "为什么好", True),
    ],
    "解析类优秀案例": [
        FieldSpec("title", "题目", True),
        FieldSpec("analysis", "解析", True),
        FieldSpec("why_good", "为什么好", True),
    ],
}

_DEFAULT_LAYOUT_KEY = "知识类"


def _log(s, operator_id, action, detail):
    if operator_id is None:
        return
    from services_rev.LogService import record as log_record
    from models_rev.User import User
    op = s.query(User).filter_by(id=operator_id).first()
    log_record(op.display_name if op else str(operator_id), None, action, detail=detail, session=s)


def list_books():
    with get_session() as s:
        rows = s.query(Book).filter_by(is_deleted=False).order_by(Book.sort_order).all()
        return [BookNode(id=r.id, name=r.name, sort_order=r.sort_order, is_deleted=r.is_deleted) for r in rows]


def list_sections():
    with get_session() as s:
        rows = s.query(Section).filter_by(is_deleted=False).order_by(Section.sort_order).all()
        return [SectionNode(id=r.id, name=r.name, sort_order=r.sort_order, is_deleted=r.is_deleted) for r in rows]


def list_case_types(section_id):
    with get_session() as s:
        sec = s.query(Section).filter_by(id=section_id, is_deleted=False).first()
        if not sec:
            raise NotFoundError("问题与范例不存在")
        rows = s.query(CaseType).filter_by(section_id=section_id, is_deleted=False).order_by(CaseType.sort_order).all()
        return [CaseTypeNode(id=r.id, section_id=r.section_id, name=r.name, sort_order=r.sort_order, is_deleted=r.is_deleted) for r in rows]


def list_subjects():
    with get_session() as s:
        rows = s.query(Subject).filter_by(is_deleted=False).order_by(Subject.sort_order).all()
        return [SubjectNode(id=r.id, name=r.name, sort_order=r.sort_order, is_deleted=r.is_deleted) for r in rows]


def create_book(name, operator_id=None):
    name = (name or "").strip()
    if not name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        if s.query(Book).filter_by(name=name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        order = s.query(Book).filter_by(is_deleted=False).count()
        node = Book(name=name, sort_order=order + 1, is_deleted=False)
        s.add(node); s.flush()
        _log(s, operator_id, "新增分类", f"书名:{name}")
        return node.id


def create_section(name, operator_id=None):
    name = (name or "").strip()
    if not name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        if s.query(Section).filter_by(name=name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        order = s.query(Section).filter_by(is_deleted=False).count()
        node = Section(name=name, sort_order=order + 1, is_deleted=False)
        s.add(node); s.flush()
        _log(s, operator_id, "新增分类", f"问题与范例:{name}")
        return node.id


def create_case_type(name, section_id, layout_key=None, operator_id=None):
    name = (name or "").strip()
    if not name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        sec = s.query(Section).filter_by(id=section_id, is_deleted=False).first()
        if not sec:
            raise NotFoundError("问题与范例不存在")
        if s.query(CaseType).filter_by(section_id=section_id, name=name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        order = s.query(CaseType).filter_by(section_id=section_id, is_deleted=False).count()
        node = CaseType(section_id=section_id, name=name, layout_key=layout_key or _DEFAULT_LAYOUT_KEY, sort_order=order + 1, is_deleted=False)
        s.add(node); s.flush()
        _log(s, operator_id, "新增分类", f"案例类型:{name}")
        return node.id


def create_subject(name, operator_id=None):
    name = (name or "").strip()
    if not name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        if s.query(Subject).filter_by(name=name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        order = s.query(Subject).filter_by(is_deleted=False).count()
        node = Subject(name=name, sort_order=order + 1, is_deleted=False)
        s.add(node); s.flush()
        _log(s, operator_id, "新增分类", f"模块:{name}")
        return node.id


def rename_book(book_id, new_name, operator_id=None):
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        node = s.query(Book).filter_by(id=book_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(Book).filter_by(name=new_name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        old = node.name; node.name = new_name; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "重命名分类", f"书名:{old}->{new_name}")
        return True


def rename_section(section_id, new_name, operator_id=None):
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        node = s.query(Section).filter_by(id=section_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(Section).filter_by(name=new_name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        old = node.name; node.name = new_name; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "重命名分类", f"问题与范例:{old}->{new_name}")
        return True


def rename_case_type(case_type_id, new_name, operator_id=None):
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        node = s.query(CaseType).filter_by(id=case_type_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(CaseType).filter_by(section_id=node.section_id, name=new_name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        old = node.name; node.name = new_name; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "重命名分类", f"案例类型:{old}->{new_name}")
        return True


def rename_subject(subject_id, new_name, operator_id=None):
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValidationError("请输入名称")
    with get_session() as s:
        node = s.query(Subject).filter_by(id=subject_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(Subject).filter_by(name=new_name, is_deleted=False).first():
            raise ValidationError("名称已存在")
        old = node.name; node.name = new_name; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "重命名分类", f"模块:{old}->{new_name}")
        return True


def delete_book(book_id, operator_id=None):
    with get_session() as s:
        node = s.query(Book).filter_by(id=book_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(Case).filter_by(book_id=book_id).count() > 0:
            raise ValidationError("该分类下存在案例,无法删除")
        name = node.name; node.is_deleted = True; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "删除分类", f"书名:{name}")
        return True


def delete_section(section_id, operator_id=None):
    with get_session() as s:
        node = s.query(Section).filter_by(id=section_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(CaseType).filter_by(section_id=section_id, is_deleted=False).count() > 0:
            raise ValidationError("该分类下存在子分类,无法删除")
        if s.query(Case).filter_by(section_id=section_id).count() > 0:
            raise ValidationError("该分类下存在案例,无法删除")
        name = node.name; node.is_deleted = True; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "删除分类", f"问题与范例:{name}")
        return True


def delete_case_type(case_type_id, operator_id=None):
    with get_session() as s:
        node = s.query(CaseType).filter_by(id=case_type_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(Case).filter_by(case_type_id=case_type_id).count() > 0:
            raise ValidationError("该分类下存在案例,无法删除")
        name = node.name; node.is_deleted = True; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "删除分类", f"案例类型:{name}")
        return True


def delete_subject(subject_id, operator_id=None):
    with get_session() as s:
        node = s.query(Subject).filter_by(id=subject_id, is_deleted=False).first()
        if not node:
            raise NotFoundError("分类节点不存在")
        if s.query(Case).filter_by(subject_id=subject_id).count() > 0:
            raise ValidationError("该分类下存在案例,无法删除")
        name = node.name; node.is_deleted = True; node.updated_at = datetime.utcnow()
        _log(s, operator_id, "删除分类", f"模块:{name}")
        return True


def validate_catalog(book_id, section_id, case_type_id, subject_id):
    with get_session() as s:
        b = s.query(Book).filter_by(id=book_id, is_deleted=False).first()
        sec = s.query(Section).filter_by(id=section_id, is_deleted=False).first()
        ct = s.query(CaseType).filter_by(id=case_type_id, is_deleted=False).first()
        sub = s.query(Subject).filter_by(id=subject_id, is_deleted=False).first()
        if not (b and sec and ct and sub):
            return False
        if ct.section_id != section_id:
            return False
        return True


def _names_map(book_ids, section_ids, case_type_ids, subject_ids):
    result = {"book": {}, "section": {}, "case_type": {}, "subject": {}}
    with get_session() as s:
        if book_ids:
            for r in s.query(Book).filter(Book.id.in_(book_ids)).all():
                result["book"][r.id] = r.name
        if section_ids:
            for r in s.query(Section).filter(Section.id.in_(section_ids)).all():
                result["section"][r.id] = r.name
        if case_type_ids:
            for r in s.query(CaseType).filter(CaseType.id.in_(case_type_ids)).all():
                result["case_type"][r.id] = r.name
        if subject_ids:
            for r in s.query(Subject).filter(Subject.id.in_(subject_ids)).all():
                result["subject"][r.id] = r.name
    return result


def get_case_type_name(case_type_id):
    with get_session() as s:
        ct = s.query(CaseType).filter_by(id=case_type_id, is_deleted=False).first()
        return ct.name if ct else None


def get_field_layout(case_type_name):
    key = case_type_name if case_type_name in _LAYOUTS else _DEFAULT_LAYOUT_KEY
    return [FieldSpec(f.name, f.label, f.required, f.applicable) for f in _LAYOUTS[key]]


def get_field_layout_by_id(case_type_id):
    name = get_case_type_name(case_type_id)
    if name is None:
        return get_field_layout(_DEFAULT_LAYOUT_KEY)
    ct = None
    with get_session() as s:
        ct = s.query(CaseType).filter_by(id=case_type_id, is_deleted=False).first()
    layout_key = ct.layout_key if ct else _DEFAULT_LAYOUT_KEY
    key = layout_key if layout_key in _LAYOUTS else _DEFAULT_LAYOUT_KEY
    return [FieldSpec(f.name, f.label, f.required, f.applicable) for f in _LAYOUTS[key]]


def get_field_label(name):
    return _FIELD_LABELS.get(name, name)


def seed_catalog(session):
    if not (session.query(Book).count() == 0 and session.query(Section).count() == 0
            and session.query(CaseType).count() == 0 and session.query(Subject).count() == 0):
        return
    books = ["《大题必备·材料词》", "《必刷100讲》", "《最后十课》", "《解题大师》"]
    sections = ["审稿问题汇总", "审稿优秀案例"]
    problem_types = ["知识类", "解析类"]
    excellent_types = ["知识类优秀案例", "解析类优秀案例"]
    subjects = [
        "必修一中特", "必修二经济", "必修三政法", "必修四哲文",
        "选必一国政经", "选必二法律", "选必三逻辑",
    ]
    for i, name in enumerate(books, 1):
        session.add(Book(name=name, sort_order=i, is_deleted=False))
    session.flush()
    for i, name in enumerate(sections, 1):
        session.add(Section(name=name, sort_order=i, is_deleted=False))
    session.flush()
    sec_problem = session.query(Section).filter_by(name="审稿问题汇总").first()
    sec_excellent = session.query(Section).filter_by(name="审稿优秀案例").first()
    for i, ct_name in enumerate(problem_types, 1):
        session.add(CaseType(section_id=sec_problem.id, name=ct_name, layout_key=ct_name, sort_order=i, is_deleted=False))
    for i, ct_name in enumerate(excellent_types, 1):
        session.add(CaseType(section_id=sec_excellent.id, name=ct_name, layout_key=ct_name, sort_order=i, is_deleted=False))
    session.flush()
    for i, sub_name in enumerate(subjects, 1):
        session.add(Subject(name=sub_name, sort_order=i, is_deleted=False))
    session.flush()
