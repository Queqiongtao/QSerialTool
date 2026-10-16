"""测试接收面板的渲染合并、批量追加与分栏视图。"""

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    build_window,
    connect_session,
    current_tab,
    cursor_point,
    fragment_styles,
    mouse_drag,
    mouse_press,
    mouse_release,
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


def test_receive_context_menu_only_offers_copy_and_select_all(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        split_menu = tab.receive_panel.output._build_context_menu()
        assert [action.text() for action in split_menu.actions()] == ["复制", "全选"]
        assert split_menu.actions()[0].isEnabled() is False

        tab.set_view_mode("terminal", persist=False)
        terminal_menu = tab.receive_panel.output._build_context_menu()
        assert [action.text() for action in terminal_menu.actions()] == ["复制", "全选"]

        cursor = tab.receive_panel.output.textCursor()
        cursor.insertText("draft")
        tab.receive_panel.output.setTextCursor(cursor)
        cursor.setPosition(0)
        cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
        tab.receive_panel.output.setTextCursor(cursor)
        selected_menu = tab.receive_panel.output._build_context_menu()
        assert selected_menu.actions()[0].isEnabled() is True

        QApplication.clipboard().clear()
        selected_menu.actions()[0].trigger()
        assert QApplication.clipboard().text() == "dr"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_split_selection_survives_incoming_data(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        output = tab.receive_panel.output
        assert tab.receive_panel.autoscroll_check.isChecked() is True
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        cursor = QTextCursor(output.document())
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        transport.push_read(b"second")
        qtbot.waitUntil(lambda: len(tab.controller.records) == 2, timeout=2000)

        assert output.textCursor().hasSelection() is True
        assert len(output.textCursor().selectedText()) == 5

        cleared = QTextCursor(output.document())
        cleared.setPosition(0)
        output.setTextCursor(cleared)

        assert output.textCursor().position() == output.document().characterCount() - 1
    finally:
        tab.controller.close(force=True)
        window.close()


def test_split_drag_selection_anchor_survives_incoming_data(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        text = output.toPlainText()
        start = text.index("hello")
        end = start + len("hello")

        # 按下后数据帧到达：光标不能离开点击处，否则拖选锚点会漂到文档末尾。
        mouse_press(output, cursor_point(output, start))
        transport.push_read(b"second")
        qtbot.waitUntil(lambda: "second" in output.toPlainText(), timeout=2000)

        assert output.textCursor().hasSelection() is False
        assert output.textCursor().position() == start

        mouse_drag(output, cursor_point(output, end))
        mouse_release(output, cursor_point(output, end))

        cursor = output.textCursor()
        assert cursor.selectionStart() == start
        assert cursor.selectedText() == "hello"
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


def test_receive_header_shows_all_controls_when_width_allows(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow

    try:
        window.resize(1180, 760)
        qtbot.waitUntil(lambda: not overflow.folded_widgets(), timeout=2000)

        assert not overflow.button.isVisibleTo(receive_panel)
        for widget in (
            receive_panel.mode_combo,
            receive_panel.timestamp_check,
            receive_panel.rx_check,
            receive_panel.tx_check,
            receive_panel.pause_button,
            receive_panel.clear_button,
            receive_panel.wrap_check,
            receive_panel.autoscroll_check,
            tab.view_toggle_button,
        ):
            assert widget.isVisibleTo(tab)
            assert widget.width() >= widget.sizeHint().width()
    finally:
        window.close()


def test_receive_header_folds_secondary_controls_when_narrow(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow

    try:
        window.resize(900, 600)
        qtbot.waitUntil(lambda: bool(overflow.folded_widgets()), timeout=2000)

        folded = overflow.folded_widgets()
        assert receive_panel.autoscroll_check in folded
        assert receive_panel.wrap_check in folded
        assert receive_panel.pause_button not in folded
        assert receive_panel.clear_button not in folded
        assert receive_panel.mode_combo not in folded
        assert tab.view_toggle_button not in folded

        assert overflow.button.isVisibleTo(receive_panel)
        for widget in (
            receive_panel.mode_combo,
            receive_panel.pause_button,
            receive_panel.clear_button,
            tab.view_toggle_button,
            overflow.button,
        ):
            assert widget.isVisibleTo(tab)
            assert widget.geometry().right() <= receive_panel.width()

        visible_actions = [
            action.text() for action in overflow.menu.actions() if action.isVisible()
        ]
        assert sorted(visible_actions) == sorted(widget.text() for widget in folded)
    finally:
        window.close()


def test_receive_header_overflow_action_mirrors_checkbox_state(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow

    try:
        window.resize(900, 600)
        qtbot.waitUntil(
            lambda: receive_panel.autoscroll_check in overflow.folded_widgets(), timeout=2000
        )
        action = next(item for item in overflow.menu.actions() if item.text() == "自动滚动")
        assert action.isVisible()

        action.setChecked(False)
        assert not receive_panel.autoscroll_check.isChecked()
        receive_panel.autoscroll_check.setChecked(True)
        assert action.isChecked()

        window.resize(1180, 760)
        qtbot.waitUntil(lambda: not overflow.folded_widgets(), timeout=2000)
        assert receive_panel.autoscroll_check.isChecked()

        window.resize(900, 600)
        qtbot.waitUntil(
            lambda: receive_panel.autoscroll_check in overflow.folded_widgets(), timeout=2000
        )
        texts = [item.text() for item in overflow.menu.actions()]
        assert len(texts) == len(set(texts))
    finally:
        window.close()


def test_receive_panel_empty_state_placeholder(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel

    try:
        assert receive_panel.output.toPlainText() == ""
        assert receive_panel.output.placeholderText() == "暂无数据"

        receive_panel.append_record(
            LogRecord.from_bytes(
                timestamp_utc=datetime(2026, 10, 4, tzinfo=timezone.utc),
                direction="rx",
                raw=b"hello",
                encoding="utf-8",
                session_id="empty-state",
            )
        )
        assert receive_panel.output.toPlainText() != ""

        qtbot.mouseClick(tab.view_toggle_button, Qt.MouseButton.LeftButton)
        assert receive_panel.output.placeholderText() == ""

        qtbot.mouseClick(tab.view_toggle_button, Qt.MouseButton.LeftButton)
        assert receive_panel.output.placeholderText() == "暂无数据"
    finally:
        window.close()
