# utils/kb_utils.py
"""知识库 UI 组件：胶囊标签、颜色选择器、条目详情、关联选择器。

胶囊与亮度自适应复刻自 TaskScheduler/widgets/capsule.py。
"""
import streamlit as st

from utils.render_utils import render_markdown
from utils.auth_utils import check_permission
from services.knowledge_base_services import (
    get_all_preset_colors,
    add_preset_color,
    delete_preset_color,
    get_question_entries,
    get_all_entries,
    get_all_groups,
    get_entry_questions,
    set_question_entries,
)


# ===================== 胶囊组件 =====================

def get_text_color(color: str):
    """YIQ 亮度公式自动选黑白文字色。"""
    color = (color or "").lstrip("#")
    if len(color) == 6:
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return "#000000" if luminance > 186 else "#FFFFFF"
    return "#FFFFFF"


def render_capsule(label, bg_color):
    """返回单个胶囊 HTML 字符串。"""
    text_color = get_text_color(bg_color)
    return (
        f"<span style='background:{bg_color};color:{text_color};"
        "padding:4px 12px;border-radius:999px;font-size:12px;"
        "font-weight:500;margin-right:8px;margin-bottom:4px;display:inline-block;'>"
        f"{label}</span>"
    )


def render_capsules_html(items):
    """items: [{'title':..,'color':..},...] 返回拼接 HTML。"""
    if not items:
        return ""
    return "".join(render_capsule(it["title"], it.get("color") or "#409EFF") for it in items)


# ===================== 颜色选择器 =====================

def color_picker_component(default_color="#409EFF", key_prefix="kb"):
    """颜色选择：预设下拉 + st.color_picker 自定义，返回选中 hex。

    选预设时直接采用预设值（不渲染 picker，避免固定 key 覆盖预设选择）；
    选“自定义”时才用 color_picker。
    """
    colors = get_all_preset_colors()
    col_pre, col_pick, col_preview = st.columns([2, 1, 1])

    with col_pre:
        preset_names = [c["color_name"] for c in colors] if colors else []
        options = ["（自定义）"] + preset_names
        chosen = st.selectbox("预设颜色", options, index=0, key=f"{key_prefix}_preset_sel")

    if chosen != "（自定义）":
        selected = next(c["color_value"] for c in colors if c["color_name"] == chosen)
        with col_pick:
            st.caption(f"预设色值 `{selected}`")
    else:
        with col_pick:
            selected = st.color_picker(
                "自定义",
                value=default_color,
                key=f"{key_prefix}_color_pick",
            )

    with col_preview:
        st.markdown("#### 色块预览")
        st.markdown(
            f"<div style='width:100%;height:32px;background:{selected};"
            "border-radius:6px;border:1px solid #ccc;'></div>",
            unsafe_allow_html=True,
        )

    return selected


def preset_color_manager_component():
    """预设颜色管理（新增/删除），用于管理页。"""
    st.subheader("预设颜色管理")
    colors = get_all_preset_colors()

    if colors:
        for c in colors:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                st.markdown(
                    f"<div style='width:36px;height:36px;background:{c['color_value']};"
                    "border-radius:8px;border:1px solid #ccc;'></div>",
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    f"**{c['color_name']}** &nbsp; <span style='color:gray;font-size:12px'>{c['color_value']}</span>",
                    unsafe_allow_html=True,
                )
            with col3:
                if st.button("删除", key=f"kb_del_color_{c['id']}"):
                    if delete_preset_color(c["id"], operator_role=st.session_state.get("role")):
                        st.rerun()
                    else:
                        st.error("删除失败")
    else:
        st.info("暂无预设颜色")

    st.divider()
    with st.expander("新增预设颜色"):
        col_n, col_v = st.columns(2)
        with col_n:
            name = st.text_input("颜色名称", key="kb_new_color_name")
        with col_v:
            value = st.color_picker("颜色值", "#409EFF", key="kb_new_color_value")
        if st.button("保存", key="kb_save_color"):
            if not name.strip():
                st.warning("请输入名称")
            elif add_preset_color(name.strip(), value, operator_role=st.session_state.get("role")):
                st.rerun()
            else:
                st.error("保存失败（可能重名）")


# ===================== 题目关联胶囊展示 =====================

