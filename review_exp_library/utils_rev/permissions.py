"""子站点独立角色与权限矩阵。"""

ROLE_CHIEF = "chief"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

ALL_ROLES = (ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER)

ROLE_NAMES = {
    ROLE_CHIEF: "总编",
    ROLE_EDITOR: "编辑",
    ROLE_VIEWER: "浏览者",
}

PERMISSIONS = {
    "browse":          (ROLE_CHIEF, ROLE_EDITOR, ROLE_VIEWER),
    "create":          (ROLE_CHIEF, ROLE_EDITOR),
    "edit":            (ROLE_CHIEF, ROLE_EDITOR),
    "submit":          (ROLE_CHIEF, ROLE_EDITOR),
    "review":          (ROLE_CHIEF,),
    "archive":         (ROLE_CHIEF,),
    "restore":         (ROLE_CHIEF,),
    "delete":          (ROLE_CHIEF,),
    "backup":          (ROLE_CHIEF,),
    "manage_members":  (ROLE_CHIEF,),
}


def has_permission(role, perm):
    return role in PERMISSIONS.get(perm, ())


def is_chief(role):
    return role == ROLE_CHIEF


def is_editor(role):
    return role == ROLE_EDITOR


def role_display_name(role):
    return ROLE_NAMES.get(role, role)
