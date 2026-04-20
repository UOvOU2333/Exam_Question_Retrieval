# agentPage.py
import streamlit as st

def agent():
    """智能助手聊天界面"""
    
    # 标题与清空按钮放在同一行
    col_title, col_clear = st.columns([3, 1])
    with col_title:
        st.title("🤖 智能题库助手")
    with col_clear:
        if st.button("清空历史对话", type="primary"):
            st.session_state.agent_messages = []
            st.session_state.agent_intermediate_steps = []
            st.rerun()
    
    st.caption("你可以用自然语言向我提问，例如：“找一道关于全过程人民民主的题目”、“2024年浙江首考题有哪些”")
    
    # 获取当前用户信息（登录时已存入 session_state）
    if "user_id" not in st.session_state or "role" not in st.session_state:
        st.error("用户信息缺失，请重新登录。")
        return
    
    user_id = st.session_state["user_id"]
    role = st.session_state["role"]
    
    # 缓存 Agent 实例（避免每次交互都重新构建）
    @st.cache_resource(show_spinner=False)
    def get_agent(_user_id, _role):
        from chains.rag.agent import build_agent_for_user
        return build_agent_for_user(user_id=_user_id, role=_role)
    
    agent_executor = get_agent(user_id, role)
    
    # 初始化聊天历史 和 中间步骤记录
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = []
    if "agent_intermediate_steps" not in st.session_state:
        st.session_state.agent_intermediate_steps = []
    
    # 显示历史消息
    for msg in st.session_state.agent_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # 接受用户输入
    if prompt := st.chat_input("请输入你的问题或指令"):
        # 添加用户消息
        st.session_state.agent_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # 调用 Agent
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    # AgentExecutor.invoke 需要传入字典，key 为 "input"
                    response = agent_executor.invoke({"input": prompt})
                    answer = response.get("output", "抱歉，我无法处理这个请求。")
                    steps = response.get("intermediate_steps", [])
                    
                    # 记录中间步骤（用于折叠区显示）
                    step_texts = []
                    for action, observation in steps:
                        tool_name = action.tool
                        tool_input = action.tool_input
                        step_texts.append(f"调用工具: {tool_name}\n   输入: {tool_input}\n   输出: {observation}")
                    st.session_state.agent_intermediate_steps = step_texts
                    
                except Exception as e:
                    answer = f"发生错误：{str(e)}"
                    st.session_state.agent_intermediate_steps = [f"错误: {str(e)}"]
                
                st.markdown(answer)
                st.session_state.agent_messages.append({"role": "assistant", "content": answer})
        
        st.rerun()
    
    # 折叠区域：显示 Agent 执行步骤（放在聊天框下方）
    with st.expander("查看 Agent 执行步骤"):
        if st.session_state.agent_intermediate_steps:
            for step in st.session_state.agent_intermediate_steps:
                st.text(step)
        else:
            st.info("暂无执行步骤，发送消息后会显示。")