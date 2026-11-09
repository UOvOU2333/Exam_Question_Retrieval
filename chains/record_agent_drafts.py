"""录题 Agent 草稿/撤销栈/图片库/PDF库/片段/匹配草稿的 session_state 封装。

所有数据存 st.session_state，按 session_id 隔离，会话结束自动清理。

封装类：
  - DraftStore          录题草稿区（pending → committed/discarded，上限 20）
  - UndoStack           撤销/重做栈（LIFO，深度上限 50）
  - SessionImageGallery 会话图片库（file_id 归属校验）
  - SessionPdfLibrary   会话 PDF 库
  - PdfFragmentStore    PDF 原文片段（供对照预览）
  - MatchDraftStore     评分细则匹配草稿（pending/skipped/low_confidence/manual_match/committed/discarded）

草稿丢失恢复说明：
  草稿存 st.session_state，会话异常中断时未确认草稿自动丢弃（spec 4.2.4）。
  已确认提交记录保留在正式题库与 operation_logs（含草稿快照）。
  撤销栈会话结束清空，已提交记录不受影响。
"""
import streamlit as st
from datetime import datetime

# 草稿数上限
DRAFT_MAX = 20
# 撤销栈深度上限
UNDO_MAX = 50


def _now():
    return datetime.now().isoformat()


class DraftStore:
    """录题草稿区。草稿 ID 格式 draft-N，状态 pending/committed/discarded。"""

    def __init__(self, session_id):
        self.session_id = session_id
        self._key = "record_drafts_%s" % session_id
        self._seq_key = "record_draft_seq_%s" % session_id

    def _drafts(self):
        return st.session_state.setdefault(self._key, [])

    def _next_id(self):
        seq = st.session_state.get(self._seq_key, 0) + 1
        st.session_state[self._seq_key] = seq
        return "draft-%d" % seq

    def add(self, draft_type, snapshot_after, target_question_id=None, snapshot_before=None):
        """新增草稿。超 DRAFT_MAX 拒绝返回 None。"""
        drafts = self._drafts()
        if len([d for d in drafts if d["status"] == "pending"]) >= DRAFT_MAX:
            return None
        draft_id = self._next_id()
        drafts.append({
            "draft_id": draft_id,
            "draft_type": draft_type,
            "target_question_id": target_question_id,
            "snapshot_before": snapshot_before,
            "snapshot_after": snapshot_after,
            "status": "pending",
            "created_at": _now(),
        })
        return draft_id

    def get(self, draft_id):
        for d in self._drafts():
            if d["draft_id"] == draft_id:
                return d
        return None

    def update_snapshot(self, draft_id, snapshot_updates):
        """更新草稿 snapshot_after 字段（用户在审核界面编辑草稿）。

        仅 pending 状态可编辑。snapshot_updates 为要覆盖的字段字典。
        """
        d = self.get(draft_id)
        if not d or d["status"] != "pending":
            return False
        d["snapshot_after"].update(snapshot_updates)
        d["edited_at"] = _now()
        return True

    def list_pending(self):
        return [d for d in self._drafts() if d["status"] == "pending"]

    def list_all(self):
        return list(self._drafts())

    def commit(self, draft_id):
        """标记已提交，返回草稿快照供服务层写库。"""
        for d in self._drafts():
            if d["draft_id"] == draft_id and d["status"] == "pending":
                d["status"] = "committed"
                d["committed_at"] = _now()
                return d
        return None

    def discard(self, draft_id):
        for d in self._drafts():
            if d["draft_id"] == draft_id and d["status"] == "pending":
                d["status"] = "discarded"
                d["discarded_at"] = _now()
                return True
        return False


class UndoStack:
    """撤销/重做栈，LIFO，深度上限 UNDO_MAX。超限最早归档只读。"""

    def __init__(self, session_id):
        self.session_id = session_id
        self._key = "record_undo_%s" % session_id
        self._redo_key = "record_redo_%s" % session_id

    def _stack(self):
        return st.session_state.setdefault(self._key, [])

    def _redo(self):
        return st.session_state.setdefault(self._redo_key, [])

    def push(self, op_type, target_id, snapshot_before, snapshot_after):
        stack = self._stack()
        stack.append({
            "op_type": op_type,
            "target_id": target_id,
            "snapshot_before": snapshot_before,
            "snapshot_after": snapshot_after,
            "created_at": _now(),
        })
        # 超限最早归档（只读保留，但不再可撤销）
        if len(stack) > UNDO_MAX:
            stack.pop(0)
        return True

    def pop(self):
        stack = self._stack()
        if not stack:
            return None
        return stack.pop()

    def peek(self):
        stack = self._stack()
        return stack[-1] if stack else None

    def push_redo(self, op):
        self._redo().append(op)

    def pop_redo(self):
        redo = self._redo()
        if not redo:
            return None
        return redo.pop()

    def list_all(self):
        return list(self._stack())

    def clear(self):
        st.session_state[self._key] = []
        st.session_state[self._redo_key] = []


