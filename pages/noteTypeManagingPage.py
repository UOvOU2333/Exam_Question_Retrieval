import streamlit as st
from utils.note_utils import note_type_selector_component, question_notes_component


def note_type_management():
    st.set_page_config(page_title="备注类型管理", layout="wide")
    st.title("备注管理系统")
    
    # 创建标签页展示不同版本
    tab1, tab2 = st.tabs(["备注类型管理", "备注管理"])
    
    with tab1:
        note_type_selector_component()
    
    with tab2:
        question_notes_component()
    
        with st.expander("查看Session State（调试信息）"):
            st.json({
                "selected_type_id": st.session_state.get('selected_type_id'),
                "selected_type_name": st.session_state.get('selected_type_name'),
                "selected_type_id_compact": st.session_state.get('selected_type_id_compact')
            })
