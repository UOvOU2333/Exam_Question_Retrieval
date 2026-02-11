# authPage.py
import streamlit as st
import sqlite3
import hashlib
from datetime import datetime


DB_PATH = "data/questions.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate(username, password):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT username, password_hash, role FROM users WHERE username = ?",
        (username,)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        return False, None

    username_db, password_hash_db, role = row
    if hash_password(password) == password_hash_db:
        return True, role

    return False, None


def login():
    st.subheader("用户登录")

    # 已登录，直接显示信息
    if st.session_state.get("logged_in"):
        st.success(f"已登录：{st.session_state['username']} ({st.session_state['role']})")

        if st.button("退出登录"):
            for k in ["logged_in", "username", "role"]:
                st.session_state.pop(k, None)
            # st.experimental_rerun()
        return

    username = st.text_input("用户名")
    password = st.text_input("密码", type="password")

    if st.button("登录"):
        ok, role = authenticate(username, password)
        if ok:
            st.session_state["logged_in"] = True
            st.session_state["username"] = username
            st.session_state["role"] = role
            st.success("登录成功")
            # st.experimental_rerun()
        else:
            st.error("用户名或密码错误")
