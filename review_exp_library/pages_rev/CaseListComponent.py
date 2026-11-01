"""案例列表摘要组件。"""

import streamlit as st

from pages_rev.CaseDetailComponent import render_case_detail
from services_rev.CaseService import get_case_detail, revoke_to_draft
from utils_rev.exceptions import PermissionError, NotFoundError, StateTransitionError


def render_case_list(summaries, show_diff: bool = True, is_chief: bool = False, user_id: int = None, keyword: str | None = None):
    if not summaries:
        st.info("暂无案例")
        return

    for sm in summaries:
        with st.container(border=True):
            head_col, status_col, time_col = st.columns([5, 2, 3])
            with head_col:
                st.markdown(f"**#{sm.id} {sm.title_summary or '（无标题）'}**")
                st.caption(f"{sm.book} › {sm.section} › {sm.case_type} › {sm.subject}")
            with status_col:
                st.markdown(f"状态：{sm.status}")
            with time_col:
                st.caption(f"审稿 {sm.review_time} ｜ 更新 {sm.update_time:%Y-%m-%d}")
            meta_parts = []
            if sm.owner_names:
                meta_parts.append(f"负责人：{sm.owner_names}")
            if sm.submitter_name:
                meta_parts.append(f"提交人：{sm.submitter_name}")
            if meta_parts:
                st.caption(" ｜ ".join(meta_parts))
            with st.expander("查看详情", expanded=True):
                detail = get_case_detail(sm.id)
                if detail:
                    render_case_detail(detail, show_diff=show_diff, keyword=keyword)
                else:
                    st.warning("案例不存在")

            if is_chief:
                col_rev, col_edit = st.columns(2)
                with col_rev:
                    if st.button("撤回到草稿", key=f"br_revoke_{sm.id}", use_container_width=True):
                        try:
                            revoke_to_draft(sm.id, user_id)
                            st.success("已撤回到草稿")
                            st.rerun()
                        except (PermissionError, NotFoundError, StateTransitionError) as e:
                            st.error(str(e))
                with col_edit:
                    if st.button("编辑", key=f"br_edit_{sm.id}", use_container_width=True):
                        st.session_state["rev_browse_editing_id"] = sm.id
                        st.rerun()
