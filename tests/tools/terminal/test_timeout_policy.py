from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from openhands.tools.terminal.definition import TerminalAction
from openhands.tools.terminal.terminal.terminal_session import TerminalSession
from openhands.tools.terminal.timeout_policy import (
    RUNTIME_IDLE_TIMEOUT_SECONDS_ENV,
    foreground_timeout_rejection_for,
    get_max_foreground_timeout_seconds,
    get_runtime_idle_timeout_seconds,
)


def test_terminal_action_timeout_is_bounded_and_defaults_to_fifteen_seconds():
    assert TerminalAction(command="echo ready").timeout == 15
    assert TerminalAction(command="echo ready", timeout=5).timeout == 5
    assert TerminalAction(command="echo ready", timeout=300).timeout == 300


@pytest.mark.parametrize(
    "timeout", [None, 0, 4.99, 300.01, 301, float("inf"), float("nan")]
)
def test_terminal_action_rejects_missing_or_out_of_range_timeouts(timeout):
    with pytest.raises(ValidationError):
        TerminalAction(command="echo ready", timeout=timeout)


def test_runtime_idle_timeout_unset_disables_cap(monkeypatch):
    monkeypatch.delenv(RUNTIME_IDLE_TIMEOUT_SECONDS_ENV, raising=False)

    assert get_runtime_idle_timeout_seconds() is None
    assert get_max_foreground_timeout_seconds() is None
    assert (
        foreground_timeout_rejection_for(
            command="sleep 9999",
            is_input=False,
            timeout=9999,
        )
        is None
    )


def test_foreground_timeout_cap_uses_ninety_percent_of_idle_threshold(monkeypatch):
    monkeypatch.setenv(RUNTIME_IDLE_TIMEOUT_SECONDS_ENV, "1200")

    assert get_runtime_idle_timeout_seconds() == 1200
    assert get_max_foreground_timeout_seconds() == 1080
    assert (
        foreground_timeout_rejection_for(
            command="sleep 1080",
            is_input=False,
            timeout=1080,
        )
        is None
    )

    rejection = foreground_timeout_rejection_for(
        command="sleep 1500",
        is_input=False,
        timeout=1500,
    )

    assert rejection is not None
    assert "timeout=1500s" in rejection
    assert "idle cleanup after 1200s" in rejection
    assert "currently 1080s" in rejection


def test_foreground_timeout_cap_ignores_inputs_and_empty_commands(monkeypatch):
    monkeypatch.setenv(RUNTIME_IDLE_TIMEOUT_SECONDS_ENV, "200")

    assert (
        foreground_timeout_rejection_for(command="C-c", is_input=True, timeout=200)
        is None
    )
    assert (
        foreground_timeout_rejection_for(command="", is_input=False, timeout=200)
        is None
    )


def test_terminal_session_rejects_timeout_exceeding_runtime_idle_cap_before_execution(
    monkeypatch,
):
    monkeypatch.setenv(RUNTIME_IDLE_TIMEOUT_SECONDS_ENV, "200")
    terminal = MagicMock()
    terminal.work_dir = "/workspace"
    terminal.username = None
    session = TerminalSession(terminal=terminal)
    session._initialized = True

    observation = session.execute(TerminalAction(command="sleep 200", timeout=200))

    assert observation.is_error is True
    assert observation.command == "sleep 200"
    assert "currently 180s" in observation.text
    terminal.read_screen.assert_not_called()
    terminal.send_keys.assert_not_called()


def test_runtime_idle_timeout_rejects_nonfinite_configuration():
    assert (
        get_runtime_idle_timeout_seconds({RUNTIME_IDLE_TIMEOUT_SECONDS_ENV: "inf"})
        is None
    )
    assert (
        get_runtime_idle_timeout_seconds({RUNTIME_IDLE_TIMEOUT_SECONDS_ENV: "nan"})
        is None
    )
    assert (
        get_runtime_idle_timeout_seconds({RUNTIME_IDLE_TIMEOUT_SECONDS_ENV: "-inf"})
        is None
    )
