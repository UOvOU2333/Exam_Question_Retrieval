import re
import streamlit as st


IMAGE_PATTERN = re.compile(r"!\[.*?\]\((.*?)\)")


def render_markdown(text: str):
    """
    Streamlit 友好的 Markdown 渲染：
    - 文本：st.markdown
    - 图片：st.image
    """
    if not text:
        return

    lines = text.split("\n")

    buffer = []

    def flush_buffer():
        if buffer:
            md = "\n".join(buffer).replace("\n", "  \n")
            st.markdown(md, unsafe_allow_html=True)
            buffer.clear()

    for line in lines:
        match = IMAGE_PATTERN.search(line)

        if match:
            # 先把之前的文字渲染掉
            flush_buffer()

            img_path = match.group(1)
            try:
                st.image(img_path)
            except Exception:
                st.warning(f"⚠️ 图片无法加载：{img_path}")
        else:
            buffer.append(line)

    flush_buffer()
