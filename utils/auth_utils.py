import streamlit as st


def require_login():
    if not st.session_state.get("logged_in"):
        st.warning("请先登录")
        st.stop()


def require_role(*roles):
    if st.session_state.get("role") not in roles:
        st.error("权限不足")
        st.stop()
