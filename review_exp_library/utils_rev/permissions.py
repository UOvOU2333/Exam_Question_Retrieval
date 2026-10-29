"""子站点独立角色与权限矩阵。"""

ROLE_ADMIN = "admin"
ROLE_CHIEF = "chief"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

ALL_ROLES = (ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER)

ROLE_NAMES = {
    ROLE_ADMIN: "管理员",
    ROLE_CHIEF: "总编",
    ROLE_EDITOR: "编辑",
    ROLE_VIEWER: "浏览者",
}

ROLE_EN_SHORT = {
    ROLE_ADMIN: "Admin",
    ROLE_CHIEF: "Chief",
    ROLE_EDITOR: "Editor",
    ROLE_VIEWER: "Viewer",
}

PERMISSIONS = {
    "browse":          (ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER),
    "create":          (ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR),
    "edit":            (ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR),
    "submit":          (ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR),
    "review":          (ROLE_ADMIN, ROLE_CHIEF),
    "archive":         (ROLE_ADMIN, ROLE_CHIEF),
    "restore":         (ROLE_ADMIN, ROLE_CHIEF),
    "delete":          (ROLE_ADMIN, ROLE_CHIEF),
    "backup":          (ROLE_ADMIN, ROLE_CHIEF),
    "manage_members":  (ROLE_ADMIN, ROLE_CHIEF),
    "manage_catalog":  (ROLE_ADMIN, ROLE_CHIEF),
    "self_manage":     (ROLE_ADMIN, ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER),
}


def has_permission(role, perm):
    return role in PERMISSIONS.get(perm, ())


def is_admin(role):
    return role == ROLE_ADMIN


def is_chief(role):
    return role in (ROLE_ADMIN, ROLE_CHIEF)


def is_editor(role):
    return role == ROLE_EDITOR


def role_display_name(role):
    return ROLE_NAMES.get(role, role)
