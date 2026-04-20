# note_tools.py
from typing import Optional, List, Dict, Any
from langchain.tools import tool
from services.note_services import (
    create_note_type,
    update_note_type,
    soft_delete_note_type,
    get_note_type,
    get_all_note_types,
    restore_note_type,
    permanently_delete_note_type,
    get_question_notes,
    create_question_note,
    soft_delete_question_note,
)
from services.user_services import get_user_by_id
from chains.loger import trace
import sqlite3

# ---------- 权限辅助函数（同 question_tools） ----------
def _check_read_permission(role: str) -> bool:
    return role in ("viewer", "editor", "admin")

def _check_write_permission(role: str) -> bool:
    return role in ("editor", "admin")

def _check_admin_permission(role: str) -> bool:
    return role == "admin"

# ---------- 辅助函数：将 sqlite3.Row 或 Row 列表转换为字典 ----------
def _row_to_dict(row):
    """将 sqlite3.Row 或 None 转换为字典"""
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return row

def _rows_to_dict_list(rows):
    """将 sqlite3.Row 列表转换为字典列表"""
    if not rows:
        return []
    return [dict(row) if isinstance(row, sqlite3.Row) else row for row in rows]

# ---------- 笔记类型管理 ----------
@tool
def create_note_type_tool(
    type_name: str,
    created_by: int,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    创建一个新的笔记类型（标签）。
    权限：editor / admin
    """

    # ========== 自动解包 LLM 错误传入的字典 ==========
    if isinstance(type_name, dict):
        trace("NoteTools", f"{role} {user_id} AutoUnpackDict", f"type_name is dict: {type_name}")
        # 尝试从字典中提取 type_name，也可能包含 created_by
        new_type_name = type_name.get("type_name") or type_name.get("name")
        new_created_by = type_name.get("created_by") or created_by
        if not new_type_name:
            return "错误：type_name 参数格式不正确，请提供字符串类型名称。"
        return create_note_type_tool(
            type_name=new_type_name,
            created_by=new_created_by,
            user_id=user_id,
            role=role,
        )
    # ================================================

    trace("NoteTools", f"{role} {user_id} CreateNoteType", f"type_name={type_name}")

    if not _check_write_permission(role):
        return "错误：您没有创建笔记类型的权限（需要 editor 或 admin 角色）"

    try:
        type_id = create_note_type(name=type_name, created_by=created_by)
        if type_id:
            trace("NoteTools", f"{role} {user_id} CreateNoteType Result", f"success: type_id={type_id}")
            return f"笔记类型 '{type_name}' 创建成功，ID = {type_id}。"
        else:
            trace("NoteTools", f"{role} {user_id} CreateNoteType Result", f"failed: type_name already exists")
            return f"创建失败：笔记类型 '{type_name}' 可能已存在。"
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} CreateNoteType Error", str(e), level="error")
        return f"创建笔记类型时发生错误：{str(e)}"

@tool
def update_note_type_tool(
    type_id: int,
    new_name: Optional[str] = None,
    updated_by: int = None,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    更新笔记类型的名称。
    权限：editor / admin
    """

    # ========== 自动解包 LLM 错误传入的字典 ==========
    if isinstance(type_id, dict):
        trace("NoteTools", f"{role} {user_id} AutoUnpackDict", f"type_id is dict: {type_id}")
        new_type_id = type_id.get("type_id")
        new_name = type_id.get("new_name") or new_name
        updated_by = type_id.get("updated_by") or updated_by
        if not new_type_id:
            return "错误：type_id 参数格式不正确，请提供整数 ID。"
        return update_note_type_tool(
            type_id=new_type_id,
            new_name=new_name,
            updated_by=updated_by,
            user_id=user_id,
            role=role,
        )
    if isinstance(new_name, dict):
        trace("NoteTools", f"{role} {user_id} AutoUnpackDict", f"new_name is dict: {new_name}")
        new_name = new_name.get("new_name") or new_name.get("name")
    # ================================================

    trace("NoteTools", f"{role} {user_id} UpdateNoteType", f"type_id={type_id}, new_name={new_name}")

    if not _check_write_permission(role):
        return "错误：您没有更新笔记类型的权限（需要 editor 或 admin 角色）"

    if not new_name:
        return "请提供新的类型名称（new_name）。"

    try:
        success = update_note_type(type_id=type_id, name=new_name, updated_by=updated_by)
        if success:
            trace("NoteTools", f"{role} {user_id} UpdateNoteType Result", f"success: type_id={type_id} renamed to {new_name}")
            return f"笔记类型 ID {type_id} 已更新为 '{new_name}'。"
        else:
            trace("NoteTools", f"{role} {user_id} UpdateNoteType Result", f"failed: type_id={type_id} not found or name conflict")
            return f"更新失败：未找到ID为 {type_id} 的未删除笔记类型，或名称 '{new_name}' 已存在。"
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} UpdateNoteType Error", str(e), level="error")
        return f"更新笔记类型时发生错误：{str(e)}"

