import sqlite3

DB_PATH = "data/questions.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# =====================
# 创建题目（上传）
# =====================
def create_question(content, answer, analysis, source, analysis_source, year, paper_type, question_no):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""INSERT INTO questions
        (content, answer, analysis, source, analysis_source, year, paper_type, question_no)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (content, answer, analysis, source, analysis_source, year, paper_type, question_no))

    qid = cur.lastrowid
    conn.commit()
    conn.close()
    return qid


# =====================
# 单题详情
# =====================
def get_question_detail(question_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
    question = cur.fetchone()

    # tags
    cur.execute("""
        SELECT t.name
        FROM tags t
        JOIN question_tags qt ON t.id = qt.tag_id
        WHERE qt.question_id = ?
    """, (question_id,))
    tags = [r[0] for r in cur.fetchall()]

    # modules
    cur.execute("""
        SELECT m.name
        FROM knowledge_modules m
        JOIN question_modules qm ON m.id = qm.module_id
        WHERE qm.question_id = ?
    """, (question_id,))
    modules = [r[0] for r in cur.fetchall()]

    # used_by
    cur.execute("""
        SELECT u.name
        FROM used_by u
        JOIN question_used_by qu ON u.id = qu.used_by_id
        WHERE qu.question_id = ?
    """, (question_id,))
    used_by = [r[0] for r in cur.fetchall()]

    # remarks
    cur.execute("""
        SELECT content, created_at
        FROM remarks
        WHERE question_id = ?
        ORDER BY created_at DESC
    """, (question_id,))
    remarks = cur.fetchall()

    conn.close()

    return {
        "question": question,
        "tags": tags,
        "modules": modules,
        "used_by": used_by,
        "remarks": remarks
    }


# =====================
# 从数据库查询问题
# =====================
def search_questions(keyword: str, field: str = "all", years: list | None = None):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    kw = f"%{keyword}%"

    base_sql = """
        SELECT questionID, content, answer, analysis, source, analysis_source,
            year, paper_type, question_no
        FROM questions
    """

    conditions = []
    params = []

    # ===== 关键词条件 =====
    if keyword.strip():
        if field != "all":
            conditions.append(f"{field} LIKE ?")
            params.append(kw)
        else:
            conditions.append("""
                (content LIKE ?
                OR answer LIKE ?
                OR analysis LIKE ?)
            """)
            params.extend([kw, kw, kw])

    # ===== 年份条件（支持多选）=====
    if years:
        placeholders = ",".join(["?"] * len(years))
        conditions.append(f"year IN ({placeholders})")
        params.extend(years)

    # ===== 拼接 WHERE =====
    if conditions:
        sql = base_sql + " WHERE " + " AND ".join(conditions) + " ORDER BY created_at DESC"
    else:
        sql = base_sql + " ORDER BY created_at DESC"

    cur.execute(sql, tuple(params))

    rows = cur.fetchall()
    conn.close()

    return rows


# =====================
# 更新单题
# =====================
def update_question(qid, content, answer, analysis, source, analysis_source, year, paper_type, question_no):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE questions SET 
        content = ?, 
        answer = ?, 
        analysis = ?, 
        source = ?, 
        analysis_source = ?,
        year = ?,
        paper_type = ?,
        question_no = ?
    WHERE questionID = ?  
    """, (
        content,
        answer,
        analysis,
        source,
        analysis_source,
        year,
        paper_type,
        question_no,
        qid
    ))

    conn.commit()
    conn.close()

    return qid
