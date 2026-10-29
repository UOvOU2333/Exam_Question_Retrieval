"""图片上传与清理服务。"""

import hashlib
import os

from utils_rev.config import IMAGE_DIR, IMAGE_REL_PREFIX


def save_image(uploaded_file) -> str:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    content = uploaded_file.getvalue()
    digest = hashlib.sha256(content).hexdigest()[:16]
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        ext = ".png"
    filename = f"{digest}{ext}"
    filepath = IMAGE_DIR / filename
    if not filepath.exists():
        filepath.write_bytes(content)
    return f"{IMAGE_REL_PREFIX}/{filename}"


def cleanup_images(paths):
    success, failed = [], []
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
                success.append(p)
            elif p:
                failed.append(p)
        except Exception:
            failed.append(p)
    return success, failed


def abs_path(rel_path: str) -> str:
    from utils_rev.config import BASE_DIR
    return str(BASE_DIR / rel_path)
