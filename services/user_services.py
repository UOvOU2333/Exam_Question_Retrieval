import sqlite3
import sqlite3
import hashlib
from datetime import datetime

DB_PATH = "./data/questions.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate(username, password):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, username, password_hash, role FROM users WHERE username = ? AND is_deleted = 0",
        (username,)
    )
    row = cur.fetchone()
    conn.commit()
    conn.close()

    if not row:
        return False, None, None

    id, username_db, password_hash_db, role = row
    if hash_password(password) == password_hash_db:
        return True, role, id

    return False, None, None


def get_all_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created_at FROM users WHERE is_deleted = 0 ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_users_with_deleted():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def create_user(username, password_hash, role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (username, password_hash, role, created_at, is_deleted)
        VALUES (?, ?, ?, ?, 0)
    """, (username, password_hash, role, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def update_user_role(user_id, role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users 
        SET role = ?,
        updated_at = datetime('now','localtime')
        WHERE id = ?
        """, (role, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def soft_delete_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    sql = """
    UPDATE users
    SET is_deleted = 1,
        updated_at = datetime('now','localtime')
    WHERE id = ?
    """
    cur.execute(sql, (user_id,))
    conn.commit()
    conn.close()


def restore_user(conn, user_id):
    conn = get_conn()
    cur = conn.cursor()
    sql = """
    UPDATE users
    SET is_deleted = 0,
        updated_at = datetime('now','localtime')
    WHERE id = ?
    """
    cur.execute(sql, (user_id,))
    conn.commit()
    conn.close()
