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
        "SELECT username, password_hash, role FROM users WHERE username = ?",
        (username,)
    )
    row = cur.fetchone()
    conn.commit()
    conn.close()

    if not row:
        return False, None

    username_db, password_hash_db, role = row
    if hash_password(password) == password_hash_db:
        return True, role

    return False, None

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def get_all_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created_at FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows


def create_user(username, password_hash, role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (username, password_hash, role, created_at)
        VALUES (?, ?, ?, ?)
    """, (username, password_hash, role, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def update_user_role(user_id, role):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
