"""会话错误追踪：只在首个错误时记录。"""

from qserialtool.domain import DomainError, UserFacingError


class SessionErrorTracker:
    """共享的错误槽：记录首个错误，重复失败不覆盖既有错误。"""

    def __init__(self) -> None:
        self._error: UserFacingError | None = None

    @property
    def current(self) -> UserFacingError | None:
        """返回当前记录的错误。"""
        return self._error

    def clear(self) -> None:
        """清空已记录的错误（连接开始时调用）。"""
        self._error = None

    def record(self, error: DomainError) -> bool:
        """记录错误；返回是否为第一个被记录的错误。"""
        if self._error is not None:
            return False
        self._error = error.to_user_facing()
        return True
