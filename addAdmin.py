import sqlite3, hashlib, datetime

conn = sqlite3.connect("data/questions.db")
cur = conn.cursor()

pwd = hashlib.sha256("admin123".encode()).hexdigest()

cur.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,          -- admin / editor / viewer
    created_at TEXT
);

''')
conn.commit()

cur.execute("""
INSERT INTO users (username, password_hash, role, created_at)
VALUES (?, ?, ?, ?)
""", ("admin", pwd, "admin", datetime.datetime.now().isoformat()))

conn.commit()

cur.execute("""
CREATE TABLE IF NOT EXISTS questions (
    questionID INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    answer TEXT NOT NULL,
    analysis TEXT NOT NULL,
    source TEXT NOT NULL,
    analysis_source TEXT NOT NULL,
    created_at DATE DEFAULT CURRENT_DATE
);
""")

conn.close()
