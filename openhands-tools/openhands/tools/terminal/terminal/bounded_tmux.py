"""Run tmux client commands with bounded subprocess timeouts."""

from __future__ import annotations

import logging
import math
import shlex
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from types import ModuleType
from typing import Any, cast

import libtmux
import libtmux.common
import libtmux.neo
import libtmux.server
from libtmux import exc
from libtmux.common import tmux_cmd

from openhands.sdk.conversation.resource_lock_manager import get_action_timeout
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)
DEFAULT_TMUX_COMMAND_TIMEOUT_SECONDS = 15.0
_PATCH_LOCK = threading.Lock()
_PATCHED = False
_NEO_COMMAND_CONTEXT: ContextVar[
    tuple[str | None, str | None, str | None, str | None, int | None, float] | None
] = ContextVar("neo_tmux_command_context", default=None)
_ORIGINAL_SERVER_FETCH_OBJS = cast(Any, getattr(libtmux.server, "fetch_objs"))
_ORIGINAL_NEO_FETCH_OBJS = cast(Any, libtmux.neo.fetch_objs)


def _run_bounded_tmux_command(
    command: list[str],
    timeout: float,
    *,
    popen: Any | None = None,
) -> tuple[int, list[str], list[str]]:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("tmux command timeout must be finite and positive")
    process: subprocess.Popen[str] | None = None
    try:
        process = (popen or subprocess.Popen)(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
        )
        assert process is not None
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        if process is not None:
            with suppress(OSError):
                process.kill()
            with suppress(OSError, subprocess.TimeoutExpired):
                process.communicate(timeout=1.0)
            with suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=1.0)
        raise TimeoutError(
            f"tmux control command exceeded its {timeout:g}s deadline"
        ) from error
    except FileNotFoundError:
        raise exc.TmuxCommandNotFound from None
    assert process is not None
    return (
        process.returncode,
        stdout.splitlines(),
        list(filter(None, stderr.splitlines())),
    )


class BoundedTmuxCommand(tmux_cmd):
    """Run one tmux client command with a finite timeout."""

    def __init__(
        self,
        *args: Any,
        tmux_bin: str | None = None,
        timeout: float = DEFAULT_TMUX_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        resolved = tmux_bin or shutil.which("tmux")
        if not resolved:
            raise exc.TmuxCommandNotFound
        command = [resolved, *map(str, args)]
        self.cmd = command
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "tmux command dispatched",
                extra={"tmux_cmd": shlex.join(command)},
            )
        self.returncode, self.stdout, self.stderr = _run_bounded_tmux_command(
            command, timeout
        )


def _bounded_module_tmux_cmd(
    *args: Any, tmux_bin: str | None = None
) -> BoundedTmuxCommand:
    explicit_tmux_bin = tmux_bin
    context = _NEO_COMMAND_CONTEXT.get()
    (
        context_tmux_bin,
        socket_name,
        socket_path,
        config_file,
        colors,
        default_timeout,
    ) = context or (
        None,
        None,
        None,
        None,
        None,
        DEFAULT_TMUX_COMMAND_TIMEOUT_SECONDS,
    )
    command_args = list(args)
    if socket_path and not any(str(arg).startswith("-S") for arg in command_args):
        command_args.insert(0, f"-S{socket_path}")
    if config_file and not any(str(arg).startswith("-f") for arg in command_args):
        command_args.insert(0, f"-f{config_file}")
    if colors == 256 and "-2" not in command_args:
        command_args.insert(0, "-2")
    elif colors == 88 and "-8" not in command_args:
        command_args.insert(0, "-8")
    if socket_name and not any(str(arg).startswith("-L") for arg in command_args):
        command_args.insert(0, f"-L{socket_name}")
    return BoundedTmuxCommand(
        *command_args,
        tmux_bin=explicit_tmux_bin or context_tmux_bin,
        timeout=cast(float, get_action_timeout(default_timeout)),
    )


