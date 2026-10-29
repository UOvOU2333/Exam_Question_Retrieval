import streamlit as st

# ==============================
# 页面间跳转（顶端导航栏）
# ==============================

@st.cache_resource
def get_logo(logo_path="static/images/logo/V2.png"):
    from PIL import Image
    return Image.open(logo_path)

def navbar(pageName):
    if pageName == "review":
        try:
            st.image(get_logo("static/images/logo/sjV1.png"))
        except Exception as e:
            st.warning("Logo 加载中 ...")
        st.write("")
    else:
        try:
            st.image(get_logo("static/images/logo/V2.png"))
        except Exception as e:
            st.warning("Logo 加载中 ...")
        st.write("")

    with st.expander("页面导航栏"):
        if pageName == "review":
            if st.button("返回政治题库", key=f"btn_home_{pageName}", use_container_width=True, type="primary"):
                st.switch_page("main.py")
        else:
            col_nav1, col_nav2 = st.columns(2)
            with col_nav1:
                if st.button("首页", key=f"btn_home_{pageName}", use_container_width=True, type="primary"):
                    st.switch_page("main.py")
            with col_nav2:
                if st.button("管理", key=f"btn_task_{pageName}", use_container_width=True):
                    st.switch_page("pages/managingPage.py")
            if st.button("审稿经验库", key=f"btn_rev_{pageName}", use_container_width=True):
                st.switch_page("pages/review.py")


def info_update():
    if st.session_state.get("update_qid"):
        st.info(f"上次成功提交/选择更新的试题 ID 是：{st.session_state['update_qid']}，如需添加备注可直接前往更新页。")
