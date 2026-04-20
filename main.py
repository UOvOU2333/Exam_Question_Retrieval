import streamlit as st
import streamlit_antd_components as sac

from pages.authPage import login
from pages.searchPage import search
from pages.agentPage import agent
from utils.navbar_utils import navbar


st.set_page_config(
    page_title="Exam Question Retrieval System",
    layout="wide"
)


def main():
    # Sidebar navigation
    with st.sidebar:
        navbar("homePage")
        st.title("题库系统")
        selected = sac.menu(
            items=[
                sac.MenuItem('试题检索', icon='database'),
                sac.MenuItem('智能助手', icon='chat'),
                sac.MenuItem('用户中心', icon='person'),
            ],
            open_all=True
        )

    if "nav" in st.session_state:
        selected = st.session_state["nav"]
        del st.session_state["nav"]

    # Page Routing
    if selected == '试题检索':
        if not st.session_state.get("logged_in"):
            st.warning("请先登录")
            login()
        else:
            search()
    
    elif selected == '智能助手':
        if not st.session_state.get("logged_in"):
            st.warning("请先登录")
            login()
        else:
            agent()
    
    elif selected == '用户中心':
        login()


if __name__ == "__main__":
    main()