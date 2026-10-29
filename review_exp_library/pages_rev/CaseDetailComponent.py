"""案例详情展示组件。"""

import streamlit as st

from services_rev.CatalogService import get_field_label
from services_rev.ImageService import abs_path
from utils_rev.dto import CaseDetail


def render_case_detail(detail: CaseDetail):
    st.markdown(f"**书名**：{detail.book} ｜ **问题与范例**：{detail.section} ｜ **类型**：{detail.case_type} ｜ **模块**：{detail.subject}")

    if detail.status == "已退回" and detail.reject_comment:
        st.error(f"退回意见：{detail.reject_comment}")

    for name, info in detail.fields.items():
        label = info["label"]
        value = info["value"]
        with st.expander(label, expanded=False):
            if value:
                st.write(value)
            else:
                st.caption("（空）")

    if detail.image_paths:
        with st.expander("图片", expanded=False):
            for rel in detail.image_paths:
                try:
                    st.image(abs_path(rel))
                except Exception:
                    st.warning("图片加载失败")

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(f"审稿时间：{detail.review_time}")
    with col2:
        st.caption(f"上传时间：{detail.upload_time:%Y-%m-%d %H:%M}")
    with col3:
        st.caption(f"更新时间：{detail.update_time:%Y-%m-%d %H:%M}")

    st.caption(f"提交编辑：{detail.creator_display_name}" +
               (f" ｜ 审稿人：{detail.reviewer_display_name}" if detail.reviewer_display_name else ""))