@contextmanager
def _neo_command_context(server: libtmux.Server) -> Iterator[None]:
    token = _NEO_COMMAND_CONTEXT.set(
        (
            getattr(server, "tmux_bin", None),
            server.socket_name,
            str(server.socket_path) if server.socket_path is not None else None,
            server.config_file,
            server.colors,
            getattr(server, "command_timeout", DEFAULT_TMUX_COMMAND_TIMEOUT_SECONDS),
        )
    )
    try:
        yield
    finally:
        _NEO_COMMAND_CONTEXT.reset(token)


def _bounded_server_fetch_objs(*args: Any, **kwargs: Any) -> Any:
    server = args[0] if args else kwargs["server"]
    with _neo_command_context(server):
        return _ORIGINAL_SERVER_FETCH_OBJS(*args, **kwargs)


def _bounded_neo_fetch_objs(*args: Any, **kwargs: Any) -> Any:
    server = args[0] if args else kwargs["server"]
    with _neo_command_context(server):
        return _ORIGINAL_NEO_FETCH_OBJS(*args, **kwargs)


def _install_libtmux_bounded_command_hooks() -> None:
    """Bound libtmux module-level command lookups that bypass Server.cmd."""
    global _PATCHED
    with _PATCH_LOCK:
        if _PATCHED:
            return
        setattr(cast(ModuleType, libtmux.neo), "tmux_cmd", _bounded_module_tmux_cmd)
        setattr(cast(ModuleType, libtmux.common), "tmux_cmd", _bounded_module_tmux_cmd)
        setattr(
            cast(ModuleType, libtmux.server),
            "fetch_objs",
            _bounded_server_fetch_objs,
        )
        setattr(
            cast(ModuleType, libtmux.neo),
            "fetch_objs",
            _bounded_neo_fetch_objs,
        )
        _PATCHED = True


class BoundedTmuxServer(libtmux.Server):
    """libtmux server whose control subprocesses use explicit deadlines."""

    def __init__(
        self,
        *args: Any,
        tmux_bin: str | None = None,
        command_timeout: float = DEFAULT_TMUX_COMMAND_TIMEOUT_SECONDS,
        **kwargs: Any,
    ) -> None:
        self.tmux_bin = tmux_bin
        self.command_timeout = command_timeout
        _install_libtmux_bounded_command_hooks()
        super().__init__(*args, **kwargs)

    def _effective_timeout(self) -> float:
        return get_action_timeout(self.command_timeout) or self.command_timeout

    def cmd(
        self,
        cmd: str,
        *args: Any,
        target: str | int | None = None,
    ) -> BoundedTmuxCommand:
        server_args: list[str | int] = [cmd]
        if self.socket_name:
            server_args.insert(0, f"-L{self.socket_name}")
        if self.socket_path:
            server_args.insert(0, f"-S{self.socket_path}")
        if self.config_file:
            server_args.insert(0, f"-f{self.config_file}")
        if self.colors:
            if self.colors == 256:
                server_args.insert(0, "-2")
            elif self.colors == 88:
                server_args.insert(0, "-8")
            else:
                raise exc.UnknownColorOption
        command_args: list[str | int]
        if target is not None:
            command_args = ["-t", str(target), *args]
        else:
            command_args = list(args)
        return BoundedTmuxCommand(
            *server_args,
            *command_args,
            tmux_bin=self.tmux_bin,
            timeout=self._effective_timeout(),
        )

    def raise_if_dead(self) -> None:
        """Check the server with the same bounded client used by ``cmd``."""
        command_args: list[str] = ["list-sessions"]
        if self.socket_name:
            command_args.insert(0, f"-L{self.socket_name}")
        if self.socket_path:
            command_args.insert(0, f"-S{self.socket_path}")
        if self.config_file:
            command_args.insert(0, f"-f{self.config_file}")
        result = BoundedTmuxCommand(
            *command_args,
            tmux_bin=self.tmux_bin,
            timeout=self._effective_timeout(),
        )
        if result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode,
                result.cmd,
                output="\n".join(result.stdout),
                stderr="\n".join(result.stderr),
            )


_install_libtmux_bounded_command_hooks()
