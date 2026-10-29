"""独立登录认证服务。"""

import hashlib

import streamlit as st

from models_rev.User import User
from models_rev.db import get_session
from utils_rev.permissions import has_permission


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate(username, password):
    with get_session() as s:
        user = s.query(User).filter_by(username=username, is_deleted=False).first()
        if not user:
            return False, None, None
        if _hash(password) != user.password_hash:
            return False, None, None
        return True, user.role, user.id


def get_user_by_id(user_id):
    with get_session() as s:
        user = s.query(User).filter_by(id=user_id, is_deleted=False).first()
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        }


def get_current_user():
    if not st.session_state.get("rev_logged_in"):
        return None
    return {
        "id": st.session_state.get("rev_user_id"),
        "username": st.session_state.get("rev_username"),
        "display_name": st.session_state.get("rev_display_name"),
        "role": st.session_state.get("rev_role"),
    }


def set_current_user(user_id, username, display_name, role):
    st.session_state["rev_logged_in"] = True
    st.session_state["rev_user_id"] = user_id
    st.session_state["rev_username"] = username
    st.session_state["rev_display_name"] = display_name
    st.session_state["rev_role"] = role


def clear_current_user():
    for k in ("rev_logged_in", "rev_user_id", "rev_username", "rev_display_name", "rev_role"):
        st.session_state.pop(k, None)


def require_login():
    if not st.session_state.get("rev_logged_in"):
        st.warning("请先登录小北的审稿经验库")
        from pages_rev.LoginPage import login
        login()
        st.stop()


def require_permission(perm):
    role = st.session_state.get("rev_role")
    if not has_permission(role, perm):
        st.error("无权限执行该操作")
        st.stop()
