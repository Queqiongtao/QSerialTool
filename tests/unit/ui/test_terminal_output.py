"""测试终端视图的增量渲染、滚动窗口、批量追加与光标闪烁。"""

import re
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QTextCursor
from PySide6.QtTest import QTest
from tests.fixtures.ui_helpers import fragment_formats

from qserialtool.domain import TerminalScreen
from qserialtool.ui.terminal_output import TerminalOutput
from qserialtool.ui.theme_manager import data_colors


def _output(qtbot: object) -> TerminalOutput:
    output = TerminalOutput()
    qtbot.addWidget(output)
    output.set_terminal_mode(True)
    return output


def test_incremental_render_matches_full_rebuild(qtbot: object) -> None:
    """增量路径与整屏重建必须逐字符一致，覆盖覆写、光标移动与擦除。"""
    output = _output(qtbot)
    screen = TerminalScreen()
    chunks = (
        "hello world\n",
        "progress 10%\rprogress 90%\n",
        "\x1b[31mred\x1b[0m 中文\n",
        "ip 10.0.0.1 link https://a.com/x OK ERROR WARN\n",
        "tab\there\n",
        "back\x08space\n",
        "\x1b[2A\rOVERRIDE-TOP\n",
        "\x1b[1;1Hhome write\n",
        "\x1b[Kcleared-tail",
        "\x1b[31m10.0.0.1\x1b[0m\r\n",
    )
    for chunk in chunks:
        screen.feed(chunk)
        output.render_screen(screen)
        incremental = output.toPlainText()
        output.render_screen(screen, full=True)

        assert output.toPlainText() == incremental, chunk


def test_incremental_render_slides_scrollback_window(qtbot: object) -> None:
    output = _output(qtbot)
    screen = TerminalScreen()
    for index in range(2100):
        screen.feed(f"line {index}\n")
        output.render_screen(screen)

    text = output.toPlainText()

    assert "已隐藏较早的 101 行" in text
    assert "line 101\n" in text
    assert "line 100\n" not in text
    assert output.document().blockCount() <= 2003

    screen.feed("tail")
    output.render_screen(screen)
    incremental = output.toPlainText()

    assert incremental.endswith("tail")
    output.render_screen(screen, full=True)
    assert output.toPlainText() == incremental


def test_incremental_render_matches_full_across_screen_trim(qtbot: object) -> None:
    """模型自身 5000 行裁剪与 2000 行渲染窗口同帧滑动时也必须对齐。"""
    output = _output(qtbot)
    screen = TerminalScreen()
    for index in range(5200):
        screen.feed(f"line {index}\r\n")
        output.render_screen(screen)
        if index % 900 == 0:
            incremental = output.toPlainText()
            output.render_screen(screen, full=True)

            assert output.toPlainText() == incremental, index

    assert screen.dropped_rows == 201
    assert "已隐藏较早的 3000 行" in output.toPlainText()

    incremental = output.toPlainText()
    output.render_screen(screen, full=True)

    assert output.toPlainText() == incremental


def test_incremental_render_keeps_draft_and_cursor_truncation(qtbot: object) -> None:
    """光标行只显示光标之前的单元格，草稿接在其后；增量改写要维持同一语义。"""
    output = _output(qtbot)
    screen = TerminalScreen()
    screen.feed("0123456789")
    output.render_screen(screen)
    output.set_draft("XY")

    screen.feed("\r")
    output.render_screen(screen)

    assert output.toPlainText() == "XY"
    assert output.draft == "XY"

    output.render_screen(screen, full=True)

    assert output.toPlainText() == "XY"


def test_append_lines_keeps_order_and_per_line_format(qtbot: object) -> None:
    output = _output(qtbot)

    output.append_lines(
        (
            (("first", "#112233", False),),
            (("RX: ", "#00aa00", True), ("payload", "#000000", False)),
        )
    )

    assert output.toPlainText() == "first\nRX: payload\n"


_TIMESTAMP_PATTERN = re.compile(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\] ")


