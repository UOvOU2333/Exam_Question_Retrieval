import hashlib
import os
import re

from pathlib import Path

IMAGE_BASE_DIR = "static/images/questions"


# ================================
# 上传图片文件，判断只上传一次，不重复上传
# ================================
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


# ============================================
#     从Markdown文本中提取图片路径
#     支持格式：![alt](path) 或 <img src="path">
# ============================================
def extract_image_paths_from_markdown(text):
    if not text:
        return []

    paths = []

    # 匹配 ![alt](path) 格式
    pattern1 = r'!\[.*?\]\(([^)]+)\)'
    matches1 = re.findall(pattern1, text)
    paths.extend(matches1)

    # 匹配 <img src="path"> 格式
    pattern2 = r'<img.*?src=[\'"]([^\'"]+)[\'"].*?>'
    matches2 = re.findall(pattern2, text)
    paths.extend(matches2)

    # 匹配直接引用的图片路径（如 ./images/abc.jpg）
    pattern3 = r'[\(\'"]((?:\./)?(?:images?/|data/)?[^\s\'"()]+\.(?:png|jpg|jpeg|gif|bmp|svg))[\'")]'
    matches3 = re.findall(pattern3, text, re.IGNORECASE)
    paths.extend(matches3)

    return paths


# =========================
# 规范化图片路径，转换为绝对路径
# =========================
def normalize_image_path(img_path, base_dir=IMAGE_BASE_DIR):

    if not img_path:
        return None

    # 如果已经是绝对路径，直接使用
    if os.path.isabs(img_path):
        return img_path

    # 去除可能的URL前缀或查询参数
    img_path = img_path.split('?')[0]  # 移除URL参数
    img_path = img_path.split('#')[0]  # 移除锚点

    # 如果是相对路径，结合基础目录
    # 移除开头的 ./ 或 .\\
    img_path = re.sub(r'^\./|^\.\\\\', '', img_path)

    # 构建绝对路径
    abs_path = os.path.join(base_dir, os.path.basename(img_path))

    # 如果文件不存在，尝试其他可能的路径
    if not os.path.exists(abs_path):
        # 尝试直接使用原始路径
        alt_path = os.path.join(base_dir, img_path)
        if os.path.exists(alt_path):
            return alt_path

    return abs_path


# ========================
# 安全删除文件，处理可能的异常
# ========================
def safe_delete_file(file_path):
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            print(f"已删除图片文件: {file_path}")  # 可以改为日志记录
            return True
    except PermissionError:
        print(f"权限不足，无法删除文件: {file_path}")
    except Exception as e:
        print(f"删除文件时出错: {file_path}, 错误: {str(e)}")
    return False
