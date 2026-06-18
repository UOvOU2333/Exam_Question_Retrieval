# tools/rag_tool.py
import chromadb
from langchain.tools import tool
from sentence_transformers import SentenceTransformer

from chains.loger import trace

CHROMA_PATH = "data/rag_chroma_db"
COLLECTION_NAME = "question_bank"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# 全局加载模型和集合（避免重复加载）
_embedder = SentenceTransformer(EMBEDDING_MODEL)
_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection = _client.get_collection(COLLECTION_NAME)

def _check_read_permission(role: str) -> bool:
    return role in ("viewer", "editor", "admin")

@tool
def rag_search_tool(query: str, user_id: int = None, role: str = None) -> str:
    """
    使用语义检索（RAG）在题目库和笔记库中查找与问题最相关的内容。
    返回相关的题目原文、答案、解析或笔记。
    权限：viewer / editor / admin
    """
    
    trace("RAGTools", f"{role} {user_id} Search", f"query={query}")

    if not _check_read_permission(role):
        return "错误：您没有使用 RAG 检索的权限（需要 viewer / editor / admin 角色）"
    
    try:
        results = _collection.query(query_texts=[query], n_results=5)
        if not results['documents'] or not results['documents'][0]:
            return "未找到与您问题相关的题目或笔记。"
        
        output = []
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            source_type = meta.get('source_type', 'unknown')
            if source_type == 'question':
                qid = meta.get('question_id', '?')
                output.append(f"[题目 {qid}]\n{doc[:500]}...")
            else:
                nid = meta.get('note_id', '?')
                qid = meta.get('question_id', '?')
                output.append(f"[笔记 {nid} (关联题目 {qid})]\n{doc[:500]}...")
        return "\n\n".join(output)
    except Exception as e:
        return f"RAG 检索失败：{str(e)}"