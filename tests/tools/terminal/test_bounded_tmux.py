import subprocess
import sys

import pytest

from openhands.tools.terminal.terminal.bounded_tmux import (
    BoundedTmuxCommand,
    _run_bounded_tmux_command,
)


def test_tmux_command_timeout_terminates_child_process():
    processes = []

    def popen(*args, **kwargs):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], **kwargs
        )
        processes.append(process)
        return process

    with pytest.raises(TimeoutError, match="tmux control command"):
        _run_bounded_tmux_command(["tmux", "capture-pane"], 0.1, popen=popen)

    assert len(processes) == 1
    assert processes[0].poll() is not None
    processes[0].wait(timeout=1.0)


def test_tmux_command_passes_bounded_timeout(monkeypatch):
    calls = []

    def run(command, timeout):
        calls.append((command, timeout))
        return 0, ["pane output"], ["warning"]

    monkeypatch.setattr(
        "openhands.tools.terminal.terminal.bounded_tmux._run_bounded_tmux_command",
        run,
    )
    command = BoundedTmuxCommand("capture-pane", tmux_bin="tmux", timeout=3.0)

    assert command.stdout == ["pane output"]
    assert command.stderr == ["warning"]
    assert calls == [(["tmux", "capture-pane"], 3.0)]


def test_server_cmd_preserves_tmux_flags_and_action_deadline(monkeypatch):
    calls = []

    def run(command, timeout):
        calls.append((command, timeout))
        return 0, [], []

    monkeypatch.setattr(
        "openhands.tools.terminal.terminal.bounded_tmux._run_bounded_tmux_command",
        run,
    )
    from openhands.sdk.conversation.resource_lock_manager import action_timeout
    from openhands.tools.terminal.terminal.bounded_tmux import BoundedTmuxServer

    server = BoundedTmuxServer(
        socket_name="test-socket",
        config_file="/tmp/tmux.conf",
        colors=256,
        tmux_bin="/usr/bin/tmux",
        command_timeout=9.0,
    )
    with action_timeout(2.0):
        server.cmd("capture-pane", "-p", target="%4")
    assert calls == [
        (
            [
                "/usr/bin/tmux",
                "-2",
                "-f/tmp/tmux.conf",
                "-Ltest-socket",
                "capture-pane",
                "-t",
                "%4",
                "-p",
            ],
            pytest.approx(2.0, abs=0.1),
        )
    ]


def test_neo_fetch_objs_uses_bounded_module_command(monkeypatch):
    calls = []

    def run(command, timeout):
        calls.append((command, timeout))
        return 0, [], []

    monkeypatch.setattr(
        "openhands.tools.terminal.terminal.bounded_tmux._run_bounded_tmux_command",
        run,
    )
    from openhands.tools.terminal.terminal.bounded_tmux import BoundedTmuxServer

    server = BoundedTmuxServer(
        socket_name="neo-socket",
        config_file="/tmp/neo.conf",
        tmux_bin="/usr/bin/tmux",
        command_timeout=4.0,
    )
    assert server.sessions == []
    assert len(calls) == 1
    command, timeout = calls[0]
    assert command[:4] == [
        "/usr/bin/tmux",
        "-f/tmp/neo.conf",
        "-Lneo-socket",
        "list-sessions",
    ]
    assert timeout == 4.0


def test_raise_if_dead_uses_bounded_command(monkeypatch):
    calls = []

    def run(command, timeout):
        calls.append((command, timeout))
        return 0, [], []

    monkeypatch.setattr(
        "openhands.tools.terminal.terminal.bounded_tmux._run_bounded_tmux_command",
        run,
    )
    from openhands.tools.terminal.terminal.bounded_tmux import BoundedTmuxServer

    server = BoundedTmuxServer(
        socket_path="/tmp/tmux-test.sock",
        tmux_bin="/usr/bin/tmux",
        command_timeout=3.0,
    )
    server.raise_if_dead()
    assert calls == [
        (
            ["/usr/bin/tmux", "-S/tmp/tmux-test.sock", "list-sessions"],
            3.0,
        )
    ]


def test_common_version_lookup_uses_bounded_module_command(monkeypatch):
    calls = []

    def run(command, timeout):
        calls.append((command, timeout))
        return 0, ["tmux 3.4"], []

    monkeypatch.setattr(
        "openhands.tools.terminal.terminal.bounded_tmux._run_bounded_tmux_command",
        run,
    )
    monkeypatch.setattr(
        "openhands.tools.terminal.terminal.bounded_tmux.shutil.which",
        lambda _: "/usr/bin/tmux",
    )
    import libtmux.common

    assert str(libtmux.common.get_version()) == "3.4"
    assert calls == [(["/usr/bin/tmux", "-V"], 15.0)]


def test_pane_refresh_uses_bounded_server_context(monkeypatch):
    calls = []

    def run(command, timeout):
        calls.append((command, timeout))
        raise TimeoutError("bounded refresh timeout")

    monkeypatch.setattr(
        "openhands.tools.terminal.terminal.bounded_tmux._run_bounded_tmux_command",
        run,
    )
    from libtmux import Pane

    from openhands.tools.terminal.terminal.bounded_tmux import BoundedTmuxServer

    server = BoundedTmuxServer(
        socket_name="refresh-socket",
        tmux_bin="/usr/bin/tmux",
        command_timeout=4.0,
    )
    pane = Pane(server=server, pane_id="%4")

    with pytest.raises(TimeoutError, match="bounded refresh timeout"):
        pane.refresh()

    assert calls
    assert calls[0][0][:4] == [
        "/usr/bin/tmux",
        "-Lrefresh-socket",
        "list-panes",
        "-a",
    ]
    assert calls[0][1] == 4.0
