"""子站点异常类型。"""


class ValidationError(Exception):
    pass


class PermissionError(Exception):
    pass


class StateTransitionError(Exception):
    pass


class ConcurrentUpdateError(Exception):
    pass


class NotFoundError(Exception):
    pass
