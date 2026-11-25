import base64
from pathlib import Path

import streamlit as st
import streamlit_antd_components as sac

from pages.authPage import login
from pages.searchPage import search
from pages.exportPage import export
from pages.aiChatPage import ai_chat
from pages.knowledgeBasePage import knowledge_base_page
from utils.navbar_utils import navbar
from utils.permissions import has_permission
from utils.app_logger import get_logger

log = get_logger("main")


BEIAN_CODE = "32011402012515"
BEIAN_URL = f"https://beian.mps.gov.cn/#/query/webSearch?code={BEIAN_CODE}"
BEIAN_LOGO = Path("static/images/logo/beian.png")


def render_beian_footer():
    try:
        img_b64 = base64.b64encode(BEIAN_LOGO.read_bytes()).decode("utf-8")
        icon_html = (
            f'<img src="data:image/png;base64,{img_b64}" '
            f'style="height:16px;width:16px;vertical-align:middle;margin-right:6px">'
        )
    except Exception:
        icon_html = ""

    st.markdown(
        f'<div style="text-align:center;padding:8px 0;font-size:13px;color:#888">'
        f'<a href="{BEIAN_URL}" target="_blank" rel="noreferrer" '
        f'style="color:#888;text-decoration:none">{icon_html}'
        f'苏公网安备{BEIAN_CODE}号</a></div>',
        unsafe_allow_html=True,
    )


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
                sac.MenuItem('知识库', icon='book'),
                sac.MenuItem('试卷导出', icon='download'),
                sac.MenuItem('智能助手', icon='chat'),
                sac.MenuItem('用户中心', icon='person'),
            ],
            open_all=True
        )

    if "nav" in st.session_state:
        selected = st.session_state["nav"]
        del st.session_state["nav"]

    # 记录页面访问（含登录态与用户名，便于卡死时定位谁在做什么）
    _user = st.session_state.get("username")
    _logged = st.session_state.get("logged_in", False)
    log.info("page_route selected=%s logged_in=%s user=%s", selected, _logged, _user or "-")

    # Page Routing
    if selected == '试题检索':
        if not st.session_state.get("logged_in"):
            st.warning("请先登录")
            login()
        else:
            search()

    elif selected == '知识库':
        if not st.session_state.get("logged_in"):
            st.warning("请先登录")
            login()
        elif not has_permission(st.session_state.get("role"), "kb_view"):
            st.error("权限不足，仅高级用户及以上可访问知识库")
        else:
            knowledge_base_page()

    elif selected == '试卷导出':
        if not st.session_state.get("logged_in"):
            st.warning("请先登录")
            login()
        else:
            export()

    elif selected == '智能助手':
        ai_chat()

    elif selected == '用户中心':
        login()

    render_beian_footer()


if __name__ == "__main__":
    main()