class SessionImageGallery:
    """会话图片库，file_id 归属校验。"""

    def __init__(self, session_id):
        self.session_id = session_id
        self._key = "record_images_%s" % session_id

    def _items(self):
        return st.session_state.setdefault(self._key, [])

    def add(self, file_id, filename, bytes_size):
        # 去重
        if self.contains(file_id):
            return False
        now = _now()
        self._items().append({
            "file_id": file_id,
            "filename": filename,
            "bytes_size": bytes_size,
            "added_at": now,
            # 最后使用时间：Agent 对话引用图片时刷新，用于“最后使用后 24 小时”过期判断
            "last_used_at": now,
            "deleted": False,
        })
        return True

    def touch(self, file_id):
        """刷新图片最后使用时间。"""
        for it in self._items():
            if it["file_id"] == file_id and not it["deleted"]:
                it["last_used_at"] = _now()
                return True
        return False

    def contains(self, file_id):
        """归属校验：file_id 在本会话且未删除。"""
        for it in self._items():
            if it["file_id"] == file_id and not it["deleted"]:
                return True
        return False

    def remove(self, file_id):
        for it in self._items():
            if it["file_id"] == file_id and not it["deleted"]:
                it["deleted"] = True
                it["deleted_at"] = _now()
                return True
        return False

    def list_all(self):
        return [it for it in self._items() if not it["deleted"]]


class SessionPdfLibrary:
    """会话 PDF 库。

    PDF 不直接上传 Files API（DeepSeek 不支持 PDF），而是每页渲染为 PNG
    图片上传到 Files API，page_file_ids 存储每页图片的 file_id 列表，
    供 LLM 视觉理解。file_id 为本地标识 local-pdf-xxx。
    """

    def __init__(self, session_id):
        self.session_id = session_id
        self._key = "record_pdfs_%s" % session_id

    def _items(self):
        return st.session_state.setdefault(self._key, [])

    def add(self, file_id, filename, bytes_size, page_count, mode, page_file_ids=None):
        if self.contains(file_id):
            return False
        now = _now()
        self._items().append({
            "file_id": file_id,
            "filename": filename,
            "bytes_size": bytes_size,
            "page_count": page_count,
            "mode": mode,
            "page_file_ids": page_file_ids or [],
            # 页号 -> Files API file_id（按需分批渲染上传）
            "page_file_map": {},
            # 已处理页号（交给 Agent 处理过）
            "processed_pages": [],
            # 当前批次页号（页面传给 Agent 的范围）
            "active_pages": [],
            "expired": False,
            "added_at": now,
            # 最后使用时间：加载批次/对话引用页图时刷新
            "last_used_at": now,
            # 页图最近一次上传时间（用于远端硬过期保护）
            "page_files_uploaded_at": None,
            "deleted": False,
        })
        return True

    def touch(self, file_id):
        """刷新 PDF 最后使用时间。"""
        it = self.get(file_id)
        if not it:
            return False
        it["last_used_at"] = _now()
        return True

    def add_page_files(self, file_id, page_files):
        """记录一批已上传的页图。

        Args:
            file_id: PDF 本地标识
            page_files: list[tuple[int, str]]，[(页号, Files API file_id)]
        """
        it = self.get(file_id)
        if not it:
            return False
        page_map = it.setdefault("page_file_map", {})
        for page_no, fid in page_files:
            page_map[str(page_no)] = fid
            if fid not in it["page_file_ids"]:
                it["page_file_ids"].append(fid)
        now = _now()
        it["expired"] = False
        it["last_used_at"] = now
        it["page_files_uploaded_at"] = now
        return True

    def get_page_file_ids(self, file_id):
        """获取某 PDF 已上传的页面图片 file_id 列表（所有批次）。"""
        it = self.get(file_id)
        return it.get("page_file_ids", []) if it else []

    def get_page_file_ids_in_range(self, file_id, page_start, page_end):
        """获取某 PDF 指定页范围内已上传的 file_id（未上传的页跳过）。"""
        it = self.get(file_id)
        if not it:
            return []
        page_map = it.get("page_file_map", {})
        result = []
        for page_no in range(int(page_start), int(page_end) + 1):
            fid = page_map.get(str(page_no))
            if fid:
                result.append(fid)
        return result

    def set_active_pages(self, file_id, page_nos):
        """设置当前批次页号（供页面过滤传给 Agent 的图片）。"""
        it = self.get(file_id)
        if not it:
            return False
        it["active_pages"] = sorted({int(n) for n in page_nos})
        return True

    def get_active_pages(self, file_id):
        it = self.get(file_id)
        return list(it.get("active_pages", [])) if it else []

    def get_active_page_file_ids(self, file_id):
        """按当前批次页号列表获取已上传的 file_id（支持非连续页号）。"""
        it = self.get(file_id)
        if not it:
            return []
        page_map = it.get("page_file_map", {})
        result = []
        for page_no in it.get("active_pages", []):
            fid = page_map.get(str(page_no))
            if fid:
                result.append(fid)
        return result

    def mark_processed(self, file_id, page_nos):
        """标记页号已处理（同一页重复标记自动去重）。"""
        it = self.get(file_id)
        if not it:
            return False
        processed = set(it.get("processed_pages", []))
        processed.update(int(n) for n in page_nos)
        it["processed_pages"] = sorted(processed)
        return True

    def clear_page_files(self, file_id, expired=True):
        """清空已上传页图与处理状态，保留本地 PDF（供重新选批次渲染）。

        用于恢复会话时检测到 Files API 文件已过期。
        """
        it = self.get(file_id)
        if not it:
            return False
        it["page_file_ids"] = []
        it["page_file_map"] = {}
        it["active_pages"] = []
        it["processed_pages"] = []
        it["page_files_uploaded_at"] = None
        it["expired"] = expired
        return True

    def all_page_file_ids(self):
        """获取所有未删除 PDF 已上传的页面图片 file_id（扁平列表）。"""
        result = []
        for it in self._items():
            if not it["deleted"]:
                result.extend(it.get("page_file_ids", []))
        return result

    def contains(self, file_id):
        for it in self._items():
            if it["file_id"] == file_id and not it["deleted"]:
                return True
        return False

    def get(self, file_id):
        for it in self._items():
            if it["file_id"] == file_id and not it["deleted"]:
                return it
        return None

    def remove(self, file_id):
        """标记删除并返回 page_file_ids（供调用方删除 Files API 上的图片）。"""
        for it in self._items():
            if it["file_id"] == file_id and not it["deleted"]:
                it["deleted"] = True
                it["deleted_at"] = _now()
                return it.get("page_file_ids", [])
        return None

    def list_all(self):
        return [it for it in self._items() if not it["deleted"]]


