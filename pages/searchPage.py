import streamlit as st
from utils.auth_utils import require_login


def search():
    require_login()

    st.title("题库检索")
    st.write(f"当前用户：{st.session_state['username']}")
