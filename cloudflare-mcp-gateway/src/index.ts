export interface GatewayEnv {
  MCP_CLIENT_TOKEN: string;
  UPSTREAM_MCP_AUTH_TOKEN: string;
  UPSTREAM_MCP_URL: string;
}

type FetchLike = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

const FORWARDED_HEADERS = [
  "accept",
  "cache-control",
  "content-type",
  "last-event-id",
  "mcp-session-id",
];

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function isConfigured(env: GatewayEnv): boolean {
  return Boolean(
    env.MCP_CLIENT_TOKEN && env.UPSTREAM_MCP_AUTH_TOKEN && env.UPSTREAM_MCP_URL,
  );
}

export function createProxyHandler(fetchImpl: FetchLike = fetch) {
  return async (request: Request, env: GatewayEnv): Promise<Response> => {
    if (!isConfigured(env)) {
      return jsonError("Gateway secrets are not configured", 500);
    }

    const requestUrl = new URL(request.url);
    if (requestUrl.pathname !== "/mcp") {
      return jsonError("Not found", 404);
    }

    if (request.method !== "GET" && request.method !== "POST" && request.method !== "DELETE") {
      return jsonError("Method not allowed", 405);
    }

    if (request.headers.get("authorization") !== `Bearer ${env.MCP_CLIENT_TOKEN}`) {
      return jsonError("Unauthorized", 401);
    }

    const upstreamUrl = new URL(env.UPSTREAM_MCP_URL);
    upstreamUrl.search = requestUrl.search;

    const headers = new Headers();
    for (const name of FORWARDED_HEADERS) {
      const value = request.headers.get(name);
      if (value !== null) {
        headers.set(name, value);
      }
    }
    headers.set("authorization", `Bearer ${env.UPSTREAM_MCP_AUTH_TOKEN}`);

    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (request.method !== "GET") {
      init.body = request.body;
      init.duplex = "half";
    }

    return fetchImpl(upstreamUrl.toString(), init);
  };
}

const gatewayHandler = createProxyHandler();

export default {
  fetch(request: Request, env: GatewayEnv): Promise<Response> {
    return gatewayHandler(request, env);
  },
};
