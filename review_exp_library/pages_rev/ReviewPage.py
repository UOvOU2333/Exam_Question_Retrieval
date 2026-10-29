"""审核队列页。"""

import streamlit as st

from pages_rev.CaseDetailComponent import render_case_detail
from services_rev.AuthService import get_current_user, require_permission
from services_rev.CaseService import get_case_detail
from services_rev.ReviewService import list_pending_review, publish, reject
from utils_rev.exceptions import StateTransitionError, ValidationError, NotFoundError


def review_page():
    require_permission("review")
    user = get_current_user()

    editing_id = st.session_state.get("rev_review_editing_id")
    if editing_id is not None:
        if st.button("← 返回审核队列", key="rv_back", type="secondary"):
            st.session_state.pop("rev_review_editing_id", None)
            st.rerun()
        from pages_rev.CaseFormPage import case_form_page
        case_form_page(case_id=editing_id, keep_status=True)
        return

    st.subheader("待总编审核队列")

    pending = list_pending_review()
    if not pending:
        st.info("当前无待审核案例")
        return

    for sm in pending:
        with st.container(border=True):
            st.markdown(f"**#{sm.id} {sm.title_summary or '（无标题）'}**")
            st.caption(f"{sm.book} › {sm.section} › {sm.case_type} › {sm.subject} ｜ 负责人：{sm.owner_names or '—'} ｜ 提交人：{sm.submitter_name or sm.display_name} ｜ 更新 {sm.update_time:%Y-%m-%d %H:%M}")
            with st.expander("查看详情", expanded=False):
                detail = get_case_detail(sm.id)
                if detail:
                    render_case_detail(detail)

            col_pub, col_edit, col_rej = st.columns([1, 1, 2])
            with col_pub:
                if st.button("通过并发布", key=f"pub_{sm.id}", type="primary"):
                    try:
                        publish(sm.id, user["id"])
                        st.success("已发布")
                        st.rerun()
                    except (StateTransitionError, NotFoundError) as e:
                        st.error(str(e))
            with col_edit:
                if st.button("编辑", key=f"rv_edit_{sm.id}"):
                    st.session_state["rev_review_editing_id"] = sm.id
                    st.rerun()
            with col_rej:
                with st.form(f"rej_form_{sm.id}"):
                    comment = st.text_area("退回补充意见 *", key=f"rej_c_{sm.id}")
                    rej_clicked = st.form_submit_button("退回")
                if rej_clicked:
                    try:
                        reject(sm.id, user["id"], comment)
                        st.success("已退回")
                        st.rerun()
                    except (ValidationError, StateTransitionError, NotFoundError) as e:
                        st.error(str(e))