@tool
def delete_note_type_tool(
    type_id: int,
    updated_by: int,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    软删除笔记类型（移入回收站，可恢复）。
    权限：editor / admin
    """

    trace("NoteTools", f"{role} {user_id} DeleteNoteType", f"type_id={type_id}")

    if not _check_write_permission(role):
        return "错误：您没有删除笔记类型的权限（需要 editor 或 admin 角色）"

    try:
        success = soft_delete_note_type(type_id=type_id, updated_by=updated_by)
        if success:
            trace("NoteTools", f"{role} {user_id} DeleteNoteType Result", f"success: type_id={type_id} soft-deleted")
            return f"笔记类型 ID {type_id} 已软删除。"
        else:
            trace("NoteTools", f"{role} {user_id} DeleteNoteType Result", f"failed: type_id={type_id} not found")
            return f"删除失败：未找到ID为 {type_id} 的未删除笔记类型。"
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} DeleteNoteType Error", str(e), level="error")
        return f"删除笔记类型时发生错误：{str(e)}"

@tool
def restore_note_type_tool(
    type_id: int,
    updated_by: int,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    恢复已软删除的笔记类型。
    权限：admin
    """

    trace("NoteTools", f"{role} {user_id} RestoreNoteType", f"type_id={type_id}")

    if not _check_admin_permission(role):
        return "错误：恢复已删除的笔记类型需要 admin 权限。"

    try:
        success = restore_note_type(type_id=type_id, updated_by=updated_by)
        if success:
            trace("NoteTools", f"{role} {user_id} RestoreNoteType Result", f"success: type_id={type_id} restored")
            return f"笔记类型 ID {type_id} 已恢复。"
        else:
            trace("NoteTools", f"{role} {user_id} RestoreNoteType Result", f"failed: type_id={type_id} not found in deleted")
            return f"恢复失败：未找到ID为 {type_id} 的已删除笔记类型。"
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} RestoreNoteType Error", str(e), level="error")
        return f"恢复笔记类型时发生错误：{str(e)}"

@tool
def permanently_delete_note_type_tool(
    type_id: int,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    永久删除笔记类型（物理删除，不可恢复）。
    权限：admin
    """

    trace("NoteTools", f"{role} {user_id} PermanentlyDeleteNoteType", f"type_id={type_id}") 

    if not _check_admin_permission(role):
        return "错误：永久删除笔记类型需要 admin 权限。"

    try:
        success = permanently_delete_note_type(type_id=type_id)
        if success:
            trace("NoteTools", f"{role} {user_id} PermanentlyDeleteNoteType Result", f"success: type_id={type_id} permanently deleted")
            return f"笔记类型 ID {type_id} 已被永久删除。"
        else:
            trace("NoteTools", f"{role} {user_id} PermanentlyDeleteNoteType Result", f"failed: type_id={type_id} may have associated notes or not exist")
            return f"删除失败：可能该类型下仍有笔记关联，或类型不存在。"
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} PermanentlyDeleteNoteType Error", str(e), level="error")
        return f"永久删除笔记类型时发生错误：{str(e)}"

@tool
def get_note_types_tool(
    include_deleted: bool = False,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    获取所有笔记类型列表（默认只显示未删除的）。
    权限：viewer / editor / admin
    """

    trace("NoteTools", f"{role} {user_id} GetNoteTypes", f"include_deleted={include_deleted}")

    if not _check_read_permission(role):
        return "错误：您没有查看笔记类型的权限（需要 viewer / editor / admin 角色）"

    try:
        types = get_all_note_types(include_deleted=include_deleted)
        # 转换为字典列表，避免 sqlite3.Row 不支持 .get()
        types = _rows_to_dict_list(types)
        if not types:
            trace("NoteTools", f"{role} {user_id} GetNoteTypes Result", "no types found")
            return "未找到任何笔记类型。"
        
        count = len(types)
        trace("NoteTools", f"{role} {user_id} GetNoteTypes Result", f"found {count} types")
        lines = []
        for t in types:
            status = " (已删除)" if t.get("is_deleted") else ""
            lines.append(f"ID {t['id']}: {t['type_name']}{status}")
        return "笔记类型列表：\n" + "\n".join(lines)
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} GetNoteTypes Error", str(e), level="error")
        return f"获取笔记类型时发生错误：{str(e)}"

