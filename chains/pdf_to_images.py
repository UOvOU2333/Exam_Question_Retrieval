"""PDF 每页渲染为 PNG 图片（PyMuPDF/fitz）。

DeepSeek Files API 不支持 PDF（仅支持 webp/png/jpeg/gif）。
本模块把 PDF 每页渲染成 PNG 图片字节，供上传到 Files API 后
由 LLM 视觉能力理解——不依赖本地文本解析，对复杂排版/公式/
图表/扫描件的识别效果远优于 pdfplumber 文本提取。

渲染参数：
  RENDER_DPI=150  平衡清晰度与图片大小（约 1240x1754 @A4）
  MAX_PAGES=30    页数上限，超过提示用户拆分（避免图片过多 token 爆炸）
"""
RENDER_DPI = 150
MAX_PAGES = 30


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


def render_pdf_pages_to_pngs(file_path, dpi=RENDER_DPI, max_pages=MAX_PAGES):
    """把 PDF 每页渲染成 PNG 字节列表。

    Args:
        file_path: PDF 本地路径
        dpi: 渲染分辨率（默认 150）
        max_pages: 最大页数上限（默认 30）

    Returns:
        list[bytes]: 每页 PNG 字节内容，顺序与 PDF 页码一致

    Raises:
        PdfRenderError: 渲染失败（依赖缺失/加密/页数超限/格式异常）
    """
    fitz = _import_fitz()
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        msg = str(e).lower()
        if "encrypt" in msg or "password" in msg or "cannot open" in msg:
            raise PdfRenderError("PDF 加密或受保护")
        raise PdfRenderError("PDF 打开失败: %s" % e)

    try:
        page_count = doc.page_count
        if page_count == 0:
            raise PdfRenderError("PDF 无页面")
        if page_count > max_pages:
            raise PdfRenderError(
                "PDF 页数 %d 超过上限 %d，请拆分后上传" % (page_count, max_pages)
            )

        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            png_bytes = pix.tobytes("png")
            images.append(png_bytes)
        return images
    except PdfRenderError:
        raise
    except Exception as e:
        raise PdfRenderError("PDF 渲染失败: %s" % e)
    finally:
        doc.close()
