"""归档区与备份页。"""

import streamlit as st

from services_rev.ArchiveService import list_archived, restore, delete_case, backup_export, backup_import
from services_rev.AuthService import get_current_user, require_permission
from utils_rev.exceptions import StateTransitionError, NotFoundError, ValidationError


def archive_page():
    require_permission("archive")
    user = get_current_user()

    st.subheader("数据备份")
    col_exp, col_down, col_imp = st.columns(3)
    with col_exp:
        if st.button("生成备份（ZIP）", use_container_width=True):
            data = backup_export()
            with col_down:
                st.download_button(
                    "下载备份文件", data=data,
                    file_name=f"review_backup_{__import__('datetime').datetime.now():%Y%m%d_%H%M}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    type="primary"
                )
    with col_imp:
        with st.expander("从备份文件恢复"):
            uploaded = st.file_uploader(
                "选择备份 ZIP 文件", type=["zip"],
                key="restore_backup_zip",
            )
            if uploaded is not None:
                st.warning("恢复操作将向数据库新增案例数据，不会覆盖现有记录。")
                if st.button("确认恢复", type="primary", key="confirm_restore_backup"):
                    try:
                        result = backup_import(uploaded.getvalue(), user["id"])
                        st.success(
                            f"恢复完成：共 {result.total} 条，导入 {result.imported} 条，"
                            f"跳过 {result.skipped} 条，图片还原 {result.images_restored} 张。"
                        )
                        if result.skipped_details:
                            with st.expander(f"查看跳过详情（{len(result.skipped_details)}）"):
                                for d in result.skipped_details:
                                    st.text(d)
                    except ValidationError as e:
                        st.error(str(e))

    st.subheader("归档区")
    archived = list_archived()
    if not archived:
        st.info("暂无归档案例")
    for sm in archived:
        with st.container(border=True):
            st.markdown(f"**#{sm.id} {sm.title_summary or '（无标题）'}**")
            st.caption(f"{sm.book} › {sm.section} › {sm.case_type} › {sm.subject} ｜ 归档于 {sm.update_time:%Y-%m-%d}")
            col_r, col_d = st.columns(2)
            with col_r:
                if st.button("恢复", key=f"rs_{sm.id}"):
                    try:
                        restore(sm.id, user["id"])
                        st.success("已恢复")
                        st.rerun()
                    except (StateTransitionError, NotFoundError) as e:
                        st.error(str(e))
            with col_d:
                if st.button("彻底删除", key=f"dl_{sm.id}", type="secondary"):
                    try:
                        res = delete_case(sm.id, user["id"])
                        msg = f"已删除，图片成功 {len(res.deleted_images)} 失败 {len(res.failed_images)}"
                        st.success(msg)
                        st.rerun()
                    except NotFoundError as e:
                        st.error(str(e))


