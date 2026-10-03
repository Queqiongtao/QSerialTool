"""测试领域包公开接口。"""

from qserialtool import domain


def test_domain_public_api_exports_expected_symbols() -> None:
    expected = {
        "AppConfig",
        "DomainError",
        "ErrorCode",
        "IncrementalTextDecoder",
        "LogRecord",
        "RecordBuffer",
        "SerialConfig",
        "SessionState",
        "SessionStateMachine",
        "TerminalScreen",
        "Transport",
        "encode_text",
        "parse_hex",
    }

    assert expected.issubset(set(domain.__all__))
