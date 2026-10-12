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


class MemoryStoreError(AgentOSError):
    """Base exception for memory persistence errors."""


class MemoryFormatError(MemoryStoreError):
    """Raised when a memory document is not valid JSON or has an invalid shape."""


class MemoryVersionError(MemoryStoreError):
    """Raised when a memory document uses an unsupported schema version."""


class MemoryItemNotFoundError(MemoryStoreError):
    """Raised when a memory item cannot be found by ID."""

