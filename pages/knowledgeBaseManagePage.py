# pages/knowledgeBaseManagePage.py
"""知识库管理页（管理后台二级菜单）。

三个 Tab：
    分组管理  — 多层分组树增删改
    条目管理  — 知识库条目增删改 + 关联题目管理
    预设颜色  — 预设色板管理
"""
import streamlit as st

from utils.auth_utils import require_permission, check_permission
from utils.kb_utils import (
    color_picker_component,
    preset_color_manager_component,
    render_entry_detail,
)
from services.knowledge_base_services import (
    get_all_groups,
    create_group,
    update_group,
    soft_delete_group,
    restore_group,
    get_all_entries,
    create_entry,
    update_entry,
    soft_delete_entry,
    restore_entry,
    get_entry,
    get_entry_questions,
    add_question_to_entry,
    remove_question_from_entry,
)


def knowledge_base_manage():
    require_permission("kb_manage")

    st.title("知识库管理")

    tab_group, tab_entry, tab_color = st.tabs(["分组管理", "条目管理", "预设颜色"])

    with tab_group:
        _manage_groups()
    with tab_entry:
        _manage_entries()
    with tab_color:
        preset_color_manager_component()


# ===================== 分组管理 =====================

def _group_indent(groups, gid):
    """计算分组深度。"""
    depth = 0
    gmap = {g["id"]: g for g in groups}
    cur = gmap.get(gid)
    seen = set()
    while cur and cur["parent_id"] and cur["parent_id"] not in seen:
        seen.add(cur["id"])
        depth += 1
        cur = gmap.get(cur["parent_id"])
    return depth


def _build_group_tree(groups):
    """构建 {parent_id: [group,...]}，根分组的 parent_id 为 None。"""
    tree = {}
    for g in groups:
        tree.setdefault(g["parent_id"], []).append(g)
    return tree


def _render_group_node(g, tree, gmap):
    """递归渲染单个分组节点：一行信息 + 子分组 expander 嵌套。"""
    children = tree.get(g["id"], [])
    parent_name = gmap.get(g["parent_id"], {}).get("name", "—") if g["parent_id"] else "根"
    st.markdown(
        f"**{g['name']}** "
        f"<span style='color:#888;font-size:12px'>ID:{g['id']} 父:{parent_name}"
        f"{f' · 子分组 {len(children)}' if children else ''}</span>",
        unsafe_allow_html=True,
    )
    if children:
        with st.expander(
            f"展开 {g['name']} 的子分组（{len(children)}）",
            expanded=False,
            key=f"kb_group_expand_{g['id']}",
        ):
            for child in children:
                _render_group_node(child, tree, gmap)


def _manage_groups():
    groups = get_all_groups()
    gmap = {g["id"]: g for g in groups}
    tree = _build_group_tree(groups)

    col_list, col_op = st.columns([2, 1])

    with col_list:
        st.subheader("分组列表")
        if not groups:
            st.info("暂无分组")
        else:
            roots = tree.get(None, [])
            if not roots:
                st.warning("存在分组但无根分组（可能父分组已删除）")
            for g in roots:
                _render_group_node(g, tree, gmap)

    with col_op:
        st.subheader("新增分组")
        parent_options = [("根（无父分组）", None)] + [(g["name"], g["id"]) for g in groups]
        pidx = st.selectbox("父分组", range(len(parent_options)),
                            format_func=lambda i: parent_options[i][0],
                            key="kb_new_group_parent")
        new_name = st.text_input("分组名称", key="kb_new_group_name")
        if st.button("新增", key="kb_add_group_btn", type="primary"):
            if not new_name.strip():
                st.warning("请输入名称")
            elif create_group(new_name.strip(), parent_options[pidx][1],
                              st.session_state.get("user_id", 1),
                              operator_role=st.session_state.get("role")):
                st.rerun()
            else:
                st.error("新增失败")

        st.divider()
        st.subheader("编辑/删除分组")
        if groups:
            sel = st.selectbox("选择分组", groups,
                               format_func=lambda g: f"{g['name']} (ID:{g['id']})",
                               key="kb_edit_group_sel")
            new_title = st.text_input("新名称", value=sel["name"], key="kb_edit_group_name")
            new_parent = st.selectbox("新父分组", range(len(parent_options)),
                                      format_func=lambda i: parent_options[i][0],
                                      key="kb_edit_group_parent")
            col_save, col_del = st.columns(2)
            with col_save:
                if st.button("保存", key="kb_save_group_btn"):
                    if update_group(sel["id"], name=new_title.strip(),
                                    parent_id=parent_options[new_parent][1],
                                    updated_by=st.session_state.get("user_id", 1),
                                    operator_role=st.session_state.get("role")):
                        st.rerun()
                    else:
                        st.error("保存失败")
            with col_del:
                with st.expander("危险操作"):
                    if st.button("删除该分组", key="kb_del_group_btn", type="primary"):
                        if soft_delete_group(sel["id"], st.session_state.get("user_id", 1),
                                             operator_role=st.session_state.get("role")):
                            st.rerun()
                        else:
                            st.error("删除失败")
        else:
            st.caption("无分组可编辑")


# ===================== 条目管理 =====================

