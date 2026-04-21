import re
import streamlit as st
from PIL import Image


IMAGE_PATTERN = re.compile(r"!\[.*?\]\((.*?)\)")

def safe_render_image(img_path):
    try:
        img = Image.open(img_path)
        st.image(img)
    except FileNotFoundError:
        st.warning(f"⚠️ 图片无法加载：{img_path}")
    except Exception as e:
        st.warning(f"⚠️ 图片加载出错：{e}")

def render_markdown(text: str, header: str | None = None):
    """
    Streamlit 友好的 Markdown 渲染：
    - 文本：st.markdown
    - 图片：st.image
    """
    if not text:
        return
    
    first_line = text.split("\n", 1)[0]
    match_first_img = IMAGE_PATTERN.search(first_line)
    match_table = is_markdown_table_start(text)
    if (match_first_img or match_table) and header:
        st.write(header)
    elif header:
        text = header + text

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
            safe_render_image(img_path)
        else:
            buffer.append(line)

    flush_buffer()


def is_markdown_table_start(lines):
    """判断指定位置是否以标准 Markdown 表格开头"""
    lines_list = lines.split("\n")

    if len(lines_list) < 2:
        return False

    line1 = lines_list[0].strip()
    line2 = lines_list[1].strip()

    # 第一行必须包含至少两个 |
    if line1.count("|") < 2:
        return False

    # 第二行必须是表格分隔符格式：|:?---+:?| 或 |---|
    # 允许冒号在两端表示对齐方式
    import re
    table_separator_pattern = r'^\s*\|[\s\-:|]+\|\s*$'

    return bool(re.match(table_separator_pattern, line2)) and "-" in line2