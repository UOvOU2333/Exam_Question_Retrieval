import sqlite3
from datetime import datetime

DB_PATH = "data/questions.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def create_note_type(name, created_by):
    """
    创建笔记类型
    :param name: 类型名称
    :param created_by: 创建人ID
    :return: 新创建的类型ID
    """
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO note_types (type_name, created_by)
            VALUES (?, ?)
        """, (name, created_by))
        
        conn.commit()
        type_id = cur.lastrowid
        return type_id
    except sqlite3.IntegrityError:
        # 处理唯一性约束冲突（type_name已存在）
        print(f"错误：笔记类型 '{name}' 已存在")
        return None
    finally:
        conn.close()


def update_note_type(type_id, name=None, updated_by=None):
    """
    更新笔记类型
    :param type_id: 类型ID
    :param name: 新的类型名称（可选）
    :param updated_by: 更新人ID
    :return: 是否更新成功
    """
    if not name and not updated_by:
        return False
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # 构建动态更新语句
        update_fields = []
        params = []
        
        if name:
            update_fields.append("type_name = ?")
            params.append(name)
        
        if updated_by:
            update_fields.append("updated_by = ?")
            params.append(updated_by)
        
        # 添加ID参数
        params.append(type_id)
        
        # 执行更新（updated_at会由触发器自动更新）
        cur.execute(f"""
            UPDATE note_types 
            SET {', '.join(update_fields)}
            WHERE id = ? AND is_deleted = 0
        """, params)
        
        conn.commit()
        success = cur.rowcount > 0
        
        if not success:
            print(f"未找到ID为 {type_id} 的未删除笔记类型")
        
        return success
    except sqlite3.IntegrityError:
        print(f"错误：笔记类型名称 '{name}' 已存在")
        return False
    finally:
        conn.close()


def soft_delete_note_type(type_id, updated_by):
    """
    软删除笔记类型
    :param type_id: 类型ID
    :param updated_by: 执行删除的用户ID
    :return: 是否删除成功
    """
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE note_types 
            SET is_deleted = 1, 
                updated_by = ?
            WHERE id = ? AND is_deleted = 0
        """, (updated_by, type_id))
        
        conn.commit()
        success = cur.rowcount > 0
        
        if not success:
            print(f"未找到ID为 {type_id} 的未删除笔记类型")
        
        return success
    finally:
        conn.close()


def get_note_type(type_id):
    """
    根据ID获取笔记类型（只返回未删除的）
    :param type_id: 类型ID
    :return: 类型信息字典
    """
    conn = get_conn()
    conn.row_factory = sqlite3.Row  # 使返回结果可以通过列名访问
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, type_name, created_by, created_at, 
               updated_by, updated_at
        FROM note_types 
        WHERE id = ? AND is_deleted = 0
    """, (type_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_all_note_types(include_deleted=False):
    """
    获取所有笔记类型
    :param include_deleted: 是否包含已删除的记录
    :return: 类型信息列表
    """
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    if include_deleted:
        cur.execute("""
            SELECT id, type_name, created_by, created_at, 
                   updated_by, updated_at, is_deleted
            FROM note_types 
            ORDER BY id
        """)
    else:
        cur.execute("""
            SELECT id, type_name, created_by, created_at, 
                   updated_by, updated_at, is_deleted
            FROM note_types 
            WHERE is_deleted = 0
            ORDER BY id
        """)
    
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def restore_note_type(type_id, updated_by):
    """
    恢复已软删除的笔记类型
    :param type_id: 类型ID
    :param updated_by: 恢复人ID
    :return: 是否恢复成功
    """
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE note_types 
        SET is_deleted = 0, 
            updated_by = ?
        WHERE id = ? AND is_deleted = 1
    """, (updated_by, type_id))
    
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    
    if not success:
        print(f"未找到ID为 {type_id} 的已删除笔记类型")
    
    return success


def permanently_delete_note_type(type_id):
    """
    永久删除笔记类型（物理删除）- 谨慎使用
    :param type_id: 类型ID
    :return: 是否删除成功
    """
    conn = get_conn()
    cur = conn.cursor()
    
    # 由于有外键约束，需要先检查是否有笔记在使用这个类型
    cur.execute("""
        DELETE FROM note_types 
        WHERE id = ?
    """, (type_id,))
    
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    
    return success