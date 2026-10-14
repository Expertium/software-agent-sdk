import re
from typing import Final


CMD_OUTPUT_PS1_BEGIN: Final[str] = "\n###PS1JSON###\n"
CMD_OUTPUT_PS1_END: Final[str] = "\n###PS1END###"
# Regex to match PS1 metadata blocks. Uses negative lookahead to handle corruption
# scenarios where concurrent output causes nested ###PS1JSON### markers. This ensures
# we match only the LAST ###PS1JSON### before each ###PS1END###.
CMD_OUTPUT_METADATA_PS1_REGEX: Final[re.Pattern[str]] = re.compile(
    rf"^{CMD_OUTPUT_PS1_BEGIN.strip()}((?:(?!{CMD_OUTPUT_PS1_BEGIN.strip()}).)*?){CMD_OUTPUT_PS1_END.strip()}",
    re.DOTALL | re.MULTILINE,
)

# Default max size for command output content
# to prevent too large observations from being saved in the stream
# This matches the default max_message_chars in LLM class
MAX_CMD_OUTPUT_SIZE: Final[int] = 30000


# Common timeout message that can be used across different timeout scenarios
TIMEOUT_MESSAGE_TEMPLATE: Final[str] = (
    "Every terminal action has a bounded timeout (default 15 seconds; "
    "allowed range 5-300 seconds). You may wait longer to see additional output "
    'by sending an empty command, or send keys ("C-c", "C-z", "C-d") '
    "to interrupt the previous command. If the terminal stops responding or "
    "reports a terminal lock timeout, call `terminal_recover` to interrupt and "
    "replace the terminal session; then retry any command that did not complete."
)

DEFAULT_COMMAND_TIMEOUT_SECONDS: Final[float] = 15.0
MIN_COMMAND_TIMEOUT_SECONDS: Final[float] = 5.0
MAX_COMMAND_TIMEOUT_SECONDS: Final[float] = 300.0

# How long to wait with no new output before considering it a no-change timeout
NO_CHANGE_TIMEOUT_SECONDS: Final[int] = 30

# How often to poll for new output in seconds, once a command has run for a while
POLL_INTERVAL: Final[float] = 0.5
# Shortest poll interval, used right after a command is sent
MIN_POLL_INTERVAL: Final[float] = 0.02
HISTORY_LIMIT: Final[int] = 10_000

TMUX_SOCKET_NAME: Final[str] = "openhands"

# Tmux session dimensions (columns x rows). Keep the viewport wide enough for
# common command output while leaving scrollback retention to HISTORY_LIMIT.
# Output wider than TMUX_SESSION_WIDTH columns will wrap; this is an accepted
# tradeoff to avoid the oversized 1000x1000 virtual terminal grid.
TMUX_SESSION_WIDTH: Final[int] = 256
TMUX_SESSION_HEIGHT: Final[int] = 200
