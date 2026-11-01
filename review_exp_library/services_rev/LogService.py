"""操作日志服务。"""

from datetime import datetime

from models_rev.OperationLog import OperationLog
from models_rev.db import get_session

VALID_ACTIONS = {
    "创建", "保存草稿", "提交审核", "发布", "退回",
    "修改", "删除", "归档", "恢复", "备份", "恢复备份",
    "新增用户", "修改角色", "禁用用户", "恢复用户", "永久删除用户",
    "修改用户名", "修改密码",
    "新增分类", "重命名分类", "删除分类", "排序分类",
    "撤回草稿",
}


def record(operator, case_id, action, detail=None, session=None):
    if action not in VALID_ACTIONS:
        raise ValueError(f"非法日志动作: {action}")

    log = OperationLog(
        operator=operator,
        case_id=case_id,
        action=action,
        detail=detail,
        created_at=datetime.utcnow(),
    )
    if session is not None:
        session.add(log)
    else:
        with get_session() as s:
            s.add(log)
