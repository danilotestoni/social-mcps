/**
 * One-time setup script: opens a visible Chromium window so you can log in to X manually,
 * then saves the session state to auth/x-session.json for reuse by the post_to_x tool.
 *
 * Run once with:  npm run setup-x
 */
import { chromium } from "./browser";
import * as path from "path";
import * as fs from "fs";

const AUTH_DIR = path.join(__dirname, "..", "auth");
const AUTH_FILE = path.join(AUTH_DIR, "x-session.json");

async function main(): Promise<void> {
  if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  }

  console.log("Abriendo Chromium. Inicia sesión en X manualmente en el navegador que aparece...");
  console.log("El script espera hasta que llegues a x.com/home (timeout: 120s).\n");

  const browser = await chromium.launch({
    headless: false,
    slowMo: 50, // small delay so interactions feel natural
  });
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto("https://x.com/login");

  // Wait until the URL changes to the home page after successful login
  await page.waitForURL("**/home", { timeout: 120_000 });

  // Let the page settle so all cookies and storage are written
  await page.waitForLoadState("networkidle").catch(() => {});

  await context.storageState({ path: AUTH_FILE });

  console.log(`\n✅ Sesión guardada en ${AUTH_FILE}`);
  console.log("Ya puedes usar la tool post_to_x desde Claude.\n");

  await browser.close();
}

main().catch((err: unknown) => {
  console.error("Error durante el setup:", err);
  process.exit(1);
});
