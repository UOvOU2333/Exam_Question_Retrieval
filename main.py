import streamlit as st
import streamlit_antd_components as sac

from authPage import login
from searchPage import search
from uploadPage import upload


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
                sac.MenuItem('用户', icon='person'),
                sac.MenuItem('数据库', icon='database'),
                sac.MenuItem('上传', icon='upload'),
            ],
            open_all=True
        )

    # Page Routing
    if selected == '用户':
        login()

    elif selected == '数据库':
        if not st.session_state.get("logged_in"):
            st.warning("请先登录")
            login()
        else:
            search()

    elif selected == '上传':
        if st.session_state.get("role") != "admin":
            st.error("无权限访问")
        else:
            upload()


if __name__ == "__main__":
    main()