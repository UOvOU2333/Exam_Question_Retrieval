import streamlit as st

from chains.deepseek_agent import run_agent, get_api_key
from services.user_services import is_ai_enabled


def _welcome(username: str) -> str:
    return (
        f"你好，{username}！我是高中政治学科题库智能助手 📚\n\n"
        "我可以帮你在高中政治题库中查找题目，比如：\n\n"
        '- **按知识点检索**：如"全过程人民民主""供给侧结构性改革""矛盾的普遍性"等\n'
        '- **按卷种/年份检索**：如"2024年浙江首考""2023年全国甲卷"\n'
        "- **按题型筛选**：选择题、非选择题、判断题\n"
        "- **按知识模块检索**：必修一至必修四、选必一至选必三\n"
        "- **查看某道题**的完整答案与解析\n\n"
        "> ⚠️ 本系统只包含高中政治题目，不涉及历史、地理、物理、化学等其他学科。\n\n"
        "你想查哪方面的题目？可以直接告诉我知识点、年份、卷种或题号～"
    )


def ai_chat():
    if not st.session_state.get("logged_in"):
        st.warning("请先登录")
        return

    col_title, col_clear = st.columns([4, 1])
    with col_title:
        st.title("🤖 智能题库助手")
    with col_clear:
        if st.button("清空对话", type="primary", use_container_width=True):
            st.session_state.ai_messages = []
            st.session_state.ai_steps = []
            st.rerun()

    st.caption("用自然语言提问，AI 会自动设计检索关键词并在题库中查找后回答。"
               "例如：“找一道关于全过程人民民主的选择题”、“2024年浙江首考有哪些非选择题”")

    if not is_ai_enabled(st.session_state.get("user_id")):
        st.error("您没有使用 AI 助手的权限，请联系管理员将您加入 AI 使用白名单。")
        return

    api_key = get_api_key()
    if not api_key:
        st.error("AI 服务尚未配置，请联系管理员在服务端设置 DeepSeek API Key。")
        return

    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []
    if "ai_steps" not in st.session_state:
        st.session_state.ai_steps = []

    if not st.session_state.ai_messages:
        username = st.session_state.get("username", "同学")
        st.session_state.ai_messages.append(
            {"role": "assistant", "content": _welcome(username)}
        )

    for msg in st.session_state.ai_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("请输入你的问题"):
        st.session_state.ai_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("思考中…"):
                answer, steps = run_agent(
                    history=st.session_state.ai_messages[:-1],
                    user_input=prompt,
                    api_key=api_key,
                    user_role=st.session_state.get("role"),
                )
            st.markdown(answer)
        st.session_state.ai_messages.append({"role": "assistant", "content": answer})
        st.session_state.ai_steps = steps
        st.rerun()

    with st.expander("🔍 查看检索过程", expanded=False):
        steps = st.session_state.ai_steps
        if not steps:
            st.caption("发送消息后，这里会展示 AI 调用的检索工具与结果。")
        else:
            for i, step in enumerate(steps, 1):
                if "error" in step:
                    st.error(f"步骤 {i} 出错：{step['error']}")
                    continue
                st.markdown(f"**步骤 {i}：调用 `{step['tool']}`**")
                st.json(step["args"])
                with st.expander("检索结果", expanded=False):
                    st.markdown(step["result"])
