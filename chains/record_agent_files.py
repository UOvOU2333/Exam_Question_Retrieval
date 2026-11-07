"""DeepSeek Files API 集成层。

提供图片/PDF 上传、列表、删除、下载能力。API Key 仅服务端读取，不前端暴露。

Files API base_url: https://api.deepseek.com（无 /v1）
  POST   /files          multipart 上传
  GET    /files          列出文件
  GET    /files/{id}     查询文件信息
  DELETE /files/{id}     删除文件
  GET    /files/{id}/content  下载文件内容

格式与大小约束：
  图片：JPEG/PNG/GIF/WebP，单文件 ≤ 64 MiB
  PDF：  .pdf，单文件 ≤ 32 MiB
"""
import os
import requests

FILES_BASE_URL = "https://api.deepseek.com"

IMAGE_MAX_BYTES = 64 * 1024 * 1024
PDF_MAX_BYTES = 32 * 1024 * 1024
IMAGE_FORMATS = {"jpeg", "jpg", "png", "gif", "webp"}

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
    """校验 PDF 格式与大小。返回 (bool, str)。"""
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    if ext != "pdf":
        return False, "仅支持 PDF 格式"
    if len(file_bytes) > PDF_MAX_BYTES:
        return False, "单文件不超过 32 MiB"
    return True, "ok"


def upload_to_files_api(file_bytes, filename, purpose="user_data",
                        api_key=None, base_url=FILES_BASE_URL, is_pdf=False):
    """上传文件到 DeepSeek Files API，返回 file_id。

    Args:
        file_bytes: 文件字节内容
        filename: 文件名
        purpose: 必须为 user_data
        api_key: DeepSeek API Key（None 则自动获取）
        base_url: Files API base
        is_pdf: 是否 PDF（影响超时）

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
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError("上传失败 [%d]: %s" % (resp.status_code, resp.text[:200]))
    body = resp.json()
    return body["id"]


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
