"""
试卷导出工具：
- 用 markdown 库把题目 Markdown 渲染成 HTML（完美还原题目录入时的格式）
- Word 导出：HTML → htmldocx → python-docx
- PDF 导出：HTML → fpdf2.write_html

这样能正确处理：
  - 硬换行（题干、①②③④、ABCD 选项各占一行）
  - 表格（Markdown table → HTML table）
  - 图片（![alt](path) → <img>）
  - 段落、加粗、斜体等
"""

import os
import re
import io
from typing import List, Tuple, Optional

import markdown


# ============================================================
# Markdown → HTML
# ============================================================

def _preprocess_markdown(text: str) -> str:
    """
    预处理题目 Markdown：
    - 把单个 \\n（行内换行）转成 Markdown 硬换行（行尾两空格），
      这样 markdown 库会生成 <br>，保留题干/选项的换行。
    - 段落间的空行（\\n\\n）保持不变（Markdown 段落分隔）。
    """
    if not text:
        return ""
    lines = text.split("\n")
    processed = []
    for i, line in enumerate(lines):
        if i < len(lines) - 1 and lines[i + 1].strip() != "" and line.strip() != "":
            # 当前行后面还有非空内容且当前行非空 → 加硬换行
            processed.append(line + "  ")
        else:
            processed.append(line)
    return "\n".join(processed)


def markdown_to_html(text: str) -> str:
    """把题目 Markdown 渲染成 HTML。"""
    if not text:
        return ""
    processed = _preprocess_markdown(text)
    return markdown.markdown(processed, extensions=["tables", "fenced_code"])


# ============================================================
# 图片处理：缺失图片的容错
# ============================================================

def _resolve_image_path_in_html(html: str, max_width_mm: float = 180) -> str:
    """
    处理 HTML 里的 <img src="path">：
    - 缺失图片 → 替换成提示文本
    - 存在图片 → 转成绝对路径，并加 width 属性限制宽度（防止超宽）
      max_width_mm: 图片最大宽度（mm），默认 180（A4 可用宽度约 190mm，留点边距）
    """
    from PIL import Image

    def replace_img(match):
        full = match.group(0)
        src = match.group(1)
        if not src:
            return full
        # 解析路径
        abs_path = None
        if os.path.isabs(src) and os.path.exists(src):
            abs_path = src
        elif os.path.exists(src):
            abs_path = os.path.abspath(src)
        if abs_path is None:
            # 图片缺失 → 替换成提示文本
            return f'<p>[图片缺失：{src}]</p>'
        # 图片存在 → 计算合适的宽度
        try:
            with Image.open(abs_path) as im:
                w_px, h_px = im.size
            # 转 mm（按 96 DPI）
            w_mm = w_px * 25.4 / 96.0
            if w_mm > max_width_mm:
                w_mm = max_width_mm
            # 重新生成 <img> 标签，带 width 属性（mm）
            # htmldocx 和 fpdf2 都支持 width 属性
            return f'<img src="{abs_path}" width="{w_mm:.1f}mm" />'
        except Exception:
            return f'<p>[图片加载失败：{src}]</p>'

    return re.sub(r'<img[^>]*src=["\']([^"\']*)["\'][^>]*/?>', replace_img, html)


# ============================================================
# Word 导出（markdown → html → htmldocx）
# ============================================================

