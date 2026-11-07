# utils/permissions.py
"""统一权限定义：角色常量、中文映射、权限矩阵、校验函数。

权限层级（从低到高）：
    experiencer < viewer < advancer < editor < admin

角色说明：
    experiencer  体验用户  仅检索题目/答案，不可查看解析
    viewer       普通用户  检索全部（含解析）
    advancer     高级用户  检索 + 试卷导出
    editor       编辑员    检索 + 上传 + 更新 + 导出 + 回收站
    admin        管理员    全部权限（含用户/备注/卷种管理、删除、AI 自动授权）
"""

# ========== 角色常量 ==========
ROLE_EXPERIENCER = "experiencer"
ROLE_VIEWER = "viewer"
ROLE_ADVANCER = "advancer"
ROLE_EDITOR = "editor"
ROLE_ADMIN = "admin"

# 所有角色（按权限层级从低到高排列）
ALL_ROLES = (
    ROLE_EXPERIENCER,
    ROLE_VIEWER,
    ROLE_ADVANCER,
    ROLE_EDITOR,
    ROLE_ADMIN,
)

# 备注可见范围默认值（全部角色可见）
DEFAULT_VISIBLE_ROLES = ",".join(ALL_ROLES)

# ========== 角色中文映射 ==========
ROLE_NAMES = {
    ROLE_EXPERIENCER: "体验用户",
    ROLE_VIEWER: "普通用户",
    ROLE_ADVANCER: "高级用户",
    ROLE_EDITOR: "编辑员",
    ROLE_ADMIN: "管理员",
}

# ========== 角色英文缩写 ==========
ROLE_EN_SHORT = {
    ROLE_EXPERIENCER: "Experiencer",
    ROLE_VIEWER: "Viwer",
    ROLE_ADVANCER: "Advancer",
    ROLE_EDITOR: "Editor",
    ROLE_ADMIN: "Admin",
}

# ========== 角色权限提示（用户主页展示用）==========
ROLE_PERMISSION_INFO = {
    ROLE_EXPERIENCER: "查看题目与答案",
    ROLE_VIEWER: "查看试题",
    ROLE_ADVANCER: "查看试题、试卷导出",
    ROLE_EDITOR: "管理试题",
    ROLE_ADMIN: "管理用户、管理试题",
}

# ========== 权限矩阵 ==========
# 每个功能点允许的角色集合
PERMISSIONS = {
    "search":            (ROLE_EXPERIENCER, ROLE_VIEWER, ROLE_ADVANCER, ROLE_EDITOR, ROLE_ADMIN),
    "view_analysis":     (ROLE_VIEWER, ROLE_ADVANCER, ROLE_EDITOR, ROLE_ADMIN),
    "export":            (ROLE_ADVANCER, ROLE_EDITOR, ROLE_ADMIN),
    "upload":            (ROLE_EDITOR, ROLE_ADMIN),
    "update":            (ROLE_EDITOR, ROLE_ADMIN),
    "delete":            (ROLE_ADMIN,),
    "recycle_bin":       (ROLE_EDITOR, ROLE_ADMIN),
    "paper_type_change": (ROLE_ADMIN,),
    "user_manage":       (ROLE_ADMIN,),
    "note_type_manage":  (ROLE_ADMIN,),
    "ai_auto":           (ROLE_ADMIN,),
    # 录题 Agent：editor 及以上角色可被授权使用
    "record_agent":      (ROLE_EDITOR, ROLE_ADVANCER, ROLE_ADMIN),
}


# ========== 校验函数（纯函数，不依赖 Streamlit）==========
def has_permission(role, perm):
    """判断角色是否拥有指定权限"""
    return role in PERMISSIONS.get(perm, ())


def can_be_authorized_for_record_agent(role):
    """判断该角色是否可被管理员手动授权使用录题 Agent。

    admin 自动授权无需在白名单，故不在可被授权集合内；
    viewer/experiencer 不可被授权。
    """
    return role in (ROLE_EDITOR, ROLE_ADVANCER)


def can_use_record_agent(role, user_id):
    """判断用户是否可使用录题 Agent（综合角色 + 白名单）。

    admin 直接放行；否则要求角色有 record_agent 权限且在录题 Agent 白名单内。
    为避免循环依赖，此处延迟 import record_agent_auth_services。
    """
    if is_admin(role):
        return True
    if not has_permission(role, "record_agent"):
        return False
    from services.record_agent_auth_services import is_record_agent_enabled
    return is_record_agent_enabled(user_id)


def can_read(role):
    """能否检索题目（所有登录角色）"""
    return has_permission(role, "search")


def can_view_analysis(role):
    """能否查看解析（experiencer 不可；同时作为 AI 工具检索门槛，避免解析泄露）"""
    return has_permission(role, "view_analysis")


def can_write(role):
    """能否上传/更新试题"""
    return has_permission(role, "upload")


def is_admin(role):
    """是否为管理员"""
    return role == ROLE_ADMIN


def role_display_name(role):
    """获取角色中文显示名，未知角色返回原值"""
    return ROLE_NAMES.get(role, role)
