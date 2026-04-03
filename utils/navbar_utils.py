import streamlit as st

# ==============================
# 页面间跳转（顶端导航栏）
# ==============================

def navbar(pageName):

    st.image("static/images/logo/V1.0.png", width='content')
    st.space()

    with st.expander("页面导航栏"):
        col_nav1, col_nav2 = st.columns(2)
        with col_nav1:
            if st.button("首页", key=f"btn_home_{pageName}", use_container_width=True, type="primary"):
                st.switch_page("main.py")
        with col_nav2:
            if st.button("管理", key=f"btn_task_{pageName}", use_container_width=True):
                st.switch_page("pages/managingPage.py")

def info_update():
    if st.session_state.get("update_qid"):
        st.info(f"上次成功提交/选择更新的试题 ID 是：{st.session_state['update_qid']}，如需添加备注可直接前往更新页。")
