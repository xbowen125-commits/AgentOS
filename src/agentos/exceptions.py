"""AgentOS exception definitions."""


class AgentOSError(Exception):
    """Base exception for AgentOS errors."""


class ToolRuntimeError(AgentOSError):
    """Base exception for tool runtime errors."""


class ToolAlreadyRegisteredError(ToolRuntimeError):
    """Raised when a tool name is registered more than once."""


class ToolNotFoundError(ToolRuntimeError):
    """Raised when a requested tool is not registered."""


class ToolArgumentError(ToolRuntimeError):
    """Raised when a tool receives invalid arguments."""


class ToolExecutionError(ToolRuntimeError):
    """Raised when a tool fails during execution."""

