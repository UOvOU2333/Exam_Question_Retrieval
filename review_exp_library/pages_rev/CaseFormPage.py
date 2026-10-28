"""案例新建/编辑表单页。"""

from datetime import date

import streamlit as st

from services_rev.AuthService import get_current_user
from services_rev.CaseService import (
    create_draft, update_case, submit_for_review, get_case_raw,
)
from services_rev.CatalogService import (
    get_books, get_sections, get_case_types, get_subjects, get_field_layout,
)
from services_rev.ImageService import save_image
from utils_rev.dto import CaseInput
from utils_rev.exceptions import (
    ValidationError, PermissionError, StateTransitionError,
    ConcurrentUpdateError, NotFoundError,
)
from utils_rev.permissions import is_chief


def case_form_page(case_id=None):
    user = get_current_user()
    editing = case_id is not None
    raw = None
    if editing:
        raw = get_case_raw(case_id)
        if not raw:
            st.error("案例不存在")
            return
        if raw["status"] == "待总编审核" and not is_chief(user["role"]):
            st.warning("该案例已提交审核，等待总编审核中，暂不可编辑。")
            return

    st.subheader("编辑案例" if editing else "新建案例")

    if raw and raw.get("reject_comment"):
        st.error(f"退回意见：{raw['reject_comment']}")

    books = get_books()
    sections = get_sections()
    default_book_idx = books.index(raw["book"]) if raw else 0
    default_section_idx = sections.index(raw["section"]) if raw else 0

    col_b, col_s, col_t, col_sub = st.columns(4)
    with col_b:
        book = st.selectbox("书名", books, index=default_book_idx, key="cf_book")
    with col_s:
        section = st.selectbox("一级板块", sections, index=default_section_idx, key="cf_section")
    case_types = get_case_types(section)
    default_ct_idx = case_types.index(raw["case_type"]) if raw and raw["case_type"] in case_types else 0
    with col_t:
        case_type = st.selectbox("案例类型", case_types, index=default_ct_idx, key="cf_case_type")
    subjects = get_subjects()
    default_sub_idx = subjects.index(raw["subject"]) if raw else 0
    with col_sub:
        subject = st.selectbox("学科板块", subjects, index=default_sub_idx, key="cf_subject")

    layout = get_field_layout(case_type)
    field_values = {}
    for spec in layout:
        default_val = raw.get(spec.name, "") if raw else ""
        field_values[spec.name] = st.text_area(
            spec.label + (" *" if spec.required else ""),
            value=default_val, height=120, key=f"cf_{spec.name}",
        )

    default_review = raw["review_time"] if raw and raw["review_time"] else date.today()
    review_time = st.date_input("审稿时间 *", value=default_review, key="cf_review_time")

    uploaded = st.file_uploader(
        "插入图片（可多选）", type=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
        accept_multiple_files=True, key="cf_images",
    )

    existing_images = raw.get("image_paths", []) if raw else []
    if existing_images:
        with st.expander("已有图片", expanded=False):
            from services_rev.ImageService import abs_path
            for rel in existing_images:
                try:
                    st.image(abs_path(rel))
                except Exception:
                    st.warning("图片加载失败")

    source_draft = st.text_input("来源稿件（可选）", value=raw.get("source_draft", "") if raw else "", key="cf_source")

    col_save, col_submit = st.columns(2)
    with col_save:
        save_clicked = st.button("保存草稿", type="secondary", use_container_width=True)
    with col_submit:
        submit_clicked = st.button("提交审核", type="primary", use_container_width=True)

    if not (save_clicked or submit_clicked):
        return

    image_paths = list(existing_images)
    if uploaded:
        for f in uploaded:
            image_paths.append(save_image(f))

    data = CaseInput(
        book=book, section=section, case_type=case_type, subject=subject,
        title=field_values.get("title"), content_before=field_values.get("content_before"),
        content_after=field_values.get("content_after"), modify_reason=field_values.get("modify_reason"),
        why_modify=field_values.get("why_modify"), modify_note=field_values.get("modify_note"),
        content=field_values.get("content"), analysis=field_values.get("analysis"),
        why_good=field_values.get("why_good"), review_time=review_time,
        source_draft=source_draft, image_paths=image_paths,
    )

    try:
        if save_clicked:
            if editing:
                update_case(case_id, data, user["id"], raw.get("update_time"))
                st.success("草稿已保存")
            else:
                new_id = create_draft(data, user["id"])
                st.success(f"草稿已保存，编号 #{new_id}")
                st.session_state["cf_editing_id"] = new_id
        elif submit_clicked:
            if editing:
                update_case(case_id, data, user["id"], raw.get("update_time"))
                submit_for_review(case_id, user["id"])
                st.success("已提交审核")
            else:
                new_id = create_draft(data, user["id"])
                submit_for_review(new_id, user["id"])
                st.success(f"已提交审核，编号 #{new_id}")
    except (ValidationError, PermissionError, StateTransitionError,
            ConcurrentUpdateError, NotFoundError) as e:
        st.error(str(e))
