import sqlite3

from tools.exam_type_utils import (
    get_new_textbook_sql_condition,
    detect_question_type,
    knowledge_modules_to_str,
)

DB_PATH = "data/questions.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# =====================
# 创建题目（上传）
# =====================
def create_question(content, answer, analysis, source, analysis_source, year, paper_type, question_no,
                    question_type=None, knowledge_modules=None):
    conn = get_conn()
    cur = conn.cursor()

    km_str = knowledge_modules_to_str(knowledge_modules)

    cur.execute("""INSERT INTO questions
        (content, answer, analysis, source, analysis_source, year, paper_type, question_no,
         question_type, knowledge_modules)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (content, answer, analysis, source, analysis_source, year, paper_type, question_no,
          question_type, km_str))

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
    field_que: str = "all",
    field_sou: str = "all",
    search_scope: str = "qa",   # "qa" 或 "source"
    no_fuzzy: bool = False,
    new_textbook_only: bool = False,
    question_type: str | None = None,
    knowledge_modules: list | None = None,
):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base_sql = """
        SELECT questionID, content, answer, analysis, source, analysis_source,
               year, paper_type, question_no, question_type, knowledge_modules
        FROM questions 
    """

    conditions = []
    params = []

    # 默认条件：不在回收站中
    conditions.append("isInRecycleBin = 0")

    # 卷种
    if paper_type:
        # if fuzzy:
        #    conditions.append("paper_type LIKE ?")
        #    params.append(f"%{paper_type}%")
        # else:
        #    conditions.append("paper_type = ?")
        #    params.append(paper_type)
        conditions.append("paper_type LIKE ?")
        params.append(f"%{paper_type}%")

    # 题号
    if question_no:
        if no_fuzzy:
            conditions.append("question_no LIKE ?")
            params.append(f"%{question_no}%")
        else:
            conditions.append("question_no = ?")
            params.append(question_no)

    # 综合关键词
    if keyword and keyword.strip():
        # kw = f"%{keyword}%" if fuzzy else keyword
        kw = f"%{keyword}%"

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
            # if fuzzy:
            #     keyword_conditions.append(f"{f} LIKE ?")
            # else:
            #     keyword_conditions.append(f"{f} = ?")
            keyword_conditions.append(f"{f} LIKE ?")
            params.append(kw)

        if keyword_conditions:
            conditions.append("(" + " OR ".join(keyword_conditions) + ")")

    # 年份
    if years:
        placeholders = ",".join(["?"] * len(years))
        conditions.append(f"year IN ({placeholders})")
        params.extend(years)

    # 新教材筛选
    if new_textbook_only:
        conditions.append(get_new_textbook_sql_condition())

    # 题型筛选
    if question_type:
        conditions.append("question_type = ?")
        params.append(question_type)

    # 知识模块筛选（多选，模块名互不包含，LIKE 安全）
    if knowledge_modules:
        km_conditions = []
        for km in knowledge_modules:
            km_conditions.append("knowledge_modules LIKE ?")
            params.append(f"%{km}%")
        conditions.append("(" + " OR ".join(km_conditions) + ")")

    # 构建最终 SQL
    sql = base_sql
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
        
    # 排序规则：年份降序，卷种升序，题号数值升序
    sql += " ORDER BY year DESC, paper_type ASC, CAST(question_no AS INTEGER) ASC"

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()

    result = [row["questionID"] for row in rows]
    return result


def get_question_by_id(qid):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT questionID, content, answer, analysis, source, analysis_source,
               year, paper_type, question_no, isInRecycleBin,
               question_type, knowledge_modules
        FROM questions
        WHERE questionID = ?
    """, (qid,))

    row = cur.fetchone()
    conn.close()
    return row


# =====================
# 更新单题
# =====================
def update_question(qid, content, answer, analysis, source, analysis_source, year, paper_type, question_no,
                    question_type=None, knowledge_modules=None):
    conn = get_conn()
    cur = conn.cursor()

    km_str = knowledge_modules_to_str(knowledge_modules)

    cur.execute("""
    UPDATE questions SET 
        content = ?, 
        answer = ?, 
        analysis = ?, 
        source = ?, 
        analysis_source = ?,
        year = ?,
        paper_type = ?,
        question_no = ?,
        question_type = ?,
        knowledge_modules = ?
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
        question_type,
        km_str,
        qid
    ))

    conn.commit()
    conn.close()

    return qid


# =====================
# 批量自动检测并回填题型（仅回填当前为空的题目）
# =====================
def batch_detect_and_fill_question_type():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT questionID, content, answer, question_no, question_type
        FROM questions
        WHERE isInRecycleBin = 0 AND (question_type IS NULL OR question_type = '')
    """)
    rows = cur.fetchall()

    stats = {"选择题": 0, "非选择题": 0, "跳过": 0}
    for row in rows:
        qtype = detect_question_type(row["content"], row["answer"], row["question_no"])
        if qtype:
            cur.execute(
                "UPDATE questions SET question_type = ? WHERE questionID = ?",
                (qtype, row["questionID"]),
            )
            stats[qtype] += 1
        else:
            stats["跳过"] += 1

    conn.commit()
    conn.close()
    return stats


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
# 根据备注信息检索题目
# =====================
def search_by_note(type_id: int | None = None,
                   content: str | None = None,
                   created_by: str | None = None,
                   fuzzy: bool = True):
    """
    根据备注信息检索题目
    支持按标签、内容、备注人搜索，可模糊匹配
    返回满足条件的 questionID 列表
    """

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base_sql = """
        SELECT DISTINCT q.questionID
        FROM questions q
        JOIN question_notes n ON q.questionID = n.question_id
        LEFT JOIN users u ON n.created_by = u.id
        WHERE q.isInRecycleBin = 0
    """

    conditions = []
    params = []

    # 标签搜索
    if type_id:
    # if type_id and type_id.strip():
        conditions.append("n.type_id = ?")
        params.append(type_id)

    # 内容搜索
    if content and content.strip():
        if fuzzy:
            conditions.append("n.content LIKE ?")
            params.append(f"%{content}%")
        else:
            conditions.append("n.content = ?")
            params.append(content)

    # 备注人搜索（支持用户名或用户ID）
    if created_by:
        if fuzzy:
            conditions.append("(u.username LIKE ? OR n.created_by LIKE ?)")
            params.append(f"%{created_by}%")
            params.append(f"%{created_by}%")
        else:
            conditions.append("(u.username = ? OR n.created_by = ?)")
            params.append(created_by)
            params.append(created_by)

    if conditions:
        sql = base_sql + " AND " + " AND ".join(conditions) + " ORDER BY n.created_at DESC"
    else:
        # 若无任何条件，返回空列表
        conn.close()
        return []

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    conn.close()

    # 提取 questionID 列表
    result = [row["questionID"] for row in rows]
    return result
