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
        search()

    elif selected == '上传':
        upload()


if __name__ == "__main__":
    main()