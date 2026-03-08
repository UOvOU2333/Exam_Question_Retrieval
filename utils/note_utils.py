import streamlit as st
import pandas as pd
from datetime import datetime

from services.note_services import *


def note_type_selector_component():
    """
    笔记类型选择器组件
    包含类型列表展示、选择和新增功能，以及软删除恢复和实际删除
    """
    # 初始化session_state
    if 'selected_type_id' not in st.session_state:
        st.session_state.selected_type_id = None
    if 'selected_type_name' not in st.session_state:
        st.session_state.selected_type_name = None
    if 'refresh_types' not in st.session_state:
        st.session_state.refresh_types = False
    if 'show_deleted' not in st.session_state:
        st.session_state.show_deleted = False  # 是否显示已删除的类型
    
    # 根据开关状态获取类型
    all_types = get_all_note_types(include_deleted=st.session_state.show_deleted)
    
    # 创建两列布局：左侧列表，右侧新增表单
    col1, col2 = st.columns([2, 1])
    col_cho1, col_cho2 = st.columns([2, 1])
    
    with col1:
        # 添加显示模式切换开关
        col_header, show_deleted_col  = st.columns([1, 1])
        with show_deleted_col:
            show_deleted = st.toggle(
                "显示已删除",
                value=st.session_state.show_deleted,
                help="开启后显示所有类型（包括已软删除的）"
            )
            if show_deleted != st.session_state.show_deleted:
                st.session_state.show_deleted = show_deleted
                st.rerun()
        with col_header:
            st.subheader("已有类型")
        
        if not all_types:
            st.info("暂无笔记类型，请在右侧添加")
        else:
            # 转换为DataFrame展示
            df = pd.DataFrame(all_types)
            
            # 格式化时间显示
            if 'created_at' in df.columns:
                df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            if 'updated_at' in df.columns:
                df['updated_at'] = pd.to_datetime(df['updated_at']).dt.strftime('%Y-%m-%d %H:%M')
            
            # 添加状态列
            df['状态'] = df['is_deleted'].apply(lambda x: '已删除' if x else '正常')
            
            # 显示数据表
            st.dataframe(
                df[['type_name', '状态', 'created_at', 'updated_at']],
                column_config={
                    "type_name": "类型名称",
                    "状态": "状态",
                    "created_at": "创建时间",
                    "updated_at": "更新时间"
                },
                width='stretch',
                hide_index=True
            )
    with col_cho1:
        if all_types:
            st.subheader("选择类型")
            
            # 只显示正常类型供选择（已删除的不能选）
            active_types = [t for t in all_types if not t.get('is_deleted', 0)]
            
            if active_types:
                # 使用列布局展示选择按钮
                cols = st.columns(3)
                for idx, type_item in enumerate(active_types):
                    col_idx = idx % 3
                    with cols[col_idx]:
                        # 判断是否为当前选中项
                        is_selected = st.session_state.selected_type_id == type_item['id']
                        button_type = "primary" if is_selected else "secondary"
                        
                        if st.button(
                            f"{type_item['type_name']}",
                            key=f"select_type_{type_item['id']}",
                            type=button_type,
                            use_container_width=True
                        ):
                            st.session_state.selected_type_id = type_item['id']
                            st.session_state.selected_type_name = type_item['type_name']
                            st.rerun()
            else:
                st.info("没有可用的正常类型")
    
    with col2:
        st.subheader("新增类型")
        
        with st.form("add_type_form", clear_on_submit=True):
            new_type_name = st.text_input(
                "类型名称",
                placeholder="例如: 知识模块",
                key="new_type_name_input"
            )
            
            if "user_id" in st.session_state:
                current_user_id = st.session_state.get("user_id")
            else:
                st.error("请先登录以获取用户ID")
                current_user_id = None

            submitted = st.form_submit_button(
                "添加类型",
                use_container_width=True,
                type="primary"
            )
            
            if submitted:
                if new_type_name:
                    with st.spinner("正在添加..."):
                        new_id = create_note_type(new_type_name, current_user_id)
                        if new_id:
                            st.success(f"添加成功！ID: {new_id}")
                            st.session_state.refresh_types = not st.session_state.refresh_types
                            st.rerun()
                        else:
                            st.error("添加失败，类型名称可能已存在")
                else:
                    st.warning("请输入类型名称")
        
        # 已删除类型恢复区域
        deleted_types = [t for t in all_types if t.get('is_deleted', 0)]
        if deleted_types and st.session_state.show_deleted:
            st.subheader("恢复已删除")
            
            for type_item in deleted_types[:3]:  # 最多显示3个，避免太长
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.caption(f"{type_item['type_name']} (ID: {type_item['id']})")
                with col_b:
                    if st.button("恢复", key=f"restore_{type_item['id']}", use_container_width=True):
                        if "user_id" in st.session_state:
                            if restore_note_type(type_item['id'], st.session_state.user_id):
                                st.success(f"已恢复: {type_item['type_name']}")
                                st.session_state.refresh_types = not st.session_state.refresh_types
                                st.rerun()
                            else:
                                st.error("恢复失败")
                        else:
                            st.error("请先登录")
            
            if len(deleted_types) > 3:
                st.caption(f"... 还有 {len(deleted_types) - 3} 个已删除类型")
    
    with col_cho2:
        st.subheader("快速操作")
        
        if st.session_state.selected_type_id:
            # 获取当前选中类型的详细信息
            selected_type = next(
                (t for t in all_types if t['id'] == st.session_state.selected_type_id), 
                None
            )
            
            if selected_type and not selected_type.get('is_deleted', 0):
                # 更新表单
                with st.expander("编辑选中类型"):
                    with st.form("update_type_form"):
                        new_name = st.text_input(
                            "新名称",
                            value=st.session_state.selected_type_name
                        )
                        if "user_id" in st.session_state:
                            updater_id = st.session_state.get("user_id")
                        else:
                            st.error("请先登录以获取用户ID")
                            updater_id = None

                        if st.form_submit_button("更新", use_container_width=True, type="primary"):
                            if update_note_type(
                                st.session_state.selected_type_id,
                                name=new_name,
                                updated_by=updater_id
                            ):
                                st.success("更新成功")
                                st.rerun()
                            else:
                                st.error("更新失败")
                
                # 操作按钮组
                col_a, col_b = st.columns(2)
                with col_a:
                    # 软删除按钮
                    if st.button(
                        "软删除",
                        type="secondary",
                        use_container_width=True,
                        key="soft_delete_btn",
                        help="将类型标记为已删除（可恢复）"
                    ):
                        if "user_id" in st.session_state:
                            if soft_delete_note_type(
                                st.session_state.selected_type_id, 
                                st.session_state.user_id
                            ):
                                st.success("删除成功")
                                st.session_state.selected_type_id = None
                                st.session_state.selected_type_name = None
                                st.rerun()
                            else:
                                st.error("删除失败，可能已被删除")
                        else:
                            st.error("请先登录")
                
                with col_b:
                    # 永久删除按钮（需要确认）
                    if st.button(
                        "永久删除",
                        type="secondary",
                        use_container_width=True,
                        key="permanent_delete_btn",
                        help="彻底从数据库删除，不可恢复！"
                    ):
                        st.session_state.confirm_permanent_delete = True
                
                # 永久删除确认对话框
                if st.session_state.get('confirm_permanent_delete', False):
                    st.warning("**危险操作**：永久删除将彻底移除这条记录，不可恢复！")
                    col_confirm1, col_confirm2 = st.columns(2)
                    with col_confirm1:
                        if st.button("确认删除", type="primary", use_container_width=True):
                            if permanently_delete_note_type(st.session_state.selected_type_id):
                                st.success("已永久删除")
                                st.session_state.selected_type_id = None
                                st.session_state.selected_type_name = None
                                st.session_state.confirm_permanent_delete = False
                                st.rerun()
                            else:
                                st.error("删除失败")
                    with col_confirm2:
                        if st.button("取消", use_container_width=True):
                            st.session_state.confirm_permanent_delete = False
                            st.rerun()
            
            elif selected_type and selected_type.get('is_deleted', 0):
                # 如果是已删除的类型，显示恢复选项
                st.info("当前选中的是已删除的类型")
                
                if st.button(
                    "恢复此类型",
                    type="primary",
                    use_container_width=True,
                    key="restore_selected_btn"
                ):
                    if "user_id" in st.session_state:
                        if restore_note_type(
                            st.session_state.selected_type_id, 
                            st.session_state.user_id
                        ):
                            st.success("恢复成功")
                            st.session_state.refresh_types = not st.session_state.refresh_types
                            st.rerun()
                        else:
                            st.error("恢复失败")
                    else:
                        st.error("请先登录")
        else:
            st.info("从左侧选择一个类型进行操作")


