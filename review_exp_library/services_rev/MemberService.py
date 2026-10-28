"""成员管理服务。"""

from datetime import datetime

from models_rev.User import User
from models_rev.db import get_session
from services_rev.LogService import record as log_record
from utils_rev.dto import Member
from utils_rev.exceptions import ValidationError, NotFoundError
from utils_rev.permissions import ROLE_EDITOR, ROLE_VIEWER

EDITOR_COUNT_TARGET = 3


def list_members():
    with get_session() as s:
        rows = s.query(User).order_by(User.id).all()
        return [
            Member(id=u.id, username=u.username, display_name=u.display_name,
                   role=u.role, is_deleted=u.is_deleted)
            for u in rows
        ]


def update_role(user_id: int, new_role: str, operator_id: int) -> bool:
    if new_role not in (ROLE_EDITOR, ROLE_VIEWER):
        raise ValidationError("仅可调整为编辑或浏览者角色")
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise NotFoundError("用户不存在")
        if u.role == "chief":
            raise ValidationError("总编角色不可变更")

        if new_role == ROLE_EDITOR and u.role != ROLE_EDITOR:
            cur_editors = s.query(User).filter_by(role=ROLE_EDITOR, is_deleted=False).count()
            if cur_editors + 1 > EDITOR_COUNT_TARGET:
                raise ValidationError(f"编辑数量须维持 {EDITOR_COUNT_TARGET} 位")
        if new_role != ROLE_EDITOR and u.role == ROLE_EDITOR:
            cur_editors = s.query(User).filter_by(role=ROLE_EDITOR, is_deleted=False).count()
            if cur_editors - 1 < EDITOR_COUNT_TARGET:
                raise ValidationError(f"编辑数量须维持 {EDITOR_COUNT_TARGET} 位")

        u.role = new_role
        u.updated_at = datetime.utcnow()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id),
                   None, "修改", detail=f"调整 {u.username} 角色为 {new_role}", session=s)
        return True


def create_member(username: str, password: str, display_name: str, role: str, operator_id: int) -> int:
    import hashlib
    if role not in (ROLE_EDITOR, ROLE_VIEWER):
        raise ValidationError("仅可创建编辑或浏览者")
    with get_session() as s:
        existing = s.query(User).filter_by(username=username).first()
        if existing:
            raise ValidationError("用户名已存在")
        if role == ROLE_EDITOR:
            cur = s.query(User).filter_by(role=ROLE_EDITOR, is_deleted=False).count()
            if cur + 1 > EDITOR_COUNT_TARGET:
                raise ValidationError(f"编辑数量须维持 {EDITOR_COUNT_TARGET} 位")
        u = User(
            username=username,
            password_hash=hashlib.sha256(password.encode("utf-8")).hexdigest(),
            display_name=display_name, role=role,
        )
        s.add(u)
        s.flush()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id),
                   None, "创建", detail=f"新增成员 {username}", session=s)
        return u.id
