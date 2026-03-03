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
def search_questions(
    paper_type: str | None = None,
    question_no: str | None = None,
    keyword: str | None = None,
    years: list | None = None,
    field_que: str = "all",
    field_sou: str = "all",
    search_scope: str = "qa",   # "qa" 或 "source"
    fuzzy: bool = True
):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base_sql = """
        SELECT questionID, content, answer, analysis, source, analysis_source,
               year, paper_type, question_no
        FROM questions
    """

    conditions = []
    params = []

    # 卷种
    if paper_type:
        if fuzzy:
            conditions.append("paper_type LIKE ?")
            params.append(f"%{paper_type}%")
        else:
            conditions.append("paper_type = ?")
            params.append(paper_type)

    # 题号
    if question_no:
        if fuzzy:
            conditions.append("question_no LIKE ?")
            params.append(f"%{question_no}%")
        else:
            conditions.append("question_no = ?")
            params.append(question_no)

    # 综合关键词
    if keyword and keyword.strip():
        kw = f"%{keyword}%" if fuzzy else keyword

        keyword_conditions = []

        if search_scope == "qa":
            # 仅搜索题目/答案/解析
            if field_que == "all":
                fields = ["content", "answer", "analysis"]
            else:
                fields = [field_que]

        elif search_scope == "source":
            # 仅搜索来源
            if field_sou == "all":
                fields = ["source", "analysis_source"]
            else:
                fields = [field_sou]
        else:
            fields = []

        for f in fields:
            if fuzzy:
                keyword_conditions.append(f"{f} LIKE ?")
            else:
                keyword_conditions.append(f"{f} = ?")
            params.append(kw)

        if keyword_conditions:
            conditions.append("(" + " OR ".join(keyword_conditions) + ")")

    # 年份
    if years:
        placeholders = ",".join(["?"] * len(years))
        conditions.append(f"year IN ({placeholders})")
        params.extend(years)

    if conditions:
        sql = base_sql + " WHERE " + " AND ".join(conditions) + " ORDER BY created_at DESC"
    else:
        sql = base_sql + " ORDER BY created_at DESC"

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def search_qid(qid):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT questionID, content, answer, analysis, source, analysis_source,
               year, paper_type, question_no
        FROM questions
        WHERE questionID = ?
    """, (qid,))

    row = cur.fetchone()
    conn.close()
    return row

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
