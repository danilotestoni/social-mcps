import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { postToX } from "./tools/post-to-x";
import { shareToFbFeed } from "./tools/share-to-fb-feed";

const server = new McpServer({
  name: "social-automation-mcp",
  version: "1.0.0",
});

server.tool(
  "post_to_x",
  "Publica un tweet en X (Twitter). Requiere haber ejecutado 'npm run setup-x' previamente para autenticar.",
  {
    text: z
      .string()
      .min(1)
      .max(280)
      .describe("Texto del tweet (máximo 280 caracteres)"),
    dry_run: z
      .boolean()
      .optional()
      .describe("Si es true, devuelve el payload sin publicar nada."),
  },
  async ({ text, dry_run }) => {
    const result = await postToX(text, dry_run ?? false);
    return {
      content: [{ type: "text" as const, text: JSON.stringify(result) }],
    };
  }
);

server.tool(
  "share_to_fb_feed",
  "Comparte un post de la página de Facebook en el feed personal. Requiere haber ejecutado 'npm run setup-fb' previamente para autenticar con la cuenta personal.",
  {
    post_url: z
      .string()
      .url()
      .describe("URL del post de la página de Facebook a compartir"),
    message: z
      .string()
      .max(63206)
      .optional()
      .describe("Texto opcional para acompañar el post compartido"),
    dry_run: z
      .boolean()
      .optional()
      .describe("Si es true, devuelve el payload sin publicar nada."),
  },
  async ({ post_url, message, dry_run }) => {
    const result = await shareToFbFeed(post_url, message, dry_run ?? false);
    return {
      content: [{ type: "text" as const, text: JSON.stringify(result) }],
    };
  }
);

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  process.stderr.write(`Fatal error: ${err}\n`);
  process.exit(1);
});
