import { postToX } from "./src/tools/post-to-x";

postToX("🤖 Test de publicación automática desde MCP. Puedes eliminar este tweet.")
  .then((result) => {
    console.log("\nResultado:", JSON.stringify(result, null, 2));
    process.exit(result.success ? 0 : 1);
  })
  .catch((err) => {
    console.error("Error inesperado:", err);
    process.exit(1);
  });
