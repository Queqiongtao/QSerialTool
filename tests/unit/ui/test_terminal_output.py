"""测试终端视图的增量渲染、滚动窗口与批量追加。"""

from qserialtool.domain import TerminalScreen
from qserialtool.ui.terminal_output import TerminalOutput


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
