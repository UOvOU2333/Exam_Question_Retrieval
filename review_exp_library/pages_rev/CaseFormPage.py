"""案例新建/编辑表单页（分类 ID 驱动）。"""

from datetime import date, datetime

import streamlit as st

from pages_rev.CaseDetailComponent import render_case_detail
from services_rev.AuthService import get_current_user
from services_rev.CaseService import (
    create_draft, update_case, submit_for_review, get_case_raw,
)
from services_rev.CatalogService import (
    list_books, list_sections, list_case_types, list_subjects, get_field_layout_by_id,
)
from services_rev.ImageService import save_image
from services_rev.MemberService import list_members
from services_rev.ReviewService import publish_direct
from utils_rev.dto import CaseDetail, CaseInput
from utils_rev.exceptions import (
    ValidationError, PermissionError, StateTransitionError,
    ConcurrentUpdateError, NotFoundError,
)
from utils_rev.permissions import is_admin, is_chief
from utils_rev.render_utils import render_markdown

# 用户主动标注语法：前缀 + 文字 + 后缀（渲染端统一转译）
_ANNOTATION_WRAPS = {
    "荧光黄": ("==", "=="),
    "荧光绿": ("==绿:", "=="),
    "荧光蓝": ("==蓝:", "=="),
    "红色字": ("【【红:", "】】"),
    "蓝色字": ("【【蓝:", "】】"),
}


