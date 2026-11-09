"""PDF 每页渲染为 PNG 图片（PyMuPDF/fitz）。

DeepSeek Files API 不支持 PDF（仅支持 webp/png/jpeg/gif）。
本模块把 PDF 页面渲染成 PNG 图片字节，供上传到 Files API 后
由 LLM 视觉能力理解——不依赖本地文本解析，对复杂排版/公式/
图表/扫描件的识别效果远优于 pdfplumber 文本提取。

渲染参数：
  RENDER_DPI=150  平衡清晰度与图片大小（约 1240x1754 @A4）

页数不设上限，仅受 PDF 文件大小约束；支持任意页号组合（非连续页）。
批次范围仅用于操作便利，不是限制。
"""
import re

RENDER_DPI = 150


class PdfRenderError(Exception):
    """PDF 渲染异常。"""
    pass


def _import_fitz():
    """延迟导入 PyMuPDF，失败抛 PdfRenderError。

    优先 import pymupdf（新 API），回退 import fitz（旧 API，已废弃但仍可用）。
    """
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz
        return fitz
    except ImportError:
        raise PdfRenderError("PDF 渲染依赖缺失（PyMuPDF 未安装，请 pip install PyMuPDF）")


def _open_pdf(fitz, file_path):
    """打开 PDF，统一异常信息。"""
    try:
        return fitz.open(file_path)
    except Exception as e:
        msg = str(e).lower()
        if "encrypt" in msg or "password" in msg or "cannot open" in msg:
            raise PdfRenderError("PDF 加密或受保护")
        raise PdfRenderError("PDF 打开失败: %s" % e)


def get_pdf_page_count(file_path):
    """读取 PDF 总页数（不渲染）。"""
    fitz = _import_fitz()
    doc = _open_pdf(fitz, file_path)
    try:
        count = doc.page_count
        if count == 0:
            raise PdfRenderError("PDF 无页面")
        return count
    finally:
        doc.close()


# 页选择表达式分隔符：中英文逗号、顿号、分号、空白
_PAGE_SPLIT_PATTERN = re.compile(r"[,，、;；\s]+")
# 区间写法：1-3 / 1~3 / 1—3 / 1–3 / 1至3
_PAGE_RANGE_PATTERN = re.compile(r"(\d+)\s*(?:[-~—–]|至)\s*(\d+)")
_PAGE_SINGLE_PATTERN = re.compile(r"(\d+)")


def parse_page_selection(text, page_count=None):
    """解析页选择表达式，返回去重升序的页号列表。

    支持非连续页号，如 "1-5,8,10-12" / "1、3、5-7" / "1-3 8 10"。

    Args:
        text: 页选择表达式
        page_count: 可选 PDF 总页数，用于越界校验

    Returns:
        list[int]: 升序页号列表；空表达式返回 []

    Raises:
        PdfRenderError: 表达式无法识别或页号越界
    """
    text = (text or "").strip()
    if not text:
        return []
    pages = set()
    for chunk in _PAGE_SPLIT_PATTERN.split(text):
        if not chunk:
            continue
        range_match = _PAGE_RANGE_PATTERN.fullmatch(chunk)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start > end:
                raise PdfRenderError("页范围起始不能大于结束：%s" % chunk)
            pages.update(range(start, end + 1))
            continue
        single_match = _PAGE_SINGLE_PATTERN.fullmatch(chunk)
        if single_match:
            pages.add(int(single_match.group(1)))
            continue
        raise PdfRenderError("无法识别的页号写法：%s" % chunk)
    if not pages:
        return []
    result = sorted(pages)
    if page_count is not None:
        invalid = [p for p in result if p < 1 or p > int(page_count)]
        if invalid:
            raise PdfRenderError(
                "页号超出范围：%s（PDF 共 %d 页）" % (
                    ",".join(str(p) for p in invalid), int(page_count),
                )
            )
    return result


def render_pdf_pages(file_path, page_nos, dpi=RENDER_DPI, max_pages=None):
    """按页号列表渲染 PNG，支持非连续页号。

    Args:
        file_path: PDF 本地路径
        page_nos: 页号列表（1-based），内部去重升序
        dpi: 渲染分辨率（默认 150）
        max_pages: 可选页数上限；None 表示不限制

    Returns:
        list[tuple[int, bytes]]: [(页号, PNG 字节)]，按页号升序

    Raises:
        PdfRenderError: 渲染失败（依赖缺失/加密/页号越界/格式异常）
    """
    pages = sorted({int(p) for p in page_nos or []})
    if not pages:
        raise PdfRenderError("未选择任何页面")
    fitz = _import_fitz()
    doc = _open_pdf(fitz, file_path)
    try:
        page_count = doc.page_count
        if page_count == 0:
            raise PdfRenderError("PDF 无页面")
        invalid = [p for p in pages if p < 1 or p > page_count]
        if invalid:
            raise PdfRenderError(
                "页号超出范围：%s（PDF 共 %d 页）" % (
                    ",".join(str(p) for p in invalid), page_count,
                )
            )
        if max_pages is not None and len(pages) > max_pages:
            raise PdfRenderError(
                "单批页数 %d 超过上限 %d，请分批处理" % (len(pages), max_pages)
            )

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        images = []
        for page_no in pages:
            page = doc.load_page(page_no - 1)
            pix = page.get_pixmap(matrix=matrix)
            images.append((page_no, pix.tobytes("png")))
        return images
    except PdfRenderError:
        raise
    except Exception as e:
        raise PdfRenderError("PDF 渲染失败: %s" % e)
    finally:
        doc.close()


def render_pdf_page_range(file_path, page_start=1, page_end=None,
                          dpi=RENDER_DPI, max_pages=None):
    """渲染连续页范围（兼容接口），内部转为页号列表渲染。"""
    start = int(page_start or 1)
    if page_end is None:
        end = get_pdf_page_count(file_path)
    else:
        end = int(page_end)
    if start > end:
        raise PdfRenderError("页范围无效：%d-%d" % (start, end))
    return render_pdf_pages(
        file_path, range(start, end + 1), dpi=dpi, max_pages=max_pages
    )


def render_pdf_pages_to_pngs(file_path, dpi=RENDER_DPI, max_pages=None):
    """把 PDF 每页渲染成 PNG 字节列表（兼容旧接口），默认不限制页数。"""
    images = render_pdf_page_range(
        file_path, page_start=1, page_end=None, dpi=dpi, max_pages=max_pages
    )
    return [png for _page_no, png in images]