import streamlit as st
import streamlit_antd_components as sac

from pages.authPage import login
from pages.searchPage import search
from pages.uploadPage import upload
from pages.userManagePage import user_manage


st.set_page_config(
    page_title="Exam Question Retrieval System",
    layout="wide"
)


def main():
    # Sidebar navigation
    with st.sidebar:
        st.title("题库系统")
        selected = sac.menu(
            items=[
                sac.MenuItem('用户中心', icon='person'),
                sac.MenuItem('试题检索', icon='database'),
                sac.MenuItem('试题上传', icon='upload'),
                sac.MenuItem('用户管理', icon='people'),
        ],
            open_all=True
        )

    if "nav" in st.session_state:
        selected = st.session_state["nav"]
        del st.session_state["nav"]

    # Page Routing
    if selected == '用户中心':
        login()

    elif selected == '试题检索':
        if not st.session_state.get("logged_in"):
            st.warning("请先登录")
            login()
        else:
            search()

    elif selected == '试题上传':
        if st.session_state.get("role") != "admin":
            st.error("无权限访问")
        else:
            upload()

    elif selected == '用户管理':
        if st.session_state.get("role") != "admin":
            st.error("无权限访问")
        else:
            user_manage()


if __name__ == "__main__":
    main()