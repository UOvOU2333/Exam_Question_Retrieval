"""成员管理服务：完整用户管理 + 级别变更 + 账号自助。"""

import hashlib
from datetime import datetime

from models_rev.User import User
from models_rev.db import get_session
from services_rev.LogService import record as log_record
from utils_rev.dto import Member
from utils_rev.exceptions import ValidationError, NotFoundError
from utils_rev.permissions import ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER, ALL_ROLES


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _operator_role(s, operator_id):
    op = s.query(User).filter_by(id=operator_id).first()
    return op.role if op else None


def list_members(include_deleted=True):
    with get_session() as s:
        q = s.query(User).order_by(User.id)
        if not include_deleted:
            q = q.filter_by(is_deleted=False)
        return [
            Member(id=u.id, username=u.username, display_name=u.display_name,
                   role=u.role, is_deleted=u.is_deleted)
            for u in q.all()
        ]


def get_member(user_id):
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            return None
        return Member(id=u.id, username=u.username, display_name=u.display_name,
                      role=u.role, is_deleted=u.is_deleted)


def create_member(username, password, display_name, role, operator_id):
    username = (username or "").strip()
    display_name = (display_name or "").strip()
    if not username or not password or not display_name:
        raise ValidationError("账号/密码/姓名均不可为空")
    with get_session() as s:
        op_role = _operator_role(s, operator_id)
        if role == ROLE_ADMIN and op_role != ROLE_ADMIN:
            raise ValidationError("仅管理员可创建管理员")
        if role == ROLE_CHIEF and op_role != ROLE_ADMIN:
            raise ValidationError("仅管理员可创建总编")
        if role not in (ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER):
            raise ValidationError("非法角色")
        if s.query(User).filter_by(username=username).first():
            raise ValidationError("用户名已存在")
        u = User(username=username, password_hash=_hash(password),
                 display_name=display_name, role=role)
        s.add(u)
        s.flush()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id),
                   None, "新增用户", detail=f"新增 {username}", session=s)
        return u.id


def update_role(user_id, new_role, operator_id):
    if new_role not in ALL_ROLES:
        raise ValidationError("非法角色")
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise NotFoundError("用户不存在")
        if u.role == ROLE_ADMIN and u.id == operator_id:
            raise ValidationError("不可变更自己的管理员角色")
        op_role = _operator_role(s, operator_id)
        if new_role == ROLE_ADMIN and op_role != ROLE_ADMIN:
            raise ValidationError("仅管理员可变更为管理员")
        if u.role == ROLE_CHIEF and op_role != ROLE_ADMIN:
            raise ValidationError("总编角色不可变更")
        if u.is_deleted:
            raise ValidationError("已禁用用户不可变更角色，请先恢复")

        old_role = u.role
        u.role = new_role
        u.updated_at = datetime.utcnow()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id),
                   None, "修改角色", detail=f"{u.username}: {old_role}->{new_role}", session=s)
        return True


def soft_delete_user(user_id, operator_id):
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise NotFoundError("用户不存在")
        op_role = _operator_role(s, operator_id)
        if u.role == ROLE_ADMIN and op_role != ROLE_ADMIN:
            raise ValidationError("管理员不可禁用")
        if u.role == ROLE_CHIEF and op_role != ROLE_ADMIN:
            raise ValidationError("总编不可禁用")
        if u.id == operator_id:
            raise ValidationError("不可禁用当前登录用户")
        if u.is_deleted:
            raise ValidationError("用户已禁用")
        u.is_deleted = True
        u.updated_at = datetime.utcnow()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id),
                   None, "禁用用户", detail=u.username, session=s)
        return True


def restore_user(user_id, operator_id):
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise NotFoundError("用户不存在")
        if not u.is_deleted:
            raise ValidationError("用户未禁用")
        u.is_deleted = False
        u.updated_at = datetime.utcnow()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id),
                   None, "恢复用户", detail=u.username, session=s)
        return True


def delete_user(user_id, operator_id):
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise NotFoundError("用户不存在")
        op_role = _operator_role(s, operator_id)
        if u.role == ROLE_ADMIN and op_role != ROLE_ADMIN:
            raise ValidationError("管理员不可删除")
        if u.role == ROLE_CHIEF and op_role != ROLE_ADMIN:
            raise ValidationError("总编不可删除")
        if u.id == operator_id:
            raise ValidationError("不可删除当前登录用户")
        if not u.is_deleted:
            raise ValidationError("仅可永久删除已禁用用户")
        uname = u.username
        s.query(User).filter_by(id=user_id).delete()
        op = s.query(User).filter_by(id=operator_id).first()
        log_record(op.display_name if op else str(operator_id),
                   None, "永久删除用户", detail=uname, session=s)
        return True


def verify_password(user_id, password):
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            return False
        return _hash(password) == u.password_hash


def is_username_taken(new_username, exclude_user_id=None):
    with get_session() as s:
        q = s.query(User).filter_by(username=new_username)
        if exclude_user_id is not None:
            q = q.filter(User.id != exclude_user_id)
        return q.first() is not None


def update_username(user_id, new_username):
    new_username = (new_username or "").strip()
    if not new_username:
        raise ValidationError("用户名不能为空")
    if is_username_taken(new_username, exclude_user_id=user_id):
        raise ValidationError("用户名已存在")
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise NotFoundError("用户不存在")
        old = u.username
        u.username = new_username
        u.updated_at = datetime.utcnow()
        log_record(u.display_name, None, "修改用户名", detail=f"{old}->{new_username}", session=s)
        return True


def update_password(user_id, new_password):
    if not new_password or not new_password.strip():
        raise ValidationError("密码不能为空")
    with get_session() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise NotFoundError("用户不存在")
        u.password_hash = _hash(new_password)
        u.updated_at = datetime.utcnow()
        log_record(u.display_name, None, "修改密码", session=s)
        return True
