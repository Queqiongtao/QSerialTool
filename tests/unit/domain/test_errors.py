"""测试错误代码和用户错误结构。"""

import pytest

from qserialtool.domain import (
    DomainError,
    ErrorCode,
    HexFormatError,
    InvalidStateTransitionError,
    PortBusyError,
    SessionState,
    UserFacingError,
    ValidationError,
)


def test_domain_error_converts_to_user_facing_error() -> None:
    error = PortBusyError("无法打开 COM3。", diagnostic_id="IO-1")
    result = error.to_user_facing()

    assert result.code is ErrorCode.PORT_BUSY
    assert result.message == "无法打开 COM3。"
    assert result.recoverable is True
    assert result.suggestion == error.default_suggestion
    assert result.diagnostic_id == "IO-1"


def test_domain_error_uses_default_message_and_explicit_suggestion() -> None:
    error = DomainError(suggestion="稍后重试。")

    assert str(error) == "领域操作失败。"
    assert error.to_user_facing().suggestion == "稍后重试。"


def test_specialized_error_codes() -> None:
    assert HexFormatError().to_user_facing().code is ErrorCode.INVALID_HEX
    assert ValidationError().to_user_facing().code is ErrorCode.VALIDATION_ERROR


def test_invalid_state_transition_exposes_context() -> None:
    error = InvalidStateTransitionError(
        SessionState.CONNECTED,
        "connect",
        SessionState.CONNECTING,
    )

    assert error.current_state is SessionState.CONNECTED
    assert error.action == "connect"
    assert error.target_state is SessionState.CONNECTING
    assert "connected" in error.message
    assert error.suggestion == "请刷新会话状态后重试。"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"code": "NOT_A_CODE"},
        {"message": ""},
        {"recoverable": 1},
        {"suggestion": 1},
        {"diagnostic_id": 1},
    ],
)
def test_user_facing_error_rejects_invalid_fields(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "code": ErrorCode.INTERNAL_ERROR,
        "message": "错误",
        "recoverable": False,
        "suggestion": None,
        "diagnostic_id": None,
    }
    values.update(kwargs)
    with pytest.raises(ValidationError):
        UserFacingError(**values)  # type: ignore[arg-type]
