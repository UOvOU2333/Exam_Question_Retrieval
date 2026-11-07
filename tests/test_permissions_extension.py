"""权限矩阵扩展单元测试。"""
from utils.permissions import (
    has_permission,
    is_admin,
    can_be_authorized_for_record_agent,
    ROLE_EDITOR,
    ROLE_ADVANCER,
    ROLE_ADMIN,
    ROLE_VIEWER,
    ROLE_EXPERIENCER,
)


def test_record_agent_permission_point():
    assert has_permission("editor", "record_agent") is True
    assert has_permission("advancer", "record_agent") is True
    assert has_permission("admin", "record_agent") is True
    assert has_permission("viewer", "record_agent") is False
    assert has_permission("experiencer", "record_agent") is False


def test_can_be_authorized():
    assert can_be_authorized_for_record_agent(ROLE_EDITOR) is True
    assert can_be_authorized_for_record_agent(ROLE_ADVANCER) is True
    # admin 自动授权，不在可被授权集合
    assert can_be_authorized_for_record_agent(ROLE_ADMIN) is False
    assert can_be_authorized_for_record_agent(ROLE_VIEWER) is False
    assert can_be_authorized_for_record_agent(ROLE_EXPERIENCER) is False


def test_is_admin():
    assert is_admin("admin") is True
    assert is_admin("editor") is False
