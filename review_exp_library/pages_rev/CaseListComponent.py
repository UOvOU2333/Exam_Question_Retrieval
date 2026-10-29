"""案例列表摘要组件。"""

import streamlit as st

from pages_rev.CaseDetailComponent import render_case_detail
from services_rev.CaseService import get_case_detail
from utils_rev.dto import CaseSummary


def render_case_list(summaries):
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
            with st.expander("查看详情", expanded=False):
                detail = get_case_detail(sm.id)
                if detail:
                    render_case_detail(detail)
                else:
                    st.warning("案例不存在")