# ---------- 题目笔记管理 ----------
@tool
def get_question_notes_tool(
    question_id: int,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    获取指定题目下的所有笔记（未删除的）。
    权限：viewer / editor / admin
    """

    trace("NoteTools", f"{role} {user_id} GetQuestionNotes", f"question_id={question_id}")

    if not _check_read_permission(role):
        return "错误：您没有查看笔记的权限（需要 viewer / editor / admin 角色）"

    try:
        notes = get_question_notes(question_id)
        # 转换为字典列表，避免 sqlite3.Row 不支持 .get()
        notes = _rows_to_dict_list(notes)
        if not notes:
            trace("NoteTools", f"{role} {user_id} GetQuestionNotes Result", f"question_id={question_id} has no notes")
            return f"题目 ID {question_id} 下没有任何笔记。"
        
        count = len(notes)
        trace("NoteTools", f"{role} {user_id} GetQuestionNotes Result", f"question_id={question_id} found {count} notes")
        lines = [f"题目 {question_id} 的笔记："]
        for n in notes:
            # 获取创建人用户名
            creator = get_user_by_id(n.get('created_by'))
            creator_name = creator[1] if creator else f"用户{n.get('created_by')}"
            lines.append(f"  [笔记ID {n['note_id']}] 类型：{n['type_name']} (ID:{n['type_id']})")
            lines.append(f"    内容：{n['content'][:100]}...")
            lines.append(f"    创建时间：{n['created_at']}  by {creator_name} (ID:{n['created_by']})")
        return "\n".join(lines)
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} GetQuestionNotes Error", str(e), level="error")
        return f"获取题目笔记时发生错误：{str(e)}"

@tool
def create_question_note_tool(
    question_id: int,
    type_id: int,
    content: str,
    created_by: int,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    为指定题目添加一条笔记。
    权限：editor / admin
    """

    trace("NoteTools", f"{role} {user_id} CreateQuestionNote", f"question_id={question_id}, type_id={type_id}")

    if not _check_write_permission(role):
        return "错误：您没有创建笔记的权限（需要 editor 或 admin 角色）"

    try:
        note_id = create_question_note(
            question_id=question_id,
            type_id=type_id,
            content=content,
            created_by=created_by,
        )
        if note_id:
            trace("NoteTools", f"{role} {user_id} CreateQuestionNote Result", f"success: note_id={note_id}")
            return f"笔记创建成功！笔记ID = {note_id}，关联题目 {question_id}。"
        else:
            trace("NoteTools", f"{role} {user_id} CreateQuestionNote Result", "failed: invalid question_id or type_id")
            return "创建笔记失败，请检查题目ID或笔记类型ID是否正确。"
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} CreateQuestionNote Error", str(e), level="error")
        return f"创建笔记时发生错误：{str(e)}"

@tool
def delete_question_note_tool(
    note_id: int,
    updated_by: int,
    user_id: int = None,
    role: str = None,
) -> str:
    """
    软删除一条笔记（移入回收站）。
    权限：editor / admin
    """

    trace("NoteTools", f"{role} {user_id} DeleteQuestionNote", f"note_id={note_id}")

    if not _check_write_permission(role):
        return "错误：您没有删除笔记的权限（需要 editor 或 admin 角色）"

    try:
        success = soft_delete_question_note(note_id=note_id, updated_by=updated_by)
        if success:
            trace("NoteTools", f"{role} {user_id} DeleteQuestionNote Result", f"success: note_id={note_id} soft-deleted")
            return f"笔记 ID {note_id} 已软删除。"
        else:
            trace("NoteTools", f"{role} {user_id} DeleteQuestionNote Result", f"failed: note_id={note_id} not found")
            return f"删除失败：未找到ID为 {note_id} 的未删除笔记。"
    except Exception as e:
        trace("NoteTools", f"{role} {user_id} DeleteQuestionNote Error", str(e), level="error")
        return f"删除笔记时发生错误：{str(e)}"