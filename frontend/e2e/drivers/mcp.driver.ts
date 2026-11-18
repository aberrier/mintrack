import { APIRequestContext } from '@playwright/test';

/** A client of the MCP server at /mcp, as an assistant connects with an API token. */
export class McpDriver {
  constructor(private readonly request: APIRequestContext) {}

  /** The MCP initialize call: the HTTP status, and the server's name when it answered. */
  async initialize(token: string): Promise<{ status: number; serverName?: string }> {
    const response = await this.request.post('/mcp', {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json, text/event-stream' },
      data: {
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'e2e', version: '1' } },
      },
    });
    if (!response.ok()) return { status: response.status() };
    return { status: response.status(), serverName: (await response.json()).result.serverInfo.name };
  }
}
