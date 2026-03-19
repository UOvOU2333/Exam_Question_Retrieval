import sqlite3
from services.question_services import get_conn
from utils.file_utils import extract_image_paths_from_markdown, normalize_image_path, safe_delete_file

DB_PATH = "data/questions.db"


# ======================
# 获取回收站中所有题目的ID
# ======================
def get_questions_in_recycle_bin():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql = """
        SELECT questionID
        FROM questions 
        WHERE isInRecycleBin = 1
    """

    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()

    result = []
    for i in rows:
        result.append(i["questionID"])

    return result


# ======================
# 将选中的单题恢复
# ======================
def restore_the_question(qid):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sql = "UPDATE questions SET isInRecycleBin = 0 WHERE questionID = ?"
    cur.execute(sql, (qid,))

    conn.commit()
    conn.close()

    return qid


# ======================
# 删除单题(彻底删除）
# ======================
def delete_question(qid):
    """
    删除题目及其关联的图片文件
    """
    conn = None
    try:
        conn = get_conn()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. 先获取题目内容，找出所有图片路径
        cur.execute("""
            SELECT content, answer, analysis 
            FROM questions 
            WHERE questionID = ?
        """, (qid,))

        question_data = cur.fetchone()

        if question_data:
            # 收集所有图片路径
            all_image_paths = []

            # 检查每个字段
            for field in ['content', 'answer', 'analysis']:
                text = question_data[field]
                if text:
                    # 提取图片路径
                    img_paths = extract_image_paths_from_markdown(text)

                    # 规范化路径并收集
                    for img_path in img_paths:
                        normalized_path = normalize_image_path(img_path)
                        if normalized_path and normalized_path not in all_image_paths:
                            all_image_paths.append(normalized_path)

            # 2. 删除关联的备注信息（如果有外键约束，需要先删除关联表记录）
            try:
                # 删除题目关联的备注
                cur.execute("DELETE FROM question_notes WHERE question_id = ?", (qid,))
            except sqlite3.OperationalError:
                # 如果表不存在，忽略错误
                pass

            # 3. 删除数据库中的题目记录
            cur.execute("DELETE FROM questions WHERE questionID = ?", (qid,))

            # 4. 提交数据库更改
            conn.commit()

            # 5. 删除物理图片文件
            deleted_files = []
            failed_files = []

            for img_path in all_image_paths:
                if safe_delete_file(img_path):
                    deleted_files.append(img_path)
                else:
                    failed_files.append(img_path)

            # 可以选择记录删除结果
            if deleted_files:
                print(f"成功删除 {len(deleted_files)} 个图片文件")
            if failed_files:
                print(f"有 {len(failed_files)} 个图片文件删除失败")

            return {
                'success': True,
                'question_id': qid,
                'deleted_images': deleted_files,
                'failed_images': failed_files
            }

        else:
            # 题目不存在
            return {
                'success': False,
                'question_id': qid,
                'error': '题目不存在'
            }

    except sqlite3.Error as e:
        # 数据库错误
        if conn:
            conn.rollback()
        return {
            'success': False,
            'question_id': qid,
            'error': f'数据库错误: {str(e)}'
        }
    except Exception as e:
        # 其他错误
        if conn:
            conn.rollback()
        return {
            'success': False,
            'question_id': qid,
            'error': f'未知错误: {str(e)}'
        }
    finally:
        if conn:
            conn.close()
