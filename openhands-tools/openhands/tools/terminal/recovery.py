"""Out-of-band recovery tool for unresponsive terminal sessions."""

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from pydantic import Field

from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


@runtime_checkable
class RecoverableTerminalExecutor(Protocol):
    def recover(self, reason: str = "Terminal is unresponsive") -> str: ...


if TYPE_CHECKING:
    from openhands.sdk.conversation import LocalConversation


class TerminalRecoverAction(Action):
    """Request interruption and replacement of the shared terminal session."""

    reason: str = Field(
        default="Terminal is unresponsive",
        description="Why the terminal session needs to be recovered.",
    )


class TerminalRecoverObservation(Observation):
    """Result of attempting to recover a terminal session."""


class TerminalRecoverExecutor(
    ToolExecutor[TerminalRecoverAction, TerminalRecoverObservation]
):
    """Recover a terminal without acquiring the normal terminal resource lock."""

    def __init__(self, recover_session: Callable[[str], str]) -> None:
        self.recover_session = recover_session

    def __call__(
        self,
        action: TerminalRecoverAction,
        conversation: "LocalConversation | None" = None,
    ) -> TerminalRecoverObservation:
        del conversation
        return TerminalRecoverObservation.from_text(
            text=self.recover_session(action.reason),
        )


class TerminalRecoverTool(
    ToolDefinition[TerminalRecoverAction, TerminalRecoverObservation]
):
    """Force-reset the shared terminal session when it becomes unresponsive."""

    user_selectable: ClassVar[bool] = False
    catalog_description: ClassVar[str] = (
        "Interrupt and replace an unresponsive terminal session."
    )
    RECOVERY_PROMPT_GUIDANCE: ClassVar[str] = (
        "<TERMINAL_RECOVERY>\n"
        "Use `terminal_recover` if the terminal reports a session/resource-lock "
        "timeout, fails to return after its bounded timeout, or no longer accepts "
        "commands. It interrupts running terminal commands and replaces the shell; "
        "working-directory changes and shell environment variables are lost. "
        "Commands interrupted during recovery may have completed partially. Verify "
        "their effects and rerun only commands whose completion is unconfirmed. "
        "This tool bypasses the terminal-session lock.\n"
        "</TERMINAL_RECOVERY>"
    )

    def declared_resources(self, action: Action) -> DeclaredResources:
        del action
        return DeclaredResources(keys=(), declared=True)

    @classmethod
    def create(
        cls,
        *,
        terminal_executor: RecoverableTerminalExecutor,
    ) -> list["TerminalRecoverTool"]:
        return [
            cls(
                action_type=TerminalRecoverAction,
                observation_type=TerminalRecoverObservation,
                description=(
                    "Interrupt and replace the OpenHands terminal session when it "
                    "hangs or cannot acquire its session lock. This recovery tool "
                    "runs outside the terminal lock. Session environment variables "
                    "and working-directory changes are cleared; do not assume the "
                    "interrupted command failed before checking its effects."
                ),
                annotations=ToolAnnotations(
                    title="terminal_recover",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
                executor=TerminalRecoverExecutor(
                    recover_session=terminal_executor.recover
                ),
                prompt_guidance=cls.RECOVERY_PROMPT_GUIDANCE,
            )
        ]


register_tool(TerminalRecoverTool.name, TerminalRecoverTool)
