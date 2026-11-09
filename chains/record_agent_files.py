"""DeepSeek Files API 集成层。

提供图片上传/列表/删除/下载能力，以及 PDF 本地缓存能力。
API Key 仅服务端读取，不前端暴露。

Files API base_url: https://api.deepseek.com（无 /v1）
  POST   /files          multipart 上传
  GET    /files          列出文件
  GET    /files/{id}     查询文件信息
  DELETE /files/{id}     删除文件
  GET    /files/{id}/content  下载文件内容

格式与大小约束：
  图片：JPEG/PNG/GIF/WebP，单文件 ≤ 64 MiB（Files API 上传限制，见官方文档）
  PDF：  Files API 不支持 PDF（仅支持 webp/png/jpeg/gif），无 API 大小限制。
         PDF 仅本地缓存到 static/cache/，由 pdfplumber 解析后把提取的文本喂给 LLM。
         PDF_MAX_BYTES 为本地防护上限（防恶意/误传超大文件占满磁盘），
         不限制页数——仅受文件大小与解析超时约束。
"""
import os
import time
import uuid
import requests

FILES_BASE_URL = "https://api.deepseek.com"

IMAGE_MAX_BYTES = 64 * 1024 * 1024
PDF_MAX_BYTES = 100 * 1024 * 1024
IMAGE_FORMATS = {"jpeg", "jpg", "png", "gif", "webp"}

# Files API 文件有效期（秒）。作为远端硬上限尽量设长（30 天，API 允许的最大值），
# 真正的过期由系统按“最后使用后 24 小时”判断（FILE_IDLE_EXPIRE_SECONDS）。
FILE_EXPIRE_SECONDS = 30 * 24 * 3600
# 系统侧空闲过期：文件最后使用后超过 24 小时视为过期，恢复会话时要求重新上传/加载。
FILE_IDLE_EXPIRE_SECONDS = 24 * 3600
# 本地缓存清理阈值（秒），页面加载时清理超过此年龄的本地缓存文件。
# 本地 PDF 保留 7 天：Files API 页图 1 小时过期后，仍可重新渲染批次，
# 不必让用户重新上传整份 PDF。
LOCAL_CACHE_MAX_AGE = 7 * 24 * 3600

# 上传超时（秒）
IMAGE_UPLOAD_TIMEOUT = 30
PDF_UPLOAD_TIMEOUT = 60
# 下载超时（秒）
DOWNLOAD_TIMEOUT = 60

# 本地缓存目录
LOCAL_CACHE_DIR = "static/cache"


def _get_api_key(api_key=None):
    """API Key 优先显式传入，否则从环境/streamlit secrets 获取。"""
    if api_key:
        return api_key
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("deepseek_api_key")
    except Exception:
        return None


def validate_image(filename, file_bytes):
    """校验图片格式与大小。返回 (bool, str)。"""
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    if ext not in IMAGE_FORMATS:
        return False, "仅支持 JPEG/PNG/GIF/WebP，且单文件不超过 64 MiB"
    if len(file_bytes) > IMAGE_MAX_BYTES:
        return False, "图片大小超过 64 MiB 限制"
    return True, "ok"


def validate_pdf(filename, file_bytes):
    """校验 PDF 格式与大小。返回 (bool, str)。

    PDF 不上传到 Files API（DeepSeek 仅支持图片），仅本地缓存解析。
    大小限制为本地防护上限（防超大文件占满磁盘），非 API 限制；
    不限制页数，仅受文件大小与解析超时约束。
    """
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    if ext != "pdf":
        return False, "仅支持 PDF 格式"
    if len(file_bytes) > PDF_MAX_BYTES:
        return False, "单文件不超过 100 MiB"
    return True, "ok"


