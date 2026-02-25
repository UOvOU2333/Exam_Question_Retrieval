import streamlit as st
import uuid    
import streamlit_antd_components as sac

from utils.file_utils import save_uploaded_file_once

def rich_markdown(img_dir):

    col_title, col_choice = st.columns([1,2])

    with col_title:
        st.subheader("✏️ 编辑区")

    with col_choice:
        rich_tools()          # 顶部工具条

    render_tool_panel(img_dir)   # 动态工具面板

def rich_tools():

    if "active_tool" not in st.session_state:
        st.session_state.active_tool = None

    type_choice = sac.segmented(
        items=[
            sac.SegmentedItem(label="🖼️ 图片"),
            sac.SegmentedItem(label="📊 表格"),
            sac.SegmentedItem(label="∑ 公式"),
        ],
        align="start",
        radius="lg",
        size="md",
        key="rich_tool_segmented"
    )

    if type_choice:
        _map = {
            "🖼️ 图片": "image",
            "📊 表格": "table",
            "∑ 公式": "formula",
        }
        st.session_state.active_tool = _map.get(type_choice)

def image_tool(img_dir):
    st.subheader("📷 插入图片")

    uploaded_img = st.file_uploader(
        "支持 png / jpg / jpeg",
        type=["png", "jpg", "jpeg"]
    )

    if uploaded_img:
        img_url = save_uploaded_file_once(uploaded_img, img_dir)
        md = f"![图片说明]({img_url})"
        st.success("图片已生成，点击右上角复制按钮复制到剪贴板：")
        st.code(md, language="markdown")

def table_tool():
    st.subheader("📊 插入表格")

    r = st.number_input("行数", 1, 10, 2)
    c = st.number_input("列数", 1, 10, 2)

    if st.button("生成表格"):
        header = "| " + " | ".join(["列"]*c) + " |"
        split  = "| " + " | ".join(["---"]*c) + " |"
        body   = "\n".join(["| " + " | ".join([" "] * c) + " |" for _ in range(r)])

        md = f"{header}\n{split}\n{body}"
        st.success("表格 Markdown 已生成，点击右上角复制按钮复制：")
        st.code(md, language="markdown")

def formula_tool():
    st.subheader("∑ 插入公式")

    latex = st.text_input("输入 LaTeX")

    if st.button("生成公式 Markdown"):
        md = f"$$\n{latex}\n$$"
        st.success("公式 Markdown 已生成，点击右上角复制按钮复制：")
        st.code(md, language="markdown")

def render_tool_panel(img_dir):
    tool = st.session_state.active_tool

    if tool == "image":
        image_tool(img_dir)

    elif tool == "table":
        table_tool()

    elif tool == "formula":
        formula_tool()

def img_upload(img_dir):
    # =========================
    # 图片上传（公共）
    # =========================
    st.subheader("📷 图片上传（用于插入到 Markdown 中）")

    uploaded_img = st.file_uploader(
        "支持 png / jpg / jpeg",
        type=["png", "jpg", "jpeg"]
    )

    if uploaded_img:
        ext = uploaded_img.name.split(".")[-1]
        filename = f"{uuid.uuid4().hex}.{ext}"
        # save_path = os.path.join(img_dir, filename)

        # with open(save_path, "wb") as f:
        #    f.write(uploaded_img.getbuffer())

        img_url = save_uploaded_file_once(uploaded_img, img_dir)

        st.success("图片上传成功")
        st.markdown("⬇️ **复制下面这行，粘贴到任意 Markdown 编辑区即可使用：**")
        st.code(f"![图片说明]({img_url})")