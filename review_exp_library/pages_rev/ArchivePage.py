"""归档区与备份页。"""

import streamlit as st

from services_rev.ArchiveService import list_archived, restore, delete_case, backup_export
from services_rev.AuthService import get_current_user, require_permission
from utils_rev.exceptions import StateTransitionError, NotFoundError


def archive_page():
    require_permission("archive")
    user = get_current_user()
    st.subheader("归档区与数据备份")

    st.markdown("### 归档案例")
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

    st.markdown("### 数据备份")
    if st.button("生成备份（ZIP）"):
        data = backup_export()
        st.download_button(
            "下载备份文件", data=data,
            file_name=f"review_backup_{__import__('datetime').datetime.now():%Y%m%d_%H%M}.zip",
            mime="application/zip",
        )