def save_pdf_to_local(file_bytes, filename):
    """将 PDF 保存到本地缓存目录，返回 (local_file_id, local_path)。

    DeepSeek Files API 不支持 PDF（仅支持 webp/png/jpeg/gif），
    因此 PDF 仅本地缓存，由 pdfplumber 解析后把文本喂给 LLM。
    local_file_id 形如 local-pdf-xxxxxxxxxxxxxxxx，与 Files API 的
    file-api-xxx 区分，工具层通过 pdf_local_paths 字典映射到本地路径。

    Args:
        file_bytes: PDF 字节内容
        filename: 原始文件名（仅用于日志/展示）

    Returns:
        tuple[str, str]: (local_file_id, local_path)
    """
    os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
    local_file_id = "local-pdf-%s" % uuid.uuid4().hex[:16]
    local_path = os.path.join(LOCAL_CACHE_DIR, "%s.pdf" % local_file_id)
    with open(local_path, "wb") as f:
        f.write(file_bytes)
    return local_file_id, local_path


def remove_local_pdf(local_file_id, pdf_local_paths):
    """删除本地缓存的 PDF 文件并清理路径映射。

    Args:
        local_file_id: save_pdf_to_local 返回的 local_file_id
        pdf_local_paths: st.session_state["ra_pdf_local_paths"] 字典

    Returns:
        bool: 是否成功删除
    """
    local_path = pdf_local_paths.pop(local_file_id, None)
    if local_path and os.path.exists(local_path):
        try:
            os.remove(local_path)
            return True
        except OSError:
            return False
    return False


def upload_pdf_pages_as_images(file_path, filename, page_start=1, page_end=None,
                               page_nos=None, api_key=None, base_url=FILES_BASE_URL):
    """把 PDF 指定页面渲染成 PNG 并上传到 Files API。

    上传 PDF 时不再限制页数；用户可选择任意页范围/页号组合分批，
    只渲染上传所选页面，后续以 {"type":"file","file_id"} 内容块引用。

    Args:
        file_path: PDF 本地路径
        filename: 原始 PDF 文件名（用于生成页面图片名）
        page_start: 起始页（1-based，含），仅在未传 page_nos 时使用
        page_end: 结束页（含），None 表示到最后一页
        page_nos: 页号列表，支持非连续页号（如 [1,3,5]）；提供时忽略 start/end
        api_key: DeepSeek API Key（None 则自动获取）
        base_url: Files API base

    Returns:
        list[tuple[int, str]]: [(页号, file_id)]，按页号升序

    Raises:
        RuntimeError: 渲染或上传失败
    """
    from chains.pdf_to_images import (
        render_pdf_page_range,
        render_pdf_pages,
        PdfRenderError,
    )
    try:
        if page_nos is not None:
            page_pngs = render_pdf_pages(file_path, page_nos)
        else:
            page_pngs = render_pdf_page_range(
                file_path, page_start=page_start, page_end=page_end
            )
    except PdfRenderError as e:
        raise RuntimeError(str(e))

    key = _get_api_key(api_key)
    if not key:
        raise RuntimeError("DeepSeek API Key 未配置")

    base = os.path.splitext(filename)[0]
    page_files = []
    for page_no, png_bytes in page_pngs:
        page_name = "%s_p%d.png" % (base, page_no)
        ok, msg = validate_image(page_name, png_bytes)
        if not ok:
            # 已上传的页面图片回滚删除
            for _n, fid in page_files:
                delete_file_api(fid, api_key=key, base_url=base_url)
            raise RuntimeError("页面 %d 图片校验失败: %s" % (page_no, msg))
        file_id = upload_to_files_api(
            png_bytes, page_name, api_key=key, base_url=base_url
        )
        page_files.append((page_no, file_id))
    return page_files


def delete_page_images(page_file_ids, api_key=None, base_url=FILES_BASE_URL):
    """删除 PDF 页面图片（批量），用于 PDF 删除或回滚。"""
    for fid in page_file_ids or []:
        delete_file_api(fid, api_key=api_key, base_url=base_url)


