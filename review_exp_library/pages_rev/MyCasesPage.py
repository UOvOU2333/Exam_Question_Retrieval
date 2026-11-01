"""我的案例页：列出本人草稿/已退回/已发布，可编辑或删除草稿。"""

import streamlit as st

from services_rev.AuthService import get_current_user, require_login
from services_rev.CaseService import list_cases, delete_own_draft, get_case_detail
from pages_rev.CaseDetailComponent import render_case_detail
from utils_rev.exceptions import StateTransitionError, PermissionError, NotFoundError


def my_cases_page():
    require_login()
    user = get_current_user()

    editing_id = st.session_state.get("my_editing_id")
    if editing_id is not None:
        if st.button("← 返回我的案例", key="my_back", type="secondary"):
            st.session_state.pop("my_editing_id", None)
            st.rerun()
        from pages_rev.CaseFormPage import case_form_page
        case_form_page(case_id=editing_id)
        return

    st.subheader("我的案例")

    tab_draft, tab_rejected, tab_published = st.tabs(["草稿", "已退回", "已发布"])

    with tab_draft:
        drafts, _ = list_cases(
            owner_id=user["id"], status_set={"草稿"},
            sort_by="update_time", page=1, page_size=100,
        )
        _render_editable(drafts, user, allow_delete=True)

    with tab_rejected:
        rejected, _ = list_cases(
            owner_id=user["id"], status_set={"已退回"},
            sort_by="update_time", page=1, page_size=100,
        )
        _render_editable(rejected, user, allow_delete=False)

    with tab_published:
        pub, _ = list_cases(
            owner_id=user["id"], status_set={"已发布"},
            sort_by="update_time", page=1, page_size=100,
        )
        _render_editable(pub, user, allow_delete=False)


def _render_editable(summaries, user, allow_delete):
    if not summaries:
        st.info("暂无案例")
        return
    for sm in summaries:
        with st.container(border=True):
            st.markdown(f"**#{sm.id} {sm.title_summary or '（无标题）'}**")
            st.caption(f"{sm.book} › {sm.section} › {sm.case_type} › {sm.subject} ｜ 状态 {sm.status} ｜ 更新 {sm.update_time:%Y-%m-%d %H:%M}")
            col_e, col_d = st.columns([1, 1])
            with col_e:
                if st.button("编辑", key=f"my_e_{sm.id}", type="primary"):
                    st.session_state["my_editing_id"] = sm.id
                    st.rerun()
            with col_d:
                with st.expander("危险操作", expanded=False):
                    if allow_delete:
                        if st.button("删除", key=f"my_d_{sm.id}", use_container_width=True):
                            try:
                                delete_own_draft(sm.id, user["id"])
                                st.success("已删除")
                                st.rerun()
                            except (StateTransitionError, PermissionError, NotFoundError) as e:
                                st.error(str(e))

            with st.expander("查看", expanded=False):
                detail = get_case_detail(sm.id)
                if detail:
                    render_case_detail(detail)