def export_to_word(
    questions: List[dict],
    paper_title: str,
    include_answer: bool = True,
    include_analysis: bool = True,
    include_source: bool = True,
) -> bytes:
    """
    把一套试卷的题目导出为 Word 文档，返回二进制内容。
    """
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from htmldocx import HtmlToDocx

    doc = Document()

    # 设置默认中文字体（宋体）
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        from docx.oxml import OxmlElement
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), "宋体")

    parser = HtmlToDocx()

    def add_html_safe(html: str, doc):
        """安全地把 HTML 加到 Word 文档，htmldocx 出错时降级为纯文本。"""
        if not html.strip():
            return
        try:
            parser.add_html_to_document(html, doc)
        except Exception:
            # 降级：去掉所有 HTML 标签，按纯文本写入
            plain = re.sub(r'<[^>]+>', '', html)
            plain = plain.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            for line in plain.split('\n'):
                if line.strip():
                    doc.add_paragraph(line.strip())

    # 标题
    title_p = doc.add_heading(paper_title, level=0)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    info_p = doc.add_paragraph()
    info_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info_run = info_p.add_run(f"共 {len(questions)} 道题")
    info_run.font.size = Pt(10)

    doc.add_paragraph()  # 空行

    for idx, q in enumerate(questions, 1):
        qno = q.get("question_no") or str(idx)
        content = q.get("content") or ""
        answer = q.get("answer") or ""
        analysis = q.get("analysis") or ""
        source = q.get("source") or ""
        analysis_source = q.get("analysis_source") or ""

        # 题号标题
        doc.add_heading(f"第 {qno} 题", level=1)

        # 题目内容（markdown → html → docx）
        html = markdown_to_html(content)
        html = _resolve_image_path_in_html(html)
        add_html_safe(html, doc)

        # 答案
        if include_answer and answer:
            doc.add_heading("【答案】", level=2)
            html = markdown_to_html(answer)
            html = _resolve_image_path_in_html(html)
            add_html_safe(html, doc)

        # 解析
        if include_analysis and analysis:
            doc.add_heading("【解析】", level=2)
            html = markdown_to_html(analysis)
            html = _resolve_image_path_in_html(html)
            add_html_safe(html, doc)

        # 来源
        if include_source:
            src_parts = []
            if source:
                src_parts.append(f"题目来源：{source}")
            if analysis_source and analysis_source != source:
                src_parts.append(f"解析来源：{analysis_source}")
            if src_parts:
                p = doc.add_paragraph()
                run = p.add_run("；".join(src_parts))
                run.font.size = Pt(9)
                run.italic = True

        # 题目间分隔
        if idx < len(questions):
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ============================================================
# PDF 导出（markdown → html → fpdf2.write_html）
# ============================================================

# 中文字体候选路径（macOS / 各 Linux 发行版）
_CJK_FONT_CANDIDATES = [
    ("PingFang", "/System/Library/Fonts/PingFang.ttc"),
    ("STHeiti", "/System/Library/Fonts/STHeiti Medium.ttc"),
    ("HiraginoSansGB", "/System/Library/Fonts/Hiragino Sans GB.ttc"),
    ("NotoSansCJK", "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),  # RHEL/Alibaba Cloud Linux
    ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),    # Debian/Ubuntu
    ("NotoSansCJK", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),    # 其他
    ("WenQuanYi", "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc"),
]


def _find_cjk_font() -> Tuple[str, str]:
    """返回 (字体名, 字体文件路径)，找不到抛异常。"""
    for name, path in _CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            return name, path
    raise RuntimeError(
        "未找到可用的中文字体。请安装 Noto CJK 或 PingFang 等中文字体。"
    )