def upload_to_files_api(file_bytes, filename, purpose="user_data",
                        api_key=None, base_url=FILES_BASE_URL, is_pdf=False,
                        expires_seconds=FILE_EXPIRE_SECONDS):
    """上传文件到 DeepSeek Files API，返回 file_id。

    Args:
        file_bytes: 文件字节内容
        filename: 文件名
        purpose: 必须为 user_data
        api_key: DeepSeek API Key（None 则自动获取）
        base_url: Files API base
        is_pdf: 是否 PDF（影响超时）
        expires_seconds: 文件有效期（秒），到期后 Files API 自动删除。
            默认 FILE_EXPIRE_SECONDS（1 小时），避免会话结束后缓存堆积。
            传 None 则永久有效。

    Returns:
        str: file_id（格式 file-api-xxxxxxxxxxxxxxxx）

    Raises:
        RuntimeError: API Key 缺失或上传失败
    """
    key = _get_api_key(api_key)
    if not key:
        raise RuntimeError("DeepSeek API Key 未配置")
    timeout = PDF_UPLOAD_TIMEOUT if is_pdf else IMAGE_UPLOAD_TIMEOUT
    url = "%s/files" % base_url
    headers = {"Authorization": "Bearer %s" % key}
    files = {"file": (filename, file_bytes)}
    data = {"purpose": purpose}
    if expires_seconds:
        data["expires_after[anchor]"] = "created_at"
        data["expires_after[seconds]"] = str(int(expires_seconds))
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError("上传失败 [%d]: %s" % (resp.status_code, resp.text[:200]))
    body = resp.json()
    return body["id"]


def cleanup_local_cache(max_age_seconds=LOCAL_CACHE_MAX_AGE, cache_dir=LOCAL_CACHE_DIR):
    """清理本地缓存目录中超过 max_age_seconds 的旧文件。

    页面加载时调用，避免 static/cache/ 下旧文件堆积。仅清理文件，
    不递归子目录；清理失败静默跳过（不影响主流程）。

    Args:
        max_age_seconds: 文件最大年龄（秒），超过则删除
        cache_dir: 缓存目录

    Returns:
        int: 删除的文件数
    """
    if not os.path.exists(cache_dir):
        return 0
    now = time.time()
    removed = 0
    try:
        for name in os.listdir(cache_dir):
            path = os.path.join(cache_dir, name)
            if not os.path.isfile(path):
                continue
            try:
                if now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed


def delete_file_api(file_id, api_key=None, base_url=FILES_BASE_URL):
    """删除文件，返回是否成功。"""
    key = _get_api_key(api_key)
    if not key:
        return False
    url = "%s/files/%s" % (base_url, file_id)
    headers = {"Authorization": "Bearer %s" % key}
    try:
        resp = requests.delete(url, headers=headers, timeout=30)
        return resp.status_code == 200
    except Exception:
        return False


def list_files_api(api_key=None, base_url=FILES_BASE_URL, limit=100):
    """列出已上传文件。"""
    key = _get_api_key(api_key)
    if not key:
        return []
    url = "%s/files" % base_url
    headers = {"Authorization": "Bearer %s" % key}
    params = {"limit": limit}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            return []
        body = resp.json()
        return body.get("data", [])
    except Exception:
        return []


def retrieve_file_api(file_id, api_key=None, base_url=FILES_BASE_URL):
    """查询文件信息，返回 dict 或 None。"""
    key = _get_api_key(api_key)
    if not key:
        return None
    url = "%s/files/%s" % (base_url, file_id)
    headers = {"Authorization": "Bearer %s" % key}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def download_to_local_cache(file_id, api_key=None, base_url=FILES_BASE_URL):
    """下载文件至本地缓存目录 static/cache/，返回本地路径供 render_markdown 渲染。

    Returns:
        str: 本地文件路径

    Raises:
        RuntimeError: 下载失败
    """
    key = _get_api_key(api_key)
    if not key:
        raise RuntimeError("DeepSeek API Key 未配置")
    os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
    local_path = os.path.join(LOCAL_CACHE_DIR, file_id)
    if os.path.exists(local_path):
        return local_path
    url = "%s/files/%s/content" % (base_url, file_id)
    headers = {"Authorization": "Bearer %s" % key}
    resp = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError("下载失败 [%d]: %s" % (resp.status_code, resp.text[:200]))
    with open(local_path, "wb") as f:
        f.write(resp.content)
    return local_path
