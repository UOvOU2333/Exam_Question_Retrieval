"""案例新建/编辑表单页（分类 ID 驱动）。"""

from datetime import date

import streamlit as st

from services_rev.AuthService import get_current_user
from services_rev.CaseService import (
    create_draft, update_case, submit_for_review, get_case_raw,
)
from services_rev.CatalogService import (
    list_books, list_sections, list_case_types, list_subjects, get_field_layout_by_id,
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

    col_b, col_s, col_t, col_sub = st.columns(4)
    with col_b:
        book_options = [(b.id, b.name) for b in list_books()]
        default_b = raw["book_id"] if raw else book_options[0][0]
        book_id = st.selectbox("书名", book_options,
                               index=[o[0] for o in book_options].index(default_b) if default_b in [o[0] for o in book_options] else 0,
                               format_func=lambda x: x[1], key="cf_book")[0]
    with col_s:
        sec_options = [(s.id, s.name) for s in list_sections()]
        default_s = raw["section_id"] if raw else (sec_options[0][0] if sec_options else None)
        section_id = st.selectbox("问题与范例", sec_options,
                                  index=[o[0] for o in sec_options].index(default_s) if sec_options and default_s in [o[0] for o in sec_options] else 0,
                                  format_func=lambda x: x[1], key="cf_section")[0]
    with col_t:
        ct_options = [(c.id, c.name) for c in list_case_types(section_id)]
        default_ct = raw["case_type_id"] if raw else (ct_options[0][0] if ct_options else None)
        case_type_id = st.selectbox("案例类型", ct_options,
                                    index=[o[0] for o in ct_options].index(default_ct) if ct_options and default_ct in [o[0] for o in ct_options] else 0,
                                    format_func=lambda x: x[1], key="cf_case_type")[0]
    with col_sub:
        sub_options = [(s.id, s.name) for s in list_subjects()]
        default_sub = raw["subject_id"] if raw else (sub_options[0][0] if sub_options else None)
        subject_id = st.selectbox("模块", sub_options,
                                  index=[o[0] for o in sub_options].index(default_sub) if sub_options and default_sub in [o[0] for o in sub_options] else 0,
                                  format_func=lambda x: x[1], key="cf_subject")[0]

    layout = get_field_layout_by_id(case_type_id)
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
        book_id=book_id, section_id=section_id, case_type_id=case_type_id, subject_id=subject_id,
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
