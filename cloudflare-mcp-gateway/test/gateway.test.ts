import { describe, expect, it } from "vitest";
import { createProxyHandler, type GatewayEnv } from "../src/index";

const env: GatewayEnv = {
  MCP_CLIENT_TOKEN: "client-token",
  UPSTREAM_MCP_AUTH_TOKEN: "upstream-token",
  UPSTREAM_MCP_URL: "https://social-mcps-abc-uc.a.run.app/mcp",
};

function request(path = "/mcp", init: RequestInit = {}) {
  return new Request(`https://social-mcps.example.workers.dev${path}`, init);
}

describe("Cloudflare MCP gateway", () => {
  it("rejects requests without the client token before calling Cloud Run", async () => {
    let calls = 0;
    const handler = createProxyHandler(async () => {
      calls += 1;
      return new Response("should not be called");
    });

    const response = await handler(request(), env);

    expect(response.status).toBe(401);
    expect(calls).toBe(0);
  });

  it("rejects paths other than the MCP endpoint", async () => {
    const handler = createProxyHandler(async () => new Response("should not be called"));

    const response = await handler(
      request("/not-mcp", {
        headers: { Authorization: "Bearer client-token" },
      }),
      env,
    );

    expect(response.status).toBe(404);
  });

  it("forwards the MCP request with the upstream token and preserves the response", async () => {
    let forwardedUrl = "";
    let forwardedInit: RequestInit | undefined;
    const handler = createProxyHandler(async (input, init) => {
      forwardedUrl = String(input);
      forwardedInit = init;
      return new Response("upstream-response", {
        status: 202,
        headers: { "content-type": "application/json" },
      });
    });

    const response = await handler(
      request("/mcp?session=one", {
        method: "POST",
        headers: {
          Accept: "application/json, text/event-stream",
          Authorization: "Bearer client-token",
          "Content-Type": "application/json",
          "Mcp-Session-Id": "session-one",
        },
        body: JSON.stringify({ jsonrpc: "2.0", method: "initialize" }),
      }),
      env,
    );

    expect(response.status).toBe(202);
    expect(await response.text()).toBe("upstream-response");
    expect(forwardedUrl).toBe("https://social-mcps-abc-uc.a.run.app/mcp?session=one");
    expect(forwardedInit?.method).toBe("POST");
    expect(new Headers(forwardedInit?.headers).get("authorization")).toBe(
      "Bearer upstream-token",
    );
    expect(new Headers(forwardedInit?.headers).get("mcp-session-id")).toBe("session-one");
    expect(new Headers(forwardedInit?.headers).get("content-type")).toBe("application/json");
    expect(new Headers(forwardedInit?.headers).get("host")).toBeNull();
    expect(await new Response(forwardedInit?.body).text()).toContain('"method":"initialize"');
  });

  it("rejects an invalid client token", async () => {
    const handler = createProxyHandler(async () => new Response("should not be called"));

    const response = await handler(
      request("/mcp", { headers: { Authorization: "Bearer wrong-token" } }),
      env,
    );

    expect(response.status).toBe(401);
  });
});
