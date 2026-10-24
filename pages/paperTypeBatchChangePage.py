import streamlit as st

from services.paperTypeRule_services import get_rules, add_rule, delete_rule
from services.question_services import (
    count_questions_by_year_paper,
    get_paper_type_distribution,
    batch_change_paper_type,
)
from utils.auth_utils import require_role


def paper_type_batch_change():
    # ===== 权限校验 =====
    require_role("admin")

    if "show_change_dialog" not in st.session_state:
        st.session_state.show_change_dialog = False
        st.session_state.pending_mappings = None

    st.title("卷种批量变更")
    st.markdown("按 **年份 + 卷种** 批量变更题目卷种。仅作用于未进入回收站的题目，精确匹配年份与卷种。")

    # ===== 当前卷种分布预览 =====
    with st.expander("当前卷种分布（点击展开查看）", expanded=False):
        dist = get_paper_type_distribution()
        if dist:
            lines = ["| 年份 | 卷种 | 题目数 |", "|------|------|--------|"]
            for d in dist:
                lines.append(f"| {d['year']} | {d['paper_type']} | {d['count']} |")
            st.markdown("\n".join(lines))
        else:
            st.info("暂无题目")

    # ===== 变更规则管理 =====
    rules = get_rules()

    with st.container(border=True):
        st.subheader("变更规则管理")

        # 表头
        h1, h2, h3, h4 = st.columns([2, 2, 1.5, 1])
        h1.markdown("**源（年份+卷种）**")
        h2.markdown("**目标（年份+卷种）**")
        h3.markdown("**受影响题数**")
        h4.markdown("**操作**")
        st.divider()

        if not rules:
            st.info("暂无规则，请在下方添加。")
        else:
            for r in rules:
                cnt = count_questions_by_year_paper(r["from_year"], r["from_paper"])
                c1, c2, c3, c4 = st.columns([2, 2, 1.5, 1])
                c1.markdown(f"{r['from_year']} {r['from_paper']}")
                c2.markdown(f"{r['to_year']} {r['to_paper']}")
                c3.markdown(str(cnt))
                if c4.button("删除", key=f"del_rule_{r['id']}", use_container_width=True):
                    delete_rule(r["id"])
                    st.rerun()

        st.divider()

        # 添加规则表单
        with st.form("add_rule_form"):
            st.markdown("**添加新规则**")
            a1, a2, a3, a4 = st.columns([1, 2, 1, 2])
            fy = a1.number_input("源年份", min_value=2000, max_value=2100, value=2026, step=1, key="add_fy")
            fp = a2.text_input("源卷种", placeholder="如 东北卷", key="add_fp")
            ty = a3.number_input("目标年份", min_value=2000, max_value=2100, value=2026, step=1, key="add_ty")
            tp = a4.text_input("目标卷种", placeholder="如 黑吉辽蒙卷", key="add_tp")
            submitted = st.form_submit_button("添加规则")
            if submitted:
                if fp.strip() and tp.strip():
                    add_rule(int(fy), fp.strip(), int(ty), tp.strip())
                    st.rerun()
                else:
                    st.error("源卷种和目标卷种不能为空")

    # ===== 批量变更执行 =====
    st.subheader("批量变更执行")

    if not rules:
        st.warning("暂无变更规则，请先在上方添加。")
        return

    rule_ids = [r["id"] for r in rules]
    label_map = {
        r["id"]: f"{r['from_year']}{r['from_paper']} → {r['to_year']}{r['to_paper']}"
        for r in rules
    }
    cnt_map = {
        r["id"]: count_questions_by_year_paper(r["from_year"], r["from_paper"])
        for r in rules
    }
    id_to_rule = {r["id"]: r for r in rules}

    default_ids = [i for i in rule_ids if cnt_map[i] > 0]
    chosen_ids = st.multiselect(
        "选择要执行的变更规则",
        options=rule_ids,
        format_func=lambda i: label_map.get(i, str(i)),
        default=default_ids,
    )

    chosen_mappings = []
    total = 0
    for cid in chosen_ids:
        r = id_to_rule[cid]
        chosen_mappings.append((r["from_year"], r["from_paper"], r["to_year"], r["to_paper"]))
        total += cnt_map[cid]

    st.info(f"已选 {len(chosen_mappings)} 条规则，共影响 {total} 道题目。")

    # ===== 执行按钮 =====
    if st.button("执行批量变更", type="primary", disabled=len(chosen_mappings) == 0):
        st.session_state.show_change_dialog = True
        st.session_state.pending_mappings = chosen_mappings
        st.rerun()

    # ===== 确认对话框 =====
    if st.session_state.get("show_change_dialog") and st.session_state.get("pending_mappings"):
        change_confirm_dialog(st.session_state.pending_mappings)

    # ===== 执行结果展示 =====
    if st.session_state.get("change_result"):
        result = st.session_state.change_result
        st.subheader("变更结果")
        total_changed = sum(item["changed"] for item in result)
        st.success(f"批量变更完成，共变更 {total_changed} 道题目。")
        res_lines = [
            "| 源（年份+卷种） | 目标（年份+卷种） | 变更题数 |",
            "|----------------|------------------|----------|",
        ]
        for item in result:
            res_lines.append(
                f"| {item['from_year']}{item['from_paper']} | {item['to_year']}{item['to_paper']} | {item['changed']} |"
            )
        st.markdown("\n".join(res_lines))
        if st.button("清除结果", key="clear_result_btn"):
            st.session_state.change_result = None
            st.rerun()


# =========================
# 批量变更确认对话框
# =========================
@st.dialog("确认批量变更", width="small")
def change_confirm_dialog(mappings):
    st.warning("即将执行批量变更，此操作不可撤销，请仔细核对。")

    preview_lines = [
        "| 源（年份+卷种） | 目标（年份+卷种） |",
        "|----------------|------------------|",
    ]
    for (fy, fp, ty, tp) in mappings:
        preview_lines.append(f"| {fy}{fp} | {ty}{tp} |")
    st.markdown("\n".join(preview_lines))

    col1, col2 = st.columns(2)

    with col1:
        if st.button("确定执行", type="primary", key="confirm_change_btn", use_container_width=True):
            try:
                result = batch_change_paper_type(mappings)
                st.session_state.change_result = result
                st.session_state.show_change_dialog = False
                st.session_state.pending_mappings = None
                st.rerun()
            except Exception as e:
                st.error(f"变更失败：{str(e)}")

    with col2:
        if st.button("取消", type="secondary", key="cancel_change_btn", use_container_width=True):
            st.session_state.show_change_dialog = False
            st.session_state.pending_mappings = None
            st.rerun()