class PdfFragmentStore:
    """PDF 原文片段，供对照预览。片段 ID 格式 pdf-frag-N。"""

    def __init__(self, session_id):
        self.session_id = session_id
        self._key = "record_fragments_%s" % session_id
        self._seq_key = "record_fragment_seq_%s" % session_id

    def _items(self):
        return st.session_state.setdefault(self._key, [])

    def _next_id(self):
        seq = st.session_state.get(self._seq_key, 0) + 1
        st.session_state[self._seq_key] = seq
        return "pdf-frag-%d" % seq

    def add(self, source_file_id, page_range, text_content, table_markdown="", question_no_hint=None, region="question"):
        frag_id = self._next_id()
        self._items().append({
            "fragment_id": frag_id,
            "source_file_id": source_file_id,
            "page_range": page_range,
            "text_content": text_content,
            "table_markdown": table_markdown,
            "question_no_hint": question_no_hint,
            "region": region,
            "created_at": _now(),
        })
        return frag_id

    def get(self, fragment_id):
        for f in self._items():
            if f["fragment_id"] == fragment_id:
                return f
        return None

    def list_by_file(self, file_id):
        return [f for f in self._items() if f["source_file_id"] == file_id]


class MatchDraftStore:
    """评分细则匹配草稿。

    状态流转：pending → skipped/low_confidence/manual_match/similar/committed/discarded
    similar 表示该题已有基本一致的同类备注，由用户选择覆盖/追加/跳过。
    """

    def __init__(self, session_id):
        self.session_id = session_id
        self._key = "record_matches_%s" % session_id
        self._seq_key = "record_match_seq_%s" % session_id

    def _items(self):
        return st.session_state.setdefault(self._key, [])

    def _next_id(self):
        seq = st.session_state.get(self._seq_key, 0) + 1
        st.session_state[self._seq_key] = seq
        return "match-%d" % seq

    def add(self, source_file_id, rubric_content, rubric_question_no=None,
            rubric_knowledge=None, matched_question_id=None, match_features=None,
            confidence=0.0, note_type_id=None, existing_note_id=None,
            existing_content=None, similarity=None):
        match_id = self._next_id()
        self._items().append({
            "match_id": match_id,
            "source_file_id": source_file_id,
            "rubric_content": rubric_content,
            "rubric_question_no": rubric_question_no,
            "rubric_knowledge": rubric_knowledge,
            "matched_question_id": matched_question_id,
            "match_features": match_features or [],
            "confidence": confidence,
            "note_type_id": note_type_id,
            "existing_note_id": existing_note_id,
            "existing_content": existing_content,
            "similarity": similarity,
            "status": "pending",
            "revise_action": None,
            "created_at": _now(),
        })
        return match_id

    def get(self, match_id):
        for m in self._items():
            if m["match_id"] == match_id:
                return m
        return None

    def update_status(self, match_id, status, revise_action=None):
        for m in self._items():
            if m["match_id"] == match_id:
                m["status"] = status
                if revise_action is not None:
                    m["revise_action"] = revise_action
                return True
        return False

    def update_match(self, match_id, matched_question_id=None, confidence=None, status=None):
        """人工修正匹配结果。"""
        for m in self._items():
            if m["match_id"] == match_id:
                if matched_question_id is not None:
                    m["matched_question_id"] = matched_question_id
                if confidence is not None:
                    m["confidence"] = confidence
                if status is not None:
                    m["status"] = status
                return True
        return False

    def list_pending(self):
        return [m for m in self._items() if m["status"] == "pending"]

    def list_by_status(self, status):
        return [m for m in self._items() if m["status"] == status]

    def list_all(self):
        return list(self._items())