def compact_note_type_selector():
    """
    更紧凑的版本 - 使用下拉选择器替代按钮网格
    """
    
    # 初始化
    if 'selected_type_id' not in st.session_state:
        st.session_state["selected_type_id"] = None
    
    # 获取类型
    all_types = get_all_note_types()
    types_dict = {t['type_name']: t['id'] for t in all_types} if all_types else {}
    
    if types_dict:
        selected_name = st.selectbox(
            "选择类型",
            options=list(types_dict.keys()),
            key="type_selector"
        )
        if selected_name:
            st.session_state.selected_type_id = types_dict[selected_name]
    else:
        st.warning("暂无类型，请先添加")
    
    if st.session_state.selected_type_id:
        with st.expander("快速操作"):

            with st.form("quick_add", clear_on_submit=True):
                new_name = st.text_input("新增类型", placeholder="输入新增类型名称", label_visibility="collapsed")
                if st.form_submit_button("添加", width='stretch', type='primary'):
                    if new_name:
                        new_id = create_note_type(new_name, created_by=st.session_state.get("user_id"))
                        if new_id:
                            st.success("添加成功")
                            st.rerun()
                        else:
                            st.error("名称已存在")

            with st.form("update_type_form_compact"):
                new_name = st.text_input(
                    "更新类型",
                    value=selected_name
                )
                if "user_id" in st.session_state:
                    updater_id = st.session_state.get("user_id")
                else:
                    st.error("请先登录以获取用户ID")
                    updater_id = None

                if st.form_submit_button("更新", use_container_width=True, type="primary"):
                    if update_note_type(
                        st.session_state.selected_type_id,
                        name=new_name,
                        updated_by=updater_id
                    ):
                        st.success("更新成功")
                        st.rerun()
                    else:
                        st.error("更新失败")
            
            # 软删除按钮
            if st.button(
                "软删除选中类型",
                type="secondary",
                width='stretch',
                key="soft_delete_btn_compact"
            ):
                if soft_delete_note_type(st.session_state.selected_type_id, updated_by=1):
                    st.success("删除成功")
                    st.session_state.selected_type_id = None
                    st.session_state.selected_type_name = None
                    st.rerun()
                else:
                    st.error("删除失败，可能已被删除")
    else:
        st.info("从左侧选择一个类型进行编辑或删除")
