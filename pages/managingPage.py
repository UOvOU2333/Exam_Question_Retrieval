import streamlit as st
import streamlit_antd_components as sac

from pages.authPage import login
from pages.uploadPage import upload
from pages.updatePage import update
from pages.userManagePage import user_manage
from pages.noteTypeManagingPage import note_type_management
from utils.navbar_utils import navbar, info_update


st.set_page_config(
    page_title="Exam Question Retrieval System",
    layout="wide"
)


def main():
    # Sidebar navigation
    with st.sidebar:
        navbar("managingPage")
        info_update()
        st.title("题库系统")
        selected = sac.menu(
            items=[
                sac.MenuItem('试题上传', icon='upload'),
                sac.MenuItem('试题更新', icon='recycle'),
                sac.MenuItem('标签管理', icon='tags'),
                sac.MenuItem('用户管理', icon='people'),
                sac.MenuItem('用户中心', icon='person'),
        ],
            open_all=True
        )

    # Page Routing
    if selected == '用户中心':
        login()

    elif selected == '试题上传':
        if st.session_state.get("role") != "admin":
            st.error("无权限访问")
        else:
            upload()
    
    elif selected == '试题更新':
        if st.session_state.get("role") != "admin":
            st.error("无权限访问")
        else:
            update()

    elif selected == '用户管理':
        if st.session_state.get("role") != "admin":
            st.error("无权限访问")
        else:
            user_manage()

    elif selected == '标签管理':
        if st.session_state.get("role") != "admin":
            st.error("无权限访问")
        else:
            note_type_management()


if __name__ == "__main__":
    main()