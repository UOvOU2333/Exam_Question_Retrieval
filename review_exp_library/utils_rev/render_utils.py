"""Markdown 渲染工具（复刻政治题库 utils/render_utils.py）。

- 图片：![alt](path) → st.image（支持相对路径自动转绝对路径）
- 选项空格：A.①② B.①④ → A.①②&nbsp;...&nbsp;B.①④
- 连续空格：2+ 空格 → 对应数量 &nbsp;
- 硬换行：\\n → 两空格 + \\n
- 关键词高亮：<span style="color:red">
- 表格识别
"""

import os
import re

import streamlit as st
from PIL import Image

from utils_rev.config import BASE_DIR

IMAGE_PATTERN = re.compile(r"!\[.*?\]\((.*?)\)")


def _resolve_path(img_path: str) -> str:
    """相对路径转绝对路径（基于 BASE_DIR）。"""
    if os.path.isabs(img_path) and os.path.exists(img_path):
        return img_path
    abs1 = str(BASE_DIR / img_path)
    if os.path.exists(abs1):
        return abs1
    return img_path


def safe_render_image(img_path: str):
    try:
        img = Image.open(_resolve_path(img_path))
        st.image(img)
    except FileNotFoundError:
        st.warning(f"图片无法加载：{img_path}")
    except Exception as e:
        st.warning(f"图片加载出错：{e}")


def is_markdown_table_start(lines: str) -> bool:
    lines_list = lines.split("\n")
    if len(lines_list) < 2:
        return False
    line1 = lines_list[0].strip()
    line2 = lines_list[1].strip()
    if line1.count("|") < 2:
        return False
    table_separator_pattern = r"^\s*\|[\s\-:|]+\|\s*$"
    return bool(re.match(table_separator_pattern, line2)) and "-" in line2


def replace_option_spaces(text: str) -> str:
    """将形如 "A.①② B.①④ C.②③ D.③④" 选项间的空格替换为 6 个 &nbsp;。"""
    pattern = r"([A-D]\.[^\s]+)(\s+)(?=[A-D]\.[^\s]+)"
    return re.sub(pattern, lambda m: m.group(1) + "&nbsp;" * 6, text)


def render_markdown(text: str, header: str | None = None, keyword: str | None = None):
    """Streamlit 友好的 Markdown 渲染：文本用 st.markdown，图片用 st.image。"""
    if not text:
        return

    first_line = text.split("\n", 1)[0]
    match_first_img = IMAGE_PATTERN.search(first_line)
    match_table = is_markdown_table_start(text)

    if (match_first_img or match_table) and header:
        st.write(header)
    elif header:
        text = header + text

    if keyword:
        text = re.sub(re.escape(keyword), f'<span style="color:red">{keyword}</span>', text)

    lines = text.split("\n")
    buffer = []

    def flush_buffer():
        if buffer:
            processed_lines = []
            for line in buffer:
                line = replace_option_spaces(line)
                line = re.sub(r" {2,}", lambda m: "&nbsp;" * len(m.group()), line)
                processed_lines.append(line)
            md = "\n".join(processed_lines).replace("\n", "  \n")
            st.markdown(md, unsafe_allow_html=True)
            buffer.clear()

    for line in lines:
        match = IMAGE_PATTERN.search(line)
        if match:
            flush_buffer()
            img_path = match.group(1)
            safe_render_image(img_path)
        else:
            buffer.append(line)

    flush_buffer()