def _manage_entries():
    groups = get_all_groups()
    gmap = {g["id"]: g for g in groups}
    entries = get_all_entries()

    col_list, col_op = st.columns([2, 3])

    with col_list:
        st.subheader("条目列表")
        if not entries:
            st.info("暂无条目")
        else:
            for e in entries:
                gname = gmap.get(e["group_id"], {}).get("name", "未分组") if e["group_id"] else "未分组"
                color = e.get("color") or "#409EFF"
                st.markdown(
                    f"<span style='background:{color};color:#fff;padding:2px 8px;"
                    f"border-radius:4px;font-size:12px;'>{e['title']}</span>"
                    f" <span style='color:#888;font-size:12px'>[{gname}] ID:{e['id']}</span>",
                    unsafe_allow_html=True,
                )

    with col_op:
        st.subheader("新增条目")
        _entry_form(groups, gmap, existing=None)

        st.divider()
        st.subheader("编辑/删除条目")
        if entries:
            sel = st.selectbox("选择条目", entries,
                               format_func=lambda e: f"{e['title']} (ID:{e['id']})",
                               key="kb_edit_entry_sel")
            _entry_form(groups, gmap, existing=sel)
        else:
            st.caption("无条目可编辑")


def _entry_form(groups, gmap, existing):
    """条目新增/编辑表单。existing=None 为新增。"""
    is_edit = existing is not None
    prefix = "kb_edit" if is_edit else "kb_new"

    title = st.text_input("标题", value=existing["title"] if is_edit else "",
                          key=f"{prefix}_entry_title")
    content = st.text_area("正文（Markdown）", value=existing.get("content", "") if is_edit else "",
                           height=150, key=f"{prefix}_entry_content")

    group_options = [("未分组", None)] + [(g["name"], g["id"]) for g in groups]
    default_gidx = 0
    if is_edit and existing["group_id"]:
        for i, (_, gid) in enumerate(group_options):
            if gid == existing["group_id"]:
                default_gidx = i
                break
    gidx = st.selectbox("所属分组", range(len(group_options)),
                        format_func=lambda i: group_options[i][0],
                        index=default_gidx, key=f"{prefix}_entry_group")

    color = color_picker_component(
        default_color=existing.get("color", "#409EFF") if is_edit else "#409EFF",
        key_prefix=prefix,
    )

    if is_edit:
        col_save, col_del = st.columns([1, 1])
        with col_save:
            if st.button("保存修改", key=f"{prefix}_save_btn", type="primary"):
                if not title.strip():
                    st.warning("标题不能为空")
                elif update_entry(existing["id"], title=title.strip(), content=content,
                                  color=color, group_id=group_options[gidx][1],
                                  updated_by=st.session_state.get("user_id", 1),
                                  operator_role=st.session_state.get("role")):
                    st.rerun()
                else:
                    st.error("保存失败")
        with col_del:
            with st.expander("危险操作"):
                if st.button("删除该条目", key=f"{prefix}_del_btn", type="primary"):
                    if soft_delete_entry(existing["id"], st.session_state.get("user_id", 1),
                                         operator_role=st.session_state.get("role")):
                        st.rerun()
                    else:
                        st.error("删除失败")

        st.divider()
        _manage_entry_questions(existing["id"])
    else:
        if st.button("新增条目", key=f"{prefix}_add_btn", type="primary"):
            if not title.strip():
                st.warning("标题不能为空")
            elif create_entry(title.strip(), content, color, group_options[gidx][1],
                              st.session_state.get("user_id", 1),
                              operator_role=st.session_state.get("role")):
                st.rerun()
            else:
                st.error("新增失败")


def _manage_entry_questions(entry_id):
    """管理某条目关联的题目（增删）。"""
    st.markdown("**关联题目管理**")
    questions = get_entry_questions(entry_id)
    if questions:
        st.caption(f"当前关联 {len(questions)} 道题目")
        for q in questions:
            tip = f"#{q['questionID']}"
            if q["year"]:
                tip += f" {q['year']}"
            if q["paper_type"]:
                tip += f" {q['paper_type']}"
            if q["question_no"]:
                tip += f" T{q['question_no']}"
            col_t, col_d = st.columns([4, 1])
            with col_t:
                st.caption(tip)
            with col_d:
                if st.button("移除", key=f"kb_rm_q_{entry_id}_{q['questionID']}"):
                    if remove_question_from_entry(entry_id, q["questionID"],
                                                  operator_role=st.session_state.get("role")):
                        st.rerun()
    else:
        st.caption("暂无关联题目")

    st.text_input("添加题目ID（多个用逗号分隔）", key=f"kb_add_qids_{entry_id}")
    if st.button("添加关联", key=f"kb_add_q_btn_{entry_id}"):
        raw = st.session_state.get(f"kb_add_qids_{entry_id}", "")
        ids = [s.strip() for s in raw.split(",") if s.strip()]
        ok = 0
        for s in ids:
            try:
                qid = int(s)
                if add_question_to_entry(entry_id, qid, st.session_state.get("user_id", 1),
                                         operator_role=st.session_state.get("role")):
                    ok += 1
            except ValueError:
                continue
        if ok:
            st.success(f"已添加 {ok} 个关联")
            st.rerun()
        else:
            st.warning("未添加任何关联（请检查题目ID）")
