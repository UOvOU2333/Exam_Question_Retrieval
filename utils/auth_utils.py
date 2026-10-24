import streamlit as st

from utils.permissions import has_permission


def require_login():
    if not st.session_state.get("logged_in"):
        st.warning("请先登录")
        st.stop()


def require_role(*roles):
    if st.session_state.get("role") not in roles:
        st.error("权限不足")
        st.stop()


def check_role(*roles):
    if st.session_state.get("role") not in roles:
        return False
    return True


def require_permission(perm):
    """基于权限名校验，不通过则报错并中止页面"""
    if not has_permission(st.session_state.get("role"), perm):
        st.error("权限不足")
        st.stop()


def check_permission(perm):
    """基于权限名软校验，返回布尔值"""
    return has_permission(st.session_state.get("role"), perm)