def display_kb_capsules(question_id):
    """在题目详情里展示关联的知识库条目胶囊（点击跳检索页详情）。"""
    entries = get_question_entries(question_id)
    if not entries:
        return
    st.markdown("**知识库标签**")
    capsules = render_capsules_html(entries)
    st.markdown(capsules, unsafe_allow_html=True)
    # 跳转按钮：选中条目后跳到知识库检索页详情
    if check_permission("kb_view"):
        titles = [e["title"] for e in entries]
        sel = st.selectbox(
            "查看条目详情",
            ["（不跳转）"] + titles,
            index=0,
            key=f"kb_capsule_jump_{question_id}",
        )
        if sel != "（不跳转）":
            entry = next(e for e in entries if e["title"] == sel)
            st.session_state["kb_view_entry_id"] = entry["id"]
            st.session_state["nav"] = "知识库"
            st.switch_page("main.py")


# ===================== 更新页关联多选 =====================

def kb_entry_selector(question_id):
    """在试题更新页展示并编辑该题关联的知识库条目（逐条色块+勾选）。"""
    if not check_permission("kb_manage"):
        return
    st.subheader("关联知识库条目")
    all_entries = get_all_entries()
    if not all_entries:
        st.info("暂无知识库条目，请先在管理页创建")
        return

    current = get_question_entries(question_id)
    current_ids = {e["id"] for e in current}
    groups = {g["id"]: g["name"] for g in get_all_groups()}

    # 按分组归类展示，每行多列色块胶囊（带颜色）+ 勾选框
    by_group = {}
    for e in all_entries:
        by_group.setdefault(e["group_id"], []).append(e)

    COLS = 3
    selected_ids = set()
    for gid, entries in by_group.items():
        gname = groups.get(gid, "未分组")
        st.markdown(f"**{gname}**")
        for i in range(0, len(entries), COLS):
            row = entries[i:i + COLS]
            cols = st.columns(COLS)
            for j, e in enumerate(row):
                with cols[j]:
                    color = e.get("color") or "#409EFF"
                    st.markdown(render_capsule(e["title"], color), unsafe_allow_html=True)
                    if st.checkbox(
                        "关联",
                        value=(e["id"] in current_ids),
                        key=f"kb_chk_{question_id}_{e['id']}",
                    ):
                        selected_ids.add(e["id"])
        st.markdown("")

    if st.button("保存关联", key=f"kb_save_assoc_{question_id}", type="primary"):
        if set_question_entries(
            question_id,
            list(selected_ids),
            st.session_state.get("user_id", 1),
            operator_role=st.session_state.get("role"),
        ):
            st.success("关联已保存")
            st.rerun()
        else:
            st.error("保存失败")


# ===================== 条目详情渲染 =====================

def render_entry_detail(entry):
    """渲染单个知识库条目详情：标题色块 + 正文 + 关联题目列表。"""
    eid = entry["id"]
    title = entry["title"]
    color = entry.get("color") or "#409EFF"
    content = entry.get("content") or ""

    # 标题 + 色块
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>"
        f"<span style='background:{color};color:{get_text_color(color)};"
        "padding:6px 16px;border-radius:8px;font-size:18px;font-weight:600;'>"
        f"{title}</span></div>",
        unsafe_allow_html=True,
    )

    # 正文
    if content.strip():
        st.markdown("**条目内容**")
        render_markdown(content)
    else:
        st.caption("（该条目无正文内容）")

    # 关联题目
    st.markdown("**关联题目**")
    questions = get_entry_questions(eid)
    if not questions:
        st.info("暂无关联题目")
        return

    st.caption(f"共 {len(questions)} 道关联题目")
    for q in questions:
        _render_linked_question(q)


def _render_linked_question(q):
    """渲染一道关联题目（可展开看原文）。"""
    qid = q["questionID"]
    year = q["year"]
    paper_type = q["paper_type"]
    qno = q["question_no"]
    qtype = q["question_type"]

    tip = []
    if year:
        tip.append(f"{year}")
    if paper_type:
        tip.append(paper_type)
    if qno:
        tip.append(f"T{qno}")
    if qtype:
        tip.append(qtype)
    head = f"题目 #{qid}" + (f"（{' | '.join(tip)}）" if tip else "")

    with st.expander(head, expanded=False, key=f"kb_linked_q_{qid}"):
        if q.get("isInRecycleBin"):
            st.warning("该题目已在回收站")
        render_markdown(q["content"], "【题干】")
        if q.get("answer"):
            render_markdown(q["answer"], "【答案】")
        if q.get("analysis") and check_permission("view_analysis"):
            render_markdown(q["analysis"], "【解析】")
        if check_permission("update"):
            if st.button("更新此题", key=f"kb_link_update_{qid}"):
                st.session_state["update_qid"] = qid
                st.switch_page("pages/managingPage.py")
