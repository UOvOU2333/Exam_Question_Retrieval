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
# 从数据库查询问题
# =====================
def search_questions(
    paper_type: str | None = None,
    question_no: str | None = None,
    keyword: str | None = None,
    years: list | None = None,
    field_que: list | None = None,
    field_sou: list | None = None,
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

    # 默认条件：不在回收站中
    conditions.append("isInRecycleBin = 0")

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
            if not field_que:
                fields = ["content", "answer", "analysis"]
            else:
                fields = field_que

        elif search_scope == "source":
            # 仅搜索来源
            if not field_sou:
                fields = ["source", "analysis_source"]
            else:
                fields = field_sou
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


# =====================
# 单题移到回收站
# =====================
def move_to_recycle_bin(qid):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE questions SET isInRecycleBin = 1
    WHERE questionID = ?
    """, (qid,))

    conn.commit()
    conn.close()

    return qid


# =====================
# 删除单题(彻底删除）
# =====================
def delete_question(qid):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    DELETE FROM questions WHERE questionID = ?
    """, (qid,))

    conn.commit()
    conn.close()

    return qid
