"""
试卷导出服务：按"年份 + 卷种"查询整套试卷的题目，供导出使用。
"""

import sqlite3

DB_PATH = "data/questions.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def list_years_with_papers():
    """返回有题目的年份列表（降序）。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT year
        FROM questions
        WHERE isInRecycleBin = 0 AND year IS NOT NULL
        ORDER BY year DESC
    """)
    years = [row[0] for row in cur.fetchall()]
    conn.close()
    return years


def list_paper_types_by_year(year: int):
    """返回指定年份下所有卷种（升序），及每种卷种的题目数。"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT paper_type, COUNT(*) AS cnt
        FROM questions
        WHERE isInRecycleBin = 0 AND year = ? AND paper_type IS NOT NULL AND paper_type != ''
        GROUP BY paper_type
        ORDER BY paper_type ASC
    """, (year,))
    rows = [{"paper_type": r["paper_type"], "count": r["cnt"]} for r in cur.fetchall()]
    conn.close()
    return rows


def get_paper_questions(year: int, paper_type: str):
    """
    获取指定年份+卷种的所有题目（不含回收站）。
    按题号数值升序排列。
    返回 list[dict]，字段与 questions 表一致。
    """
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT questionID, content, answer, analysis, source, analysis_source,
               year, paper_type, question_no, created_at
        FROM questions
        WHERE isInRecycleBin = 0
          AND year = ?
          AND paper_type = ?
        ORDER BY CAST(question_no AS INTEGER) ASC, question_no ASC
    """, (year, paper_type))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