def test_timestamps_render_gray_prefix_and_keep_draft_aligned(qtbot: object) -> None:
    output = _output(qtbot)
    output.set_show_timestamps(True)
    screen = TerminalScreen()
    screen.feed("#cmd\n", timestamp=datetime(2026, 10, 16, 8, 0, 0, tzinfo=timezone.utc))
    output.render_screen(screen)
    output.set_draft("next")

    text = output.toPlainText()

    assert text.startswith("[2026-10-16 ")
    assert text.endswith("] #cmd\nnext")
    assert fragment_formats(output)[0][1] == data_colors().system


def test_timestamp_toggle_rebuilds_prefixes_consistently(qtbot: object) -> None:
    output = _output(qtbot)
    screen = TerminalScreen()
    screen.feed("hello", timestamp=datetime(2026, 10, 16, 8, 0, 0, tzinfo=timezone.utc))
    output.render_screen(screen)

    assert output.toPlainText() == "hello"

    output.set_show_timestamps(True)
    output.render_screen(screen, full=True)
    assert output.toPlainText().endswith("] hello")

    output.set_show_timestamps(False)
    output.render_screen(screen, full=True)
    assert output.toPlainText() == "hello"


def test_timestamps_match_between_incremental_and_full_rebuild(qtbot: object) -> None:
    output = _output(qtbot)
    output.set_show_timestamps(True)
    screen = TerminalScreen()
    chunks = ("one\n", "two\r\n", "three")
    for index, chunk in enumerate(chunks):
        screen.feed(
            chunk,
            timestamp=datetime(2026, 10, 16, 8, 0, index, tzinfo=timezone.utc),
        )
        output.render_screen(screen)
    incremental = output.toPlainText()
    output.render_screen(screen, full=True)

    assert output.toPlainText() == incremental
    lines = incremental.splitlines()

    assert len(lines) == 3
    assert all(_TIMESTAMP_PATTERN.match(line) for line in lines)
    assert [line.split("] ", 1)[1] for line in lines] == ["one", "two", "three"]


def test_block_cursor_blinks_only_when_focused_and_resets_on_input(qtbot: object) -> None:
    """光标仅在聚焦时闪烁；失焦与输入瞬间保持实心可见，隐藏后停表。"""
    output = _output(qtbot)
    output.show()
    qtbot.waitExposed(output)
    screen = TerminalScreen()
    screen.feed("ready")
    output.render_screen(screen)

    assert output._cursor_visible
    assert not output._cursor_blink_timer.isActive()

    output.setFocus(Qt.FocusReason.OtherFocusReason)
    qtbot.waitUntil(output.hasFocus, timeout=2000)
    assert output._cursor_blink_timer.isActive()

    output._blink_cursor()
    assert not output._cursor_visible
    output._blink_cursor()
    assert output._cursor_visible

    output._blink_cursor()
    assert not output._cursor_visible
    QTest.keyClicks(output, "x")
    assert output._cursor_visible
    assert output.draft == "x"

    output.hide()
    output._blink_cursor()
    assert not output._cursor_blink_timer.isActive()

    output.set_terminal_mode(False)
    assert not output._cursor_blink_timer.isActive()


def test_block_cursor_paint_toggles_with_visibility(qtbot: object) -> None:
    """光标可见时草稿末尾绘出实心块，隐藏时该像素回到底色。"""
    output = _output(qtbot)
    output.resize(300, 120)
    output.show()
    qtbot.waitExposed(output)
    screen = TerminalScreen()
    screen.feed("ab")
    output.render_screen(screen)
    output.setFocus(Qt.FocusReason.OtherFocusReason)
    qtbot.waitUntil(output.hasFocus, timeout=2000)

    def cursor_pixel() -> str:
        caret = QTextCursor(output.document())
        caret.setPosition(output._input.bounds()[1])
        rect = output.cursorRect(caret)
        width = max(output.fontMetrics().horizontalAdvance(" "), 1)
        image = output.viewport().grab().toImage()
        return image.pixelColor(rect.left() + width // 2, rect.top() + rect.height() // 2).name()

    text_color = output.palette().color(QPalette.ColorRole.Text).name()
    output._touch_cursor()
    assert cursor_pixel() == text_color

    output._blink_cursor()
    assert not output._cursor_visible
    assert cursor_pixel() != text_color
