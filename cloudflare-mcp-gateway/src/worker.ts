import { OAuthProvider } from "@cloudflare/workers-oauth-provider";
import { createProxyHandler, proxyToUpstream, type GatewayEnv } from "./index";

export interface Env extends GatewayEnv {
  OAUTH_LOGIN_PASSWORD: string;
  OAUTH_KV: KVNamespace;
  // Injected by OAuthProvider itself; used from the /authorize handler below.
  OAUTH_PROVIDER: {
    parseAuthRequest(request: Request): Promise<any>;
    lookupClient(clientId: string): Promise<{ clientName?: string } | null>;
    completeAuthorization(options: {
      request: any;
      userId: string;
      metadata: Record<string, unknown>;
      scope: string[];
      props: Record<string, unknown>;
    }): Promise<{ redirectTo: string }>;
  };
}

// Single-user deployment: one static passphrase gates the /authorize screen.
// There is no multi-tenant client management — this only exists so claude.ai's
// native connector (which requires OAuth, not custom headers) can reach the
// same upstream MCP server the Cloudflare Worker already proxies to.
const OAUTH_USER_ID = "danilo";

// Legacy static-bearer /mcp path (Claude Code, mcp-remote, scripts, etc.) —
// untouched, still works exactly as before.
const legacyHandler = createProxyHandler();

function renderLoginPage(error?: string): Response {
  return new Response(
    `<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>social-mcps · Autorizar acceso</title>
</head>
<body style="font-family:system-ui,sans-serif;max-width:420px;margin:96px auto;padding:0 16px;">
  <h2>social-mcps MCP</h2>
  <p>Introduce la contraseña para autorizar el acceso a este cliente.</p>
  ${error ? `<p style="color:#c0392b">${error}</p>` : ""}
  <form method="POST">
    <input
      type="password"
      name="password"
      placeholder="Contraseña"
      autofocus
      required
      style="width:100%;padding:8px;box-sizing:border-box;font-size:16px;"
    />
    <button
      type="submit"
      style="margin-top:12px;padding:8px 16px;font-size:16px;cursor:pointer;"
    >
      Autorizar
    </button>
  </form>
</body>
</html>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

async function handleAuthorize(request: Request, env: Env): Promise<Response> {
  let oauthReqInfo;
  try {
    oauthReqInfo = await env.OAUTH_PROVIDER.parseAuthRequest(request);
  } catch {
    return new Response("Invalid authorization request", { status: 400 });
  }

  const client = await env.OAUTH_PROVIDER.lookupClient(oauthReqInfo.clientId);
  if (!client) {
    return new Response("Unknown OAuth client", { status: 400 });
  }

  if (request.method === "POST") {
    const form = await request.formData();
    const password = String(form.get("password") ?? "");

    if (!env.OAUTH_LOGIN_PASSWORD || password !== env.OAUTH_LOGIN_PASSWORD) {
      return renderLoginPage("Contraseña incorrecta.");
    }

    const { redirectTo } = await env.OAUTH_PROVIDER.completeAuthorization({
      request: oauthReqInfo,
      userId: OAUTH_USER_ID,
      metadata: { clientName: client.clientName ?? "unknown client" },
      scope: oauthReqInfo.scope,
      props: { userId: OAUTH_USER_ID },
    });

    return Response.redirect(redirectTo, 302);
  }

  return renderLoginPage();
}

export default new OAuthProvider<Env>({
  // OAuth-protected endpoint — this is what you paste into claude.ai's
  // "Add custom connector" URL field.
  apiRoute: "/oauth/mcp",
  apiHandler: {
    async fetch(request: Request, env: Env): Promise<Response> {
      return proxyToUpstream(request, env);
    },
  },
  defaultHandler: {
    async fetch(request: Request, env: Env): Promise<Response> {
      const url = new URL(request.url);
      if (url.pathname === "/authorize") {
        return handleAuthorize(request, env);
      }
      // Anything that isn't an OAuth endpoint or the OAuth-protected route
      // falls back to the legacy static-bearer /mcp endpoint.
      return legacyHandler(request, env);
    },
  },
  authorizeEndpoint: "/authorize",
  tokenEndpoint: "/oauth/token",
  clientRegistrationEndpoint: "/oauth/register",
  scopesSupported: ["mcp"],
});
