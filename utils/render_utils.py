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

def render_markdown(text: str, header: str | None = None, keyword: str | None = None):
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

    # 若 keyword 存在且不为空字符串，才进行高亮替换
    if keyword:
        text = re.sub(re.escape(keyword), f'<span style="color:red">{keyword}</span>', text)

    lines = text.split("\n")

    buffer = []

    def flush_buffer():
        if buffer:
            processed_lines = []
            for line in buffer:
                # 1️⃣ 专门处理 ABCD 选项间的空格（新增）
                line = replace_option_spaces(line)
                # 2️⃣ 原有的连续空格替换（两个及以上空格转 &nbsp;）
                line = re.sub(r' {2,}', lambda m: '&nbsp;' * len(m.group()), line)
                processed_lines.append(line)
            md = "\n".join(processed_lines).replace("\n", "  \n")
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


def replace_option_spaces(text: str) -> str:
    """
    将形如 "A.①② B.①④ C.②③ D.③④" 的选项中，
    选项之间的连续空格（任意数量）替换为两个 &nbsp;。
    仅处理大写字母 A-D 后跟点号及非空白内容的选项。
    """
    # 匹配选项及其后面的空格（最后一个选项后的空格不匹配）
    # 模式：选项标记（如 A.①②） + 至少一个空格 + 后面紧跟另一个选项标记
    pattern = r'([A-D]\.[^\s]+)(\s+)(?=[A-D]\.[^\s]+)'
    # 将匹配到的空格部分替换为两个 &nbsp;，保留选项标记本身
    return re.sub(pattern, lambda m: m.group(1) + '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;', text)