def case_form_page(case_id=None, keep_status: bool = False):
    user = get_current_user()
    editing = case_id is not None
    raw = None
    if editing:
        raw = get_case_raw(case_id)
        if not raw:
            st.error("案例不存在")
            return
        if raw["status"] == "待总编审核" and not is_chief(user["role"]) and not keep_status:
            st.warning("该案例已提交审核，等待总编审核中，暂不可编辑。")
            return

    kid = case_id if case_id is not None else "new"
    chief = is_chief(user["role"])
    admin_direct = is_admin(user["role"])

    if keep_status:
        st.subheader(f"编辑案例 #{case_id}（保持状态）")
    else:
        st.subheader(f"编辑案例 #{case_id}" if editing else "新建案例")

    if raw and raw.get("reject_comment"):
        st.error(f"退回意见：{raw['reject_comment']}")

    # 分类选择固定在上方，编辑与预览各占一半
    col_b, col_s, col_t, col_sub = st.columns(4)
    with col_b:
        book_options = [(b.id, b.name) for b in list_books()]
        default_b = raw["book_id"] if raw else book_options[0][0]
        book_id = st.selectbox("书名", book_options,
                               index=[o[0] for o in book_options].index(default_b) if default_b in [o[0] for o in book_options] else 0,
                               format_func=lambda x: x[1], key=f"cf_{kid}_book")[0]
    with col_s:
        sec_options = [(s.id, s.name) for s in list_sections()]
        default_s = raw["section_id"] if raw else (sec_options[0][0] if sec_options else None)
        section_id = st.selectbox("问题与范例", sec_options,
                                  index=[o[0] for o in sec_options].index(default_s) if sec_options and default_s in [o[0] for o in sec_options] else 0,
                                  format_func=lambda x: x[1], key=f"cf_{kid}_section")[0]
    with col_t:
        ct_options = [(c.id, c.name) for c in list_case_types(section_id)]
        default_ct = raw["case_type_id"] if raw else (ct_options[0][0] if ct_options else None)
        case_type_id = st.selectbox("案例类型", ct_options,
                                    index=[o[0] for o in ct_options].index(default_ct) if ct_options and default_ct in [o[0] for o in ct_options] else 0,
                                    format_func=lambda x: x[1], key=f"cf_{kid}_case_type")[0]
    with col_sub:
        sub_options = [(s.id, s.name) for s in list_subjects()]
        default_sub = raw["subject_id"] if raw else (sub_options[0][0] if sub_options else None)
        subject_id = st.selectbox("模块", sub_options,
                                  index=[o[0] for o in sub_options].index(default_sub) if default_sub and default_sub in [o[0] for o in sub_options] else 0,
                                  format_func=lambda x: x[1], key=f"cf_{kid}_subject")[0]

    layout = get_field_layout_by_id(case_type_id)

    field_options = [(spec.name, spec.label + (" *" if spec.required else "")) for spec in layout]

    col_edit, col_preview = st.columns(2)

    with col_edit:
        with st.expander("插入图片到正文", expanded=False):
            _target = st.selectbox(
                "插入到哪个字段",
                field_options,
                format_func=lambda x: x[1],
                key=f"cf_{kid}_img_target",
            )
            _inline_img = st.file_uploader(
                "选择图片（png / jpg / jpeg / gif / webp / bmp）",
                type=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
                key=f"cf_{kid}_inline_img",
            )
            if _inline_img:
                _inline_rel = save_image(_inline_img)
                _md_clean = f"![图片说明]({_inline_rel})"
                st.code(_md_clean, language="markdown")
                if st.button("插入到正文", type="primary", key=f"cf_{kid}_img_insert_btn"):
                    _tkey = f"cf_{kid}_{_target[0]}"
                    _cur = st.session_state.get(_tkey, (raw.get(_target[0], "") if raw else ""))
                    st.session_state[_tkey] = (_cur or "") + f"\n\n{_md_clean}\n\n"
                    st.rerun()

        # 标注标记：只生成可复制文本，不读取/修改正文字段，避免与手动插入冲突
        with st.expander("荧光笔 / 变色标注", expanded=False):
            st.caption(
                "选择样式生成标记，复制后粘贴到正文对应位置；"
                "也可直接手写：==文字==、==绿:文字==、【【红:文字】】"
                "（颜色后的冒号全角/半角均可）"
            )
            _hl_text = st.text_input("标注文字", key=f"cf_{kid}_hl_text")
            _hl_style = st.selectbox(
                "标注样式",
                list(_ANNOTATION_WRAPS),
                key=f"cf_{kid}_hl_style",
            )
            _hl_prefix, _hl_suffix = _ANNOTATION_WRAPS[_hl_style]
            _hl_raw = (_hl_text or "").strip()
            if any(ch in _hl_raw for ch in "=【】\n"):
                st.warning("标注文字不能包含 = 【 】 或换行")
                _hl_raw = ""
            _hl_marked = f"{_hl_prefix}{_hl_raw or '文字'}{_hl_suffix}"
            st.code(_hl_marked, language="markdown")
            if _hl_raw:
                render_markdown(f"预览：{_hl_marked}")

        field_values = {}
        for spec in layout:
            default_val = raw.get(spec.name, "") if raw else ""
            field_values[spec.name] = st.text_area(
                spec.label + (" *" if spec.required else ""),
                value=default_val, height=120, key=f"cf_{kid}_{spec.name}",
            )

        default_review = raw["review_time"] if raw and raw["review_time"] else date.today()
        review_time = st.date_input("审稿时间 *", value=default_review, key=f"cf_{kid}_review_time")

        existing_images = raw.get("image_paths", []) if raw else []
        if existing_images:
            with st.expander("已有图片", expanded=False):
                from services_rev.ImageService import abs_path
                for rel in existing_images:
                    try:
                        st.image(abs_path(rel))
                    except Exception:
                        st.warning("图片加载失败")

        source_draft = st.text_input("来源稿件（可选）", value=raw.get("source_draft", "") if raw else "", key=f"cf_{kid}_source")

        members = list_members(include_deleted=False)
        mem_options = {m.id: m.display_name for m in members}
        mem_ids = [m.id for m in members]

        if editing:
            default_owners = raw.get("owner_ids") if raw else []
            if not default_owners:
                default_owners = [raw.get("created_by_id")] if raw else []
            owner_ids = st.multiselect(
                "负责人 *",
                options=mem_ids,
                default=[uid for uid in default_owners if uid in mem_ids],
                format_func=lambda x: mem_options.get(x, str(x)),
                disabled=not chief,
                key=f"cf_{kid}_owners",
            )
        else:
            # 管理员/总编新建时可指派负责人；普通编辑默认本人且不可改
            owner_ids = st.multiselect(
                "负责人 *",
                options=mem_ids,
                default=[user["id"]] if user["id"] in mem_ids else [],
                format_func=lambda x: mem_options.get(x, str(x)),
                disabled=not chief,
                key=f"cf_{kid}_owners",
            )

        editor_in_charge = "、".join(mem_options.get(uid, str(uid)) for uid in owner_ids)

        created_by_id = None
        if editing and chief:
            default_owner = raw.get("created_by_id") if raw else None
            owner_idx = mem_ids.index(default_owner) if default_owner in mem_ids else 0
            created_by_id = st.selectbox("创建者", mem_ids, index=owner_idx,
                                         format_func=lambda x: mem_options.get(x, str(x)),
                                         key=f"cf_{kid}_creator")

    with col_preview:
        st.subheader("实时预览")
        preview_fields = {
            spec.name: {"label": spec.label, "value": field_values.get(spec.name, "")}
            for spec in layout
        }
        preview_now = datetime.utcnow()
        preview_creator = user["display_name"]
        if raw and raw.get("created_by_id") in mem_options:
            preview_creator = mem_options[raw["created_by_id"]]
        render_case_detail(CaseDetail(
            id=case_id or 0,
            book_id=book_id, section_id=section_id,
            case_type_id=case_type_id, subject_id=subject_id,
            book=dict(book_options).get(book_id, ""),
            section=dict(sec_options).get(section_id, ""),
            case_type=dict(ct_options).get(case_type_id, ""),
            subject=dict(sub_options).get(subject_id, ""),
            fields=preview_fields,
            image_paths=list(existing_images),
            status=raw["status"] if raw else "草稿",
            reject_comment=raw.get("reject_comment") if raw else None,
            review_time=review_time,
            upload_time=raw["update_time"] if raw else preview_now,
            update_time=raw["update_time"] if raw else preview_now,
            review_at=None,
            creator_display_name=preview_creator,
            reviewer_display_name=None,
            editor_in_charge=editor_in_charge,
            owner_names=editor_in_charge,
            submitter_display_name=None,
        ))

    st.divider()

    if keep_status:
        save_clicked = st.button("保存", type="primary", use_container_width=True, key=f"cf_{kid}_save")
        submit_clicked = False
    else:
        # 管理员直接发布，其余角色提交总编审核
        col_save, col_submit = st.columns(2)
        with col_save:
            save_clicked = st.button("保存草稿", type="secondary", use_container_width=True, key=f"cf_{kid}_save")
        with col_submit:
            submit_label = "直接发布" if admin_direct else "提交审核"
            submit_clicked = st.button(submit_label, type="primary", use_container_width=True, key=f"cf_{kid}_submit")

    if not (save_clicked or submit_clicked):
        return

    image_paths = list(existing_images)

    data = CaseInput(
        book_id=book_id, section_id=section_id, case_type_id=case_type_id, subject_id=subject_id,
        title=field_values.get("title"), content_before=field_values.get("content_before"),
        content_after=field_values.get("content_after"), modify_reason=field_values.get("modify_reason"),
        why_modify=field_values.get("why_modify"), modify_note=field_values.get("modify_note"),
        content=field_values.get("content"), analysis=field_values.get("analysis"),
        why_good=field_values.get("why_good"), review_time=review_time,
        source_draft=source_draft, editor_in_charge=editor_in_charge,
        created_by_id=created_by_id,
        owner_ids=owner_ids,
        image_paths=image_paths,
    )

    try:
        if save_clicked:
            if editing:
                update_case(case_id, data, user["id"], raw.get("update_time"), keep_status=keep_status)
                st.success("草稿已保存")
            else:
                new_id = create_draft(data, user["id"])
                st.success(f"草稿已保存，编号 #{new_id}")
        elif submit_clicked:
            if editing:
                update_case(case_id, data, user["id"], raw.get("update_time"), keep_status=keep_status)
                if admin_direct:
                    publish_direct(case_id, user["id"])
                    st.success("已直接发布")
                else:
                    submit_for_review(case_id, user["id"])
                    st.success("已提交审核")
            else:
                new_id = create_draft(data, user["id"])
                if admin_direct:
                    publish_direct(new_id, user["id"])
                    st.success(f"已直接发布，编号 #{new_id}")
                else:
                    submit_for_review(new_id, user["id"])
                    st.success(f"已提交审核，编号 #{new_id}")
        if "my_editing_id" in st.session_state:
            st.session_state.pop("my_editing_id", None)
            st.rerun()
    except (ValidationError, PermissionError, StateTransitionError,
            ConcurrentUpdateError, NotFoundError) as e:
        st.error(str(e))