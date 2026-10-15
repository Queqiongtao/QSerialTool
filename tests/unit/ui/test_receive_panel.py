"""测试接收面板的渲染合并与批量追加。"""

from datetime import datetime, timezone

from qserialtool.domain import LogRecord
from qserialtool.ui import ReceivePanel
from qserialtool.ui import receive_panel as receive_panel_module


def _record(text: str, direction: str = "rx") -> LogRecord:
    return LogRecord.from_bytes(
        timestamp_utc=datetime(2026, 10, 4, tzinfo=timezone.utc),
        direction=direction,  # type: ignore[arg-type]
        raw=text.encode(),
        encoding="utf-8",
        session_id="flush",
    )


def test_append_record_merges_bursts_into_one_frame(
    qtbot: object,
    monkeypatch: object,
) -> None:
    panel = ReceivePanel(records_provider=lambda: (), clear_callback=lambda: 0)
    qtbot.addWidget(panel)
    monkeypatch.setattr(receive_panel_module, "_FLUSH_INTERVAL_MS", 10_000)

    panel.append_record(_record("first"))

    # 空闲后的第一条立即渲染，输入回显不等待合并窗口。
    assert "first" in panel.output.toPlainText()

    # 同一窗口内的后续记录先攒着，由定时器到点一次渲染。
    panel.append_record(_record("second"))
    panel.append_record(_record("third"))

    assert "second" not in panel.output.toPlainText()
    assert panel._pending_records

    panel._flush_pending()

    text = panel.output.toPlainText()

    assert text.index("first") < text.index("second") < text.index("third")


def test_filtered_records_skip_render_and_pending_queue(qtbot: object) -> None:
    panel = ReceivePanel(records_provider=lambda: (), clear_callback=lambda: 0)
    qtbot.addWidget(panel)
    panel.tx_check.setChecked(False)

    panel.append_record(_record("sent", "tx"))

    assert panel.output.toPlainText() == ""
    assert panel._pending_records == []


def test_pause_discards_pending_and_resume_rerenders_buffer(
    qtbot: object,
    monkeypatch: object,
) -> None:
    records: list[LogRecord] = [_record("alpha")]
    panel = ReceivePanel(records_provider=lambda: tuple(records), clear_callback=lambda: 0)
    qtbot.addWidget(panel)
    monkeypatch.setattr(receive_panel_module, "_FLUSH_INTERVAL_MS", 10_000)

    panel.append_record(records[0])

    assert "alpha" in panel.output.toPlainText()

    panel.pause_button.setChecked(True)
    records.append(_record("beta"))
    panel.append_record(records[-1])

    assert panel._pending_records == []
    assert "beta" not in panel.output.toPlainText()

    panel.pause_button.setChecked(False)

    assert "beta" in panel.output.toPlainText()


def test_terminal_mode_defers_and_merges_rendering(
    qtbot: object,
    monkeypatch: object,
) -> None:
    panel = ReceivePanel(records_provider=lambda: (), clear_callback=lambda: 0)
    qtbot.addWidget(panel)
    monkeypatch.setattr(receive_panel_module, "_FLUSH_INTERVAL_MS", 10_000)
    panel.set_terminal_mode(True)

    panel.append_record(_record("boot\nready"))

    assert panel.output.toPlainText() == "boot\nready"

    panel.append_record(_record("\nmore"))

    assert panel.output.toPlainText() == "boot\nready"

    panel._flush_pending()

    assert panel.output.toPlainText() == "boot\nready\nmore"
