import hashlib
import os

from pathlib import Path


# ===============================
# 上传图片文件，判断只上传一次，不重复上传
# ===============================
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