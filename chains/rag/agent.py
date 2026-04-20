# chains/rag/agent.py

from functools import partial
from langchain_openai import ChatOpenAI
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool

from tools.question_tools import (
    search_questions_tool,
    get_question_tool,
    # create_question_tool,
    # update_question_tool,
    # delete_question_tool,
    search_question_by_note_tool,
)
from tools.note_tools import (
    # create_note_type_tool,
    # update_note_type_tool,
    # delete_note_type_tool,
    # restore_note_type_tool,
    # permanently_delete_note_type_tool,
    get_note_types_tool,
    get_question_notes_tool,
    # create_question_note_tool,
    # delete_question_note_tool,
)
from tools.rag_tool import rag_search_tool

from chains.config import OPENAI_API_KEY, OPENAI_API_BASE
import os
from dotenv import load_dotenv
from datetime import datetime

from chains.rag.prompt import SYSTEM_PROMPT

def build_agent_for_user(user_id: int, role: str):
    load_dotenv()
    
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
        temperature=0,
        max_retries=3,
        streaming=False,
        request_timeout=120
    )
    
    # 原始工具列表（这些工具已经是 LangChain 的 Tool 对象）
    raw_tools = [
        rag_search_tool,
        search_questions_tool,
        get_question_tool,
        # create_question_tool,
        # update_question_tool,
        # delete_question_tool,
        search_question_by_note_tool,
        # create_note_type_tool,
        # update_note_type_tool,
        # delete_note_type_tool,
        # restore_note_type_tool,
        # permanently_delete_note_type_tool,
        get_note_types_tool,
        get_question_notes_tool,
        # create_question_note_tool,
        # delete_question_note_tool,
    ]
    
    bound_tools = []
    for tool_obj in raw_tools:
        # 提取原始的可调用函数
        if hasattr(tool_obj, 'func') and callable(tool_obj.func):
            original_func = tool_obj.func
        else:
            original_func = tool_obj
        
        # 绑定 user_id 和 role 参数
        bound_func = partial(original_func, user_id=user_id, role=role)
        
        # 重新包装成 LangChain Tool 对象
        new_tool = Tool(
            name=tool_obj.name if hasattr(tool_obj, 'name') else original_func.__name__,
            func=bound_func,
            description=tool_obj.description if hasattr(tool_obj, 'description') else (original_func.__doc__ or "")
        )
        bound_tools.append(new_tool)
    
    # 注入当前日期
    current_date = datetime.now().date().isoformat()
    system_prompt_with_date = SYSTEM_PROMPT.replace("{current_date}", current_date)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt_with_date),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    agent = create_tool_calling_agent(
        llm=llm,
        tools=bound_tools,
        prompt=prompt
    )
    
    executor = AgentExecutor(
        agent=agent,
        tools=bound_tools,
        verbose=True,
        max_iterations=10,
        return_intermediate_steps=True
    )
    return executor