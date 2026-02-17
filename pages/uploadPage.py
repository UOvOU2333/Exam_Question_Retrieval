import hashlib
import os
import uuid
import streamlit as st

from pathlib import Path
from utils.auth_utils import require_role
from utils.render_utils import render_markdown
from services.question_services import create_question

# =========================
# 图片存储配置
# =========================
IMAGE_DIR = "static/images/questions"
os.makedirs(IMAGE_DIR, exist_ok=True)


def save_uploaded_file_once(uploaded_file, save_dir="static/images/questions"):
    """
    智能保存上传文件：相同内容的文件只保存一次
    """
    # 1. 计算文件内容的哈希值（唯一标识）
    file_bytes = uploaded_file.getvalue()
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]

    # 2. 获取原始文件扩展名
    original_ext = Path(uploaded_file.name).suffix

    # 3. 用哈希值作为文件名（确保相同内容→相同文件名）
    filename = f"{file_hash}{original_ext}"
    save_path = os.path.join(save_dir, filename)

    # 4. 关键：只有文件不存在时才写入
    if not os.path.exists(save_path):
        with open(save_path, "wb") as f:
            f.write(file_bytes)
        print(f"✅ 新文件已保存: {filename}")
    else:
        print(f"⏭️ 文件已存在，跳过写入: {filename}")

    # 5. 返回可访问的URL路径
    return f"static/images/questions/{filename}"


def upload():
    # ===== 权限校验 =====
    require_role("admin", "editor")

    st.title("试题上传（支持 Markdown / LaTeX）")

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
        # save_path = os.path.join(IMAGE_DIR, filename)

        # with open(save_path, "wb") as f:
        #    f.write(uploaded_img.getbuffer())

        img_url = save_uploaded_file_once(uploaded_img, IMAGE_DIR)

        st.success("图片上传成功")
        st.markdown("⬇️ **复制下面这行，粘贴到任意 Markdown 编辑区即可使用：**")
        st.code(f"![图片说明]({img_url})")

    st.divider()

    # =========================
    # Markdown 编辑 + 实时预览
    # =========================
    col_edit, col_preview = st.columns(2)

    with col_edit:
        st.subheader("✏️ 编辑区（Markdown）")

        content = st.text_area(
            "试题内容",
            height=220,
            placeholder="请输入题目正文（支持 Markdown / LaTeX / 图片）"
        )

        answer = st.text_area(
            "答案",
            height=120,
            placeholder="请输入答案（支持 Markdown / LaTeX）"
        )

        analysis = st.text_area(
            "解析",
            height=180,
            placeholder="请输入解析（支持 Markdown / LaTeX）"
        )

        source = st.text_input("题目来源")
        analysis_source = st.text_input("解析来源")

    with col_preview:
        st.subheader("👀 实时预览")

        if content.strip():
            st.markdown("### 题目内容")
            render_markdown(content)

        if answer.strip():
            st.markdown("### 答案")
            render_markdown(answer)

        if analysis.strip():
            st.markdown("### 解析")
            render_markdown(analysis)

        if not (content.strip() or answer.strip() or analysis.strip()):
            st.info("开始输入后，这里会实时预览 Markdown 内容")

    st.divider()

    # =========================
    # 提交试题
    # =========================
    if st.button("✅ 提交试题", type="primary"):
        if not content.strip():
            st.error("❌ 题目内容不能为空")
            return

        create_question(
            content=content,
            answer=answer,
            analysis=analysis,
            source=source,
            analysis_source=analysis_source
        )

        st.success("🎉 试题上传成功")
        st.session_state["nav"] = "数据库"
        st.rerun()
