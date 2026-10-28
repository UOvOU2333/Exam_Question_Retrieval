"""导航栏组件，含返回题库站内路由按钮。"""

import streamlit as st

from utils_rev.site_router import go_to_main_site


def navbar():
    with st.expander("站点导航", expanded=False):
        if st.button("返回题库主站"):
            go_to_main_site()
        st.write("提示：本库独立登录，账号与题库不互通。")
