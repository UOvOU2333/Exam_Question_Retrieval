"""案例详情展示组件。"""

import streamlit as st

from services_rev.ImageService import abs_path
from utils_rev.dto import CaseDetail
from utils_rev.render_utils import render_markdown, safe_render_image


def render_case_detail(detail: CaseDetail, keyword: str | None = None):
    st.markdown(
        f"**书名**：{detail.book} ｜ "
        f"**问题与范例**：{detail.section} ｜ "
        f"**类型**：{detail.case_type} ｜ "
        f"**模块**：{detail.subject}"
    )

    if detail.status == "已退回" and detail.reject_comment:
        st.error(f"退回意见：{detail.reject_comment}")

    for name, info in detail.fields.items():
        label = info["label"]
        value = info["value"]
        if not (value and value.strip()):
            continue
        st.markdown(f"#### {label}")
        render_markdown(value, keyword=keyword)

    if detail.image_paths:
        st.markdown("#### 图片")
        for rel in detail.image_paths:
            safe_render_image(abs_path(rel))

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(f"审稿时间：{detail.review_time}")
    with col2:
        st.caption(f"上传时间：{detail.upload_time:%Y-%m-%d %H:%M}")
    with col3:
        st.caption(f"更新时间：{detail.update_time:%Y-%m-%d %H:%M}")

    meta = f"提交编辑：{detail.creator_display_name}"
    if detail.owner_names:
        meta += f" ｜ 负责人：{detail.owner_names}"
    elif detail.editor_in_charge:
        meta += f" ｜ 负责编辑：{detail.editor_in_charge}"
    if detail.submitter_display_name:
        meta += f" ｜ 提交人：{detail.submitter_display_name}"
    if detail.reviewer_display_name:
        meta += f" ｜ 审稿人：{detail.reviewer_display_name}"
    st.caption(meta)