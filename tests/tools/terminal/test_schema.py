from openhands.tools.terminal import TerminalTool


def test_to_mcp_tool_detailed_type_validation_bash(mock_conversation_state):
    """Test detailed type validation for MCP tool schema generation (terminal)."""  # noqa: E501

    terminal_tool = TerminalTool.create(conv_state=mock_conversation_state)
    assert len(terminal_tool) == 1
    terminal_tool = terminal_tool[0]
    assert isinstance(terminal_tool, TerminalTool)

    # Test terminal tool schema
    bash_mcp = terminal_tool.to_mcp_tool()
    bash_schema = bash_mcp["inputSchema"]
    bash_props = bash_schema["properties"]

    # Test command field is required string
    bash_command_schema = bash_props["command"]
    assert bash_command_schema["type"] == "string"
    assert "command" in bash_schema["required"]

    # Test is_input field is optional boolean with default
    is_input_schema = bash_props["is_input"]
    assert is_input_schema["type"] == "boolean"
    assert "is_input" not in bash_schema["required"]

    timeout_schema = bash_props["timeout"]
    assert timeout_schema["type"] == "number"
    assert timeout_schema["default"] == 15
    assert timeout_schema["minimum"] == 5
    assert timeout_schema["maximum"] == 300

    # security_risk should NOT be in the schema after #341
    assert "security_risk" not in bash_props


def test_terminal_recovery_tool_is_hidden_from_selectable_catalog(
    mock_conversation_state,
):
    tools = TerminalTool.create(conv_state=mock_conversation_state)

    assert len(tools) == 1
    assert tools[0].name == "terminal"


def test_terminal_action_schema_rejects_nonfinite_timeout():
    import pytest
    from pydantic import ValidationError

    from openhands.tools.terminal import TerminalAction

    with pytest.raises(ValidationError):
        TerminalAction(command="echo invalid", timeout=float("inf"))
    with pytest.raises(ValidationError):
        TerminalAction(command="echo invalid", timeout=float("nan"))
