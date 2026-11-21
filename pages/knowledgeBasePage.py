# pages/knowledgeBasePage.py
"""知识库检索页（首页一级菜单）。

左侧：分组树筛选 + 关键词 + 颜色筛选
右侧：条目卡片列表，点开看正文 + 关联题目（可展开原文）
"""
import streamlit as st

from utils.auth_utils import require_permission
from utils.kb_utils import render_entry_detail, render_capsule, get_text_color
from services.knowledge_base_services import (
    get_all_groups,
    search_entries,
    get_entry,
)


def _build_group_options(groups):
    """构建带层级路径前缀的分组选项 [(id, "父 › 子"), ...]，按树序排列。"""
    children = {}
    for g in groups:
        children.setdefault(g["parent_id"], []).append(g)
    options = []

    def walk(pid, prefix):
        for g in children.get(pid, []):
            label = f"{prefix}{g['name']}" if prefix else g["name"]
            options.append((g["id"], label))
            walk(g["id"], label + " › ")

    walk(None, "")
    return options


def knowledge_base_page():
    require_permission("kb_view")

    st.title("知识库")

    # 处理外部跳转：直接定位某条目
    direct_entry_id = st.session_state.pop("kb_view_entry_id", None)

    col_filter, col_main = st.columns([1, 4])

    with col_filter:
        st.subheader("筛选")
        groups = get_all_groups()
        group_options = _build_group_options(groups)
        group_ids_for_select = [g[0] for g in group_options]
        label_map = {g[0]: g[1] for g in group_options}
        selected_group_ids = st.multiselect(
            "分组",
            options=group_ids_for_select,
            format_func=lambda gid: label_map.get(gid, str(gid)),
            key="kb_filter_groups",
            placeholder="不限分组",
        )

        st.divider()
        keyword = st.text_input("关键词", key="kb_filter_kw", placeholder="标题/正文")

    with col_main:
        # 直接定位条目详情
        if direct_entry_id:
            entry = get_entry(direct_entry_id)
            if entry:
                _render_single_entry_detail(entry)
                return
            else:
                st.warning("指定的条目不存在或已删除")

        # 检索结果
        entries = search_entries(
            keyword=keyword.strip() or None,
            group_ids=selected_group_ids or None,
        )

        st.caption(f"共 {len(entries)} 个条目")
        if not entries:
            st.info("暂无匹配的知识库条目")
            return

        for e in entries:
            _render_entry_card(e)


def _render_entry_card(entry):
    """条目卡片：色块标题 + 分组 + 关联数，点击展开详情。"""
    eid = entry["id"]
    title = entry["title"]
    color = entry.get("color") or "#409EFF"
    group_name = entry.get("group_name") or "未分组"
    qcount = entry.get("question_count", 0)

    head = f"{title}  ·  [{group_name}] 关联 {qcount} 题"
    with st.expander(head, expanded=False, key=f"kb_card_{eid}"):
        render_entry_detail(entry)


def _render_single_entry_detail(entry):
    """从外部跳转直接展示某条目详情。"""
    if st.button("返回列表"):
        st.rerun()
    render_entry_detail(entry)
