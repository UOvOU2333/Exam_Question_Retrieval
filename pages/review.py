"""审稿经验库页面模块挂接入口。

由 main.py sac.menu 选中"小北的审稿经验库"时调用。
不得调用 st.set_page_config（全局唯一一次由 main.py 调用）。
"""

import sys
from pathlib import Path

_REV_DIR = str(Path(__file__).resolve().parent.parent / "review_exp_library")
if _REV_DIR not in sys.path:
    sys.path.insert(0, _REV_DIR)

import streamlit as st

st.set_page_config(page_title="小北的审稿经验库", layout="wide")


@st.cache_resource
def _ensure_rev_db():
    from models_rev.db import init_db
    init_db()
    return True


def _render_rev_subnav() -> str:
    import streamlit_antd_components as sac
    with st.sidebar:
        st.markdown("### 审稿库导航")
        return sac.menu(
            items=[
                sac.MenuItem('浏览与搜索', icon='search'),
                sac.MenuItem('新建案例', icon='plus-circle'),
                sac.MenuItem('我的案例', icon='person'),
                sac.MenuItem('待审核', icon='clipboard-check'),
                sac.MenuItem('归档与备份', icon='archive'),
                sac.MenuItem('成员管理', icon='people'),
                sac.MenuItem('分类管理', icon='diagram-3'),
                sac.MenuItem('我的账号', icon='gear'),
                sac.MenuItem('登录', icon='lock'),
            ],
            open_all=True,
            key="rev_subnav_menu",
        )


def review_exp_library_page():
    try:
        _ensure_rev_db()
    except Exception:
        st.error("审稿库初始化失败，请稍后重试")
        return

    from pages_rev.SiteHeader import site_header
    from services_rev.AuthService import get_current_user
    from utils_rev.permissions import has_permission
    from utils.navbar_utils import navbar as main_navbar

    with st.sidebar:
        main_navbar("review")

    site_header()

    pending_edit = st.session_state.pop("rev_pending_edit_id", None)
    if pending_edit is not None:
        st.session_state["rev_edit_id"] = pending_edit
        st.session_state["rev_subnav_menu"] = "新建案例"

    menu = _render_rev_subnav()
    user = get_current_user()
    logged_in = user is not None

    if menu == "浏览与搜索":
        from pages_rev.BrowsePage import browse_page
        browse_page()
    elif menu == "新建案例":
        if not logged_in:
            st.warning("请先登录")
            from pages_rev.LoginPage import login
            login()
        elif not has_permission(user["role"], "create"):
            st.error("无新建权限")
        else:
            from pages_rev.CaseFormPage import case_form_page
            edit_id = st.session_state.pop("rev_edit_id", None)
            case_form_page(case_id=edit_id)
    elif menu == "我的案例":
        if not logged_in:
            st.warning("请先登录")
            from pages_rev.LoginPage import login
            login()
        else:
            from pages_rev.MyCasesPage import my_cases_page
            my_cases_page()
    elif menu == "待审核":
        if not logged_in:
            st.warning("请先登录")
            from pages_rev.LoginPage import login
            login()
        else:
            from pages_rev.ReviewPage import review_page
            review_page()
    elif menu == "归档与备份":
        if not logged_in:
            st.warning("请先登录")
            from pages_rev.LoginPage import login
            login()
        else:
            from pages_rev.ArchivePage import archive_page
            archive_page()
    elif menu == "成员管理":
        if not logged_in:
            st.warning("请先登录")
            from pages_rev.LoginPage import login
            login()
        else:
            from pages_rev.ManagePage import manage_page
            manage_page()
    elif menu == "分类管理":
        if not logged_in:
            st.warning("请先登录")
            from pages_rev.LoginPage import login
            login()
        else:
            from pages_rev.CategoryManagePage import category_manage_page
            category_manage_page()
    elif menu == "我的账号":
        if not logged_in:
            st.warning("请先登录")
            from pages_rev.LoginPage import login
            login()
        else:
            from pages_rev.AccountPage import account_page
            account_page()
    elif menu == "登录":
        from pages_rev.LoginPage import login
        login()


review_exp_library_page()
