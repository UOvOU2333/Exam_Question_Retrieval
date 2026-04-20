import sqlite3
import uuid
from typing import List, Dict, Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# ------------------------------
# 配置参数
# ------------------------------
SQLITE_DB_PATH = "data/questions.db"      # 原始SQLite题库路径
CHROMA_DB_PATH = "data/rag_chroma_db"     # Chroma向量数据库存储路径
COLLECTION_NAME = "question_bank"         # 集合名称
EMBEDDING_MODEL = "all-MiniLM-L6-v2"      # 本地嵌入模型（轻量、无需API密钥）

# ------------------------------
# 初始化连接
# ------------------------------
# 1. 连接SQLite数据库
sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
sqlite_conn.row_factory = sqlite3.Row   # 使查询结果可按列名访问
cursor = sqlite_conn.cursor()

# 2. 初始化Chroma客户端（持久化模式）
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# 3. 加载本地嵌入模型
embedder = SentenceTransformer(EMBEDDING_MODEL)

# 4. 创建或获取集合（使用余弦相似度）
collection = chroma_client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}   # 余弦相似度检索
)

# ------------------------------
# 辅助函数：构建文本块
# ------------------------------
def build_document_from_question(question_row: Dict[str, Any]) -> str:
    """
    将一道题目的核心信息拼接为自然语言文本块，用于嵌入和检索。
    """
    parts = []
    if question_row.get("content"):
        parts.append(f"题目：{question_row['content']}")
    if question_row.get("answer"):
        parts.append(f"答案：{question_row['answer']}")
    if question_row.get("analysis"):
        parts.append(f"解析：{question_row['analysis']}")
    if question_row.get("source"):
        parts.append(f"来源：{question_row['source']}")
    if question_row.get("year"):
        parts.append(f"年份：{question_row['year']}")
    if question_row.get("paper_type"):
        parts.append(f"试卷类型：{question_row['paper_type']}")
    if question_row.get("question_no"):
        parts.append(f"题号：{question_row['question_no']}")
    return "\n".join(parts)

def build_note_text(note_row: Dict[str, Any]) -> str:
    """
    将用户笔记构建为文本块（包含笔记类型和内容）。
    """
    # 需要额外查询笔记类型名称
    type_name = "未知"
    if note_row.get("type_id"):
        cursor.execute("SELECT type_name FROM note_types WHERE id = ? AND is_deleted = 0", (note_row["type_id"],))
        result = cursor.fetchone()
        if result:
            type_name = result["type_name"]
    content = note_row.get("content", "")
    return f"笔记（{type_name}）：{content}"

# ------------------------------
# 1. 处理题目表 (questions)
# ------------------------------
print("正在处理题目数据...")
cursor.execute("""
    SELECT questionID, content, answer, analysis, source, year, paper_type, question_no
    FROM questions
    WHERE isInRecycleBin = 0 OR isInRecycleBin IS NULL
""")
questions = cursor.fetchall()

question_docs = []
question_metadatas = []
question_ids = []

for q in questions:
    doc = build_document_from_question(dict(q))
    if not doc.strip():
        continue   # 跳过空内容
    # 使用 questionID 作为唯一标识，并生成 Chroma 需要的 ID
    doc_id = f"q_{q['questionID']}"
    metadata = {
        "source_type": "question",
        "question_id": q["questionID"],
        "year": q["year"] or "",
        "paper_type": q["paper_type"] or "",
        "question_no": q["question_no"] or ""
    }
    question_docs.append(doc)
    question_metadatas.append(metadata)
    question_ids.append(doc_id)

if question_docs:
    # 批量生成嵌入（效率更高）
    embeddings = embedder.encode(question_docs, show_progress_bar=True).tolist()
    collection.add(
        ids=question_ids,
        embeddings=embeddings,
        documents=question_docs,
        metadatas=question_metadatas
    )
    print(f"已添加 {len(question_docs)} 道题目")
else:
    print("没有找到有效的题目数据")

# ------------------------------
# 2. 处理用户笔记 (question_notes)
# ------------------------------
print("正在处理笔记数据...")
cursor.execute("""
    SELECT qn.note_id, qn.question_id, qn.type_id, qn.content, nt.type_name
    FROM question_notes qn
    LEFT JOIN note_types nt ON qn.type_id = nt.id AND nt.is_deleted = 0
    WHERE qn.is_deleted = 0
""")
notes = cursor.fetchall()

note_docs = []
note_metadatas = []
note_ids = []

for note in notes:
    doc = build_note_text(dict(note))
    if not doc.strip():
        continue
    doc_id = f"note_{note['note_id']}"
    metadata = {
        "source_type": "note",
        "note_id": note["note_id"],
        "question_id": note["question_id"] or 0,
        "type_name": note["type_name"] or ""
    }
    note_docs.append(doc)
    note_metadatas.append(metadata)
    note_ids.append(doc_id)

if note_docs:
    embeddings = embedder.encode(note_docs, show_progress_bar=True).tolist()
    collection.add(
        ids=note_ids,
        embeddings=embeddings,
        documents=note_docs,
        metadatas=note_metadatas
    )
    print(f"已添加 {len(note_docs)} 条笔记")
else:
    print("没有找到有效的笔记数据")

# ------------------------------
# 清理资源
# ------------------------------
sqlite_conn.close()
print(f"\nRAG数据库构建完成！向量数据库保存位置：{CHROMA_DB_PATH}")
print(f"集合名称：{COLLECTION_NAME}，当前文档总数：{collection.count()}")