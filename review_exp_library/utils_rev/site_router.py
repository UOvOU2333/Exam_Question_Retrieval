"""站内页面路由封装，集中管理题库与审稿经验库之间的跳转，杜绝硬编码 IP/URL。"""

import streamlit as st


def go_to_main_site():
    try:
        st.switch_page("main.py")
    except Exception:
        st.warning("页面跳转失败，请稍后重试")


def go_to_review_library():
    try:
        st.switch_page("pages/review.py")
    except Exception:
        st.warning("页面跳转失败，请稍后重试")