def _render_html_to_pdf(pdf, html: str, font_name: str):
    """
    把 HTML 渲染到 PDF。
    fpdf2 的 write_html 对 <img> 的 width 支持有限（不支持 mm 单位），
    所以把图片从 HTML 里提取出来，单独用 pdf.image() 渲染（能精确控制宽度），
    其余 HTML 仍用 write_html 渲染。
    """
    from PIL import Image

    if not html.strip():
        return

    # 用 <img> 标签把 HTML 拆成多段
    img_pat = re.compile(r'<img[^>]*src=["\']([^"\']*)["\'][^>]*/?>')
    parts = []
    last_end = 0
    for m in img_pat.finditer(html):
        # 图片前的 HTML
        if m.start() > last_end:
            parts.append(("html", html[last_end:m.start()]))
        # 图片
        src = m.group(1)
        parts.append(("image", src))
        last_end = m.end()
    # 最后一段
    if last_end < len(html):
        parts.append(("html", html[last_end:]))

    # 修复被截断的 <p> 标签：每段 HTML 若含未闭合的 <p> 则补上 </p>，
    # 若以 </p> 开头则补上 <p>，避免 fpdf2 write_html 警告
    fixed_parts = []
    for kind, payload in parts:
        if kind == "html":
            h = payload
            # 简单修复：去掉孤立的 <p> 开头和 </p> 结尾，让内容成为纯文本段
            # fpdf2 的 write_html 对 <p> 包裹的文本处理正常，对残缺的会警告
            # 这里用更稳妥的方式：把残缺的 <p>/</p> 去掉
            open_p = len(re.findall(r'<p[^>]*>', h))
            close_p = len(re.findall(r'</p>', h))
            if open_p > close_p:
                h = h + '</p>' * (open_p - close_p)
            elif close_p > open_p:
                h = '<p>' * (close_p - open_p) + h
            payload = h
        fixed_parts.append((kind, payload))
    parts = fixed_parts

    page_width = pdf.w - 2 * pdf.l_margin  # A4 可用宽度（mm）

    for kind, payload in parts:
        if kind == "html":
            h = payload.strip()
            if h:
                try:
                    pdf.write_html(h)
                except Exception:
                    # 降级：纯文本
                    plain = re.sub(r'<[^>]+>', '', h)
                    plain = plain.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                    if plain.strip():
                        pdf.multi_cell(0, 7, plain, new_x="LMARGIN", new_y="NEXT")
        elif kind == "image":
            src = payload
            if not os.path.exists(src):
                pdf.multi_cell(0, 7, f"[图片缺失：{src}]", new_x="LMARGIN", new_y="NEXT")
                continue
            try:
                with Image.open(src) as im:
                    w_px, h_px = im.size
                w_mm = w_px * 25.4 / 96.0
                if w_mm > page_width:
                    w_mm = page_width
                pdf.image(src, w=w_mm)
                pdf.ln(2)
            except Exception:
                pdf.multi_cell(0, 7, f"[图片加载失败：{src}]", new_x="LMARGIN", new_y="NEXT")


def export_to_pdf(
    questions: List[dict],
    paper_title: str,
    include_answer: bool = True,
    include_analysis: bool = True,
    include_source: bool = True,
) -> bytes:
    """
    把一套试卷的题目导出为 PDF，返回二进制内容。
    """
    from fpdf import FPDF

    font_name, font_path = _find_cjk_font()

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    # 注册 Regular 和 Bold（表格表头需要粗体）
    pdf.add_font(font_name, fname=font_path)
    pdf.add_font(font_name, style="B", fname=font_path)
    pdf.set_font(font_name, size=11)

    # 标题
    pdf.set_font_size(20)
    pdf.multi_cell(0, 12, paper_title, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font_size(10)
    pdf.multi_cell(0, 8, f"共 {len(questions)} 道题", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for idx, q in enumerate(questions, 1):
        qno = q.get("question_no") or str(idx)
        content = q.get("content") or ""
        answer = q.get("answer") or ""
        analysis = q.get("analysis") or ""
        source = q.get("source") or ""
        analysis_source = q.get("analysis_source") or ""

        # 题号
        pdf.set_font_size(14)
        pdf.multi_cell(0, 10, f"第 {qno} 题", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        pdf.set_font_size(11)

        # 题目内容（markdown → html → fpdf2）
        html = markdown_to_html(content)
        html = _resolve_image_path_in_html(html)
        _render_html_to_pdf(pdf, html, font_name)

        # 答案
        if include_answer and answer:
            pdf.ln(2)
            pdf.set_font_size(12)
            pdf.multi_cell(0, 9, "【答案】", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font_size(11)
            html = markdown_to_html(answer)
            html = _resolve_image_path_in_html(html)
            _render_html_to_pdf(pdf, html, font_name)

        # 解析
        if include_analysis and analysis:
            pdf.ln(2)
            pdf.set_font_size(12)
            pdf.multi_cell(0, 9, "【解析】", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font_size(11)
            html = markdown_to_html(analysis)
            html = _resolve_image_path_in_html(html)
            _render_html_to_pdf(pdf, html, font_name)

        # 来源
        if include_source:
            src_parts = []
            if source:
                src_parts.append(f"题目来源：{source}")
            if analysis_source and analysis_source != source:
                src_parts.append(f"解析来源：{analysis_source}")
            if src_parts:
                pdf.ln(1)
                pdf.set_font_size(9)
                pdf.multi_cell(0, 6, "；".join(src_parts), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font_size(11)

        # 题间空行
        pdf.ln(4)

    # fpdf2 的 output() 返回 bytearray，streamlit download_button 需要 bytes
    return bytes(pdf.output())
