"""测试终端视图的渲染、暂停、清屏与行时间戳。"""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    RecordingStore,
    build_window,
    build_window_with_store,
    connect_session,
    current_tab,
)


def test_terminal_renders_carriage_return_overwrite(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"progress 10%\rprogress 90%")

        qtbot.waitUntil(lambda: output.toPlainText() == "progress 90%", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_applies_ansi_colors_and_wide_characters(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read("\x1b[31m红\x1b[0m".encode())

        qtbot.waitUntil(lambda: output.toPlainText() == "红", timeout=2000)
        screen = tab.receive_panel._screen
        assert screen is not None
        assert screen.lines()[0][0].style.fg == 1
        assert screen.lines()[0][1].trailing is True
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_pause_freezes_render_but_keeps_receiving(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"before")
        qtbot.waitUntil(lambda: output.toPlainText() == "before", timeout=2000)

        tab.receive_panel.pause_button.setChecked(True)
        transport.push_read(b"\rafter!")
        qtbot.waitUntil(
            lambda: (
                tab.receive_panel._screen is not None
                and tab.receive_panel._screen.text_lines()[0] == "after!"
            ),
            timeout=2000,
        )
        assert output.toPlainText() == "before"

        tab.receive_panel.pause_button.setChecked(False)
        qtbot.waitUntil(lambda: output.toPlainText() == "after!", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_clear_resets_screen(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"data")
        qtbot.waitUntil(lambda: output.toPlainText() == "data", timeout=2000)

        qtbot.mouseClick(tab.receive_panel.clear_button, Qt.MouseButton.LeftButton)

        qtbot.waitUntil(lambda: output.toPlainText() == "", timeout=2000)
        assert tab.receive_panel._screen is not None
        assert tab.receive_panel._screen.text_lines() == ("",)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_rebuilds_from_buffer_after_view_round_trip(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"persisted")
        qtbot.waitUntil(lambda: output.toPlainText() == "persisted", timeout=2000)

        tab.set_view_mode("split", persist=False)
        assert tab.receive_panel._screen is None
        tab.set_view_mode("terminal", persist=False)

        assert output.toPlainText() == "persisted"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_theme_change_redraws_without_losing_data(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"themed")
        qtbot.waitUntil(lambda: output.toPlainText() == "themed", timeout=2000)

        tab.refresh_theme()

        assert output.toPlainText() == "themed"
    finally:
        tab.controller.close(force=True)
        window.close()


_TIMESTAMP_PATTERN = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\] ")


def test_terminal_row_timestamps_render_and_toggle(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.receive_panel.terminal_timestamp_check.setChecked(True)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        text = output.toPlainText()

        assert _TIMESTAMP_PATTERN.match(text) is not None
        assert text.endswith("] hello world")

        # 勾选状态下选中复制的内容会带上行首时间前缀。
        output.selectAll()
        output.copy()
        assert QApplication.clipboard().text() == text

        # 先清掉选中，再关闭时间戳；存在选中时渲染按设计延迟。
        cursor = output.textCursor()
        cursor.clearSelection()
        output.setTextCursor(cursor)
        tab.receive_panel.terminal_timestamp_check.setChecked(False)
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_row_timestamps_survive_incremental_render_and_view_round_trip(
    qtbot: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.receive_panel.terminal_timestamp_check.setChecked(True)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        transport.push_read(b"one\n")
        qtbot.waitUntil(lambda: "one" in output.toPlainText(), timeout=2000)
        transport.push_read(b"two")
        qtbot.waitUntil(lambda: "two" in output.toPlainText(), timeout=2000)

        text = output.toPlainText()

        assert len(_TIMESTAMP_PATTERN.findall(text)) == 2

        # 分栏往返后从缓冲重建模型，行时间前缀保持不变。
        tab.set_view_mode("split", persist=False)
        tab.set_view_mode("terminal", persist=False)
        rebuilt = output.toPlainText()

        assert rebuilt == text
        assert len(_TIMESTAMP_PATTERN.findall(rebuilt)) == 2
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_timestamp_persists_per_tab(qtbot: object) -> None:
    transport = FakeTransport()
    store = RecordingStore()
    window = build_window_with_store(qtbot, transport, store)
    tab = current_tab(window)

    try:
        tab.receive_panel.terminal_timestamp_check.setChecked(True)
        window._save_timer.stop()
        window._save_config()

        assert store.saves[-1].sessions[0].terminal_timestamp is True

        second = window.new_session()
        assert second.receive_panel.terminal_timestamp_check.isChecked() is False
    finally:
        window.close()
