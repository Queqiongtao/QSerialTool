"""测试接收面板的记录渲染合并、过滤、暂停与清屏。"""

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    build_window,
    connect_session,
    current_tab,
    fragment_styles,
)

from qserialtool.domain import LogRecord
from qserialtool.ui import ReceivePanel, data_colors
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


def test_receive_panel_pause_and_clear_buffer(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        transport.push_read(b"first")
        qtbot.waitUntil(
            lambda: "first" in tab.receive_panel.output.toPlainText(),
            timeout=2000,
        )

        qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
        transport.push_read(b"second")
        qtbot.waitUntil(
            lambda: any(record.raw == b"second" for record in tab.controller.records),
            timeout=2000,
        )
        assert "second" not in tab.receive_panel.output.toPlainText()

        qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: "second" in tab.receive_panel.output.toPlainText(),
            timeout=2000,
        )
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        qtbot.mouseClick(tab.receive_panel.clear_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: tab.controller.records == (), timeout=2000)
        assert tab.receive_panel.output.toPlainText() == ""
    finally:
        tab.controller.close(force=True)
        window.close()


def test_receive_panel_renders_only_recent_records(qtbot: object) -> None:
    timestamp = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    records = tuple(
        LogRecord.from_bytes(
            timestamp_utc=timestamp,
            direction="rx",
            raw=f"line {index}".encode(),
            encoding="utf-8",
            session_id="render-cap",
        )
        for index in range(3000)
    )
    panel = ReceivePanel(
        records_provider=lambda: records,
        clear_callback=lambda: 0,
    )
    qtbot.addWidget(panel)
    panel.render_records()

    assert panel.output.document().blockCount() <= 2003
    text = panel.output.toPlainText()
    assert "已隐藏较早的 1000 条记录" in text
    assert "line 1000" in text
    assert "line 999" not in text


def _color_record(direction: str, text: str, timestamp: datetime) -> LogRecord:
    return LogRecord.from_bytes(
        timestamp_utc=timestamp,
        direction=direction,  # type: ignore[arg-type]
        raw=text.encode(),
        encoding="utf-8",
        session_id="colors",
    )


def test_receive_panel_layers_timestamp_direction_and_payload_colors(qtbot: object) -> None:
    timestamp = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    records = (
        _color_record("rx", "hello", timestamp),
        _color_record("tx", "world", timestamp),
        _color_record("system", "note", timestamp),
    )
    panel = ReceivePanel(records_provider=lambda: records, clear_callback=lambda: 0)
    qtbot.addWidget(panel)
    panel.output.clear_content()
    panel.render_records()

    colors = data_colors()
    local = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    stamp = f"[{local}] "

    # 时间戳灰色、方向前缀着色加粗、正文默认文本色；SYSTEM 行整行灰色。
    assert fragment_styles(panel.output) == [
        (stamp, colors.system, False),
        ("RX: ", colors.rx, True),
        ("hello", colors.text, False),
        (stamp, colors.system, False),
        ("TX: ", colors.tx, True),
        ("world", colors.text, False),
        (f"{stamp}SYSTEM: note", colors.system, False),
    ]


def test_receive_panel_hex_mode_keeps_payload_colors_without_timestamp(qtbot: object) -> None:
    timestamp = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    records = (_color_record("rx", "AB", timestamp),)
    panel = ReceivePanel(records_provider=lambda: records, clear_callback=lambda: 0)
    qtbot.addWidget(panel)
    panel.mode_combo.setCurrentIndex(1)
    panel.timestamp_check.setChecked(False)
    panel.output.clear_content()
    panel.render_records()

    colors = data_colors()

    assert fragment_styles(panel.output) == [
        ("RX: ", colors.rx, True),
        ("41 42", colors.text, False),
    ]


def test_receive_panel_empty_state_overlay(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel

    try:
        assert receive_panel.output.toPlainText() == ""
        assert receive_panel.empty_state.isVisible()
        assert "暂无数据" in receive_panel.empty_state.text()
        assert receive_panel.empty_state.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        # 覆盖层应居中于输出视口（允许 1px 取整误差）。
        viewport = receive_panel.output.viewport()
        expected = (
            (viewport.width() - 1) // 2 - receive_panel.empty_state.width() // 2,
            (viewport.height() - 1) // 2 - receive_panel.empty_state.height() // 2,
        )
        assert abs(receive_panel.empty_state.x() - expected[0]) <= 2
        assert abs(receive_panel.empty_state.y() - expected[1]) <= 2

        connect_session(qtbot, tab)
        transport.push_read(b"hello")
        qtbot.waitUntil(
            lambda: "hello" in receive_panel.output.toPlainText(),
            timeout=2000,
        )
        assert not receive_panel.empty_state.isVisible()

        # 终端视图隐藏提示，切回分栏且缓冲仍有内容时保持隐藏。
        qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)
        assert not receive_panel.empty_state.isVisible()
        qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: "hello" in receive_panel.output.toPlainText(),
            timeout=2000,
        )
        assert not receive_panel.empty_state.isVisible()

        # 清屏后缓冲为空，提示恢复显示。
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        qtbot.mouseClick(receive_panel.clear_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: receive_panel.output.toPlainText() == "", timeout=2000)
        assert receive_panel.empty_state.isVisible()
    finally:
        tab.controller.close(force=True)
        window.close()
