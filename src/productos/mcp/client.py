from mcp import Client

from productos.application.ports import MCPClientError
from productos.domain.tools import ToolErrorCode


class StreamableHTTPMCPClient:
    """Official MCP SDK transport for a deployment-owned Streamable HTTP endpoint."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def call_tool(
        self, provider: str, tool_name: str, arguments: dict[str, object]
    ) -> object:
        try:
            async with Client(self._url) as client:
                result = await client.call_tool(tool_name, arguments)
        except TimeoutError as exc:
            raise MCPClientError(
                ToolErrorCode.TIMEOUT, f"The {provider} MCP endpoint timed out."
            ) from exc
        except Exception as exc:
            raise MCPClientError(
                ToolErrorCode.UPSTREAM_ERROR,
                f"The {provider} MCP endpoint could not complete the call.",
            ) from exc
        if result.is_error:
            raise MCPClientError(
                ToolErrorCode.UPSTREAM_ERROR,
                f"The {provider} MCP tool reported a failure.",
            )
        if result.structured_content is None:
            raise MCPClientError(
                ToolErrorCode.UPSTREAM_ERROR,
                f"The {provider} MCP tool returned no structured output.",
            )
        return result.structured_content


class UnavailableMCPClient:
    """Honest default until an MCP transport is configured by the deployment."""

    async def call_tool(
        self, provider: str, tool_name: str, arguments: dict[str, object]
    ) -> object:
        raise MCPClientError(
            ToolErrorCode.TOOL_UNAVAILABLE,
            f"The {provider} connection is not configured.",
        )
