"""案例列表摘要组件。"""

import streamlit as st

from pages_rev.CaseDetailComponent import render_case_detail
from services_rev.CaseService import get_case_detail, revoke_to_draft
from utils_rev.exceptions import PermissionError, NotFoundError, StateTransitionError

_BADGE_STYLES = {
    "问题": "background:#dc3545;color:#ffffff;",
    "优秀": "background:#198754;color:#ffffff;",
}


def _section_badge(section: str) -> str | None:
    if not section:
        return None
    if "问题" in section:
        return "问题"
    if "优秀" in section:
        return "优秀"
    return None


def _render_badge(badge: str):
    style = _BADGE_STYLES.get(badge, "background:#6c757d;color:#ffffff;")
    st.markdown(
        f'<div style="{style}font-size:2.2rem;font-weight:800;'
        f'line-height:1.1;text-align:center;padding:0.45rem 0.3rem;'
        f'border-radius:0.5rem;letter-spacing:0.15rem;">{badge}</div>',
        unsafe_allow_html=True,
    )


def _render_case_head(sm):
    meta_parts = []
    if sm.owner_names:
        meta_parts.append(f"负责人：{sm.owner_names}")
    if sm.submitter_name:
        meta_parts.append(f"提交人：{sm.submitter_name}")

    head_col, meta_col = st.columns([7, 3])
    with head_col:
        st.markdown(f"**#{sm.id} {sm.title_summary or '（无标题）'}**")
        st.caption(f"{sm.book} › {sm.section} › {sm.case_type} › {sm.subject}")
    with meta_col:
        if meta_parts:
            st.markdown(
                f'<div style="text-align:right;color:#6c757d;font-size:0.85rem;'
                f'line-height:1.2;">{" ｜ ".join(meta_parts)}</div>',
                unsafe_allow_html=True,
            )

    status_col, time_col = st.columns([5, 5])
    with status_col:
        st.markdown(f"状态：{sm.status}")
    with time_col:
        st.caption(f"审稿 {sm.review_time} ｜ 更新 {sm.update_time:%Y-%m-%d}")


def render_case_list(summaries, show_diff: bool = True, is_chief: bool = False, user_id: int = None, keyword: str | None = None):
    if not summaries:
        st.info("暂无案例")
        return

    for sm in summaries:
        with st.container(border=True):
            badge = _section_badge(sm.section)
            if badge:
                badge_col, body_col = st.columns([1, 9], gap="small")
                with badge_col:
                    _render_badge(badge)
                with body_col:
                    _render_case_head(sm)
            else:
                _render_case_head(sm)
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
