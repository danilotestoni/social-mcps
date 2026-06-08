/**
 * One-time setup script: opens a visible Chromium window with a persistent profile
 * so you can log in to X manually. The session is stored in auth/x-profile/ and
 * reused by the post_to_x tool on every subsequent run.
 *
 * Run once with:  npm run setup-x
 * Re-run if X logs you out (roughly every 30 days of inactivity).
 */
import { chromium } from "./browser";
import * as path from "path";
import * as fs from "fs";

const AUTH_DIR = path.join(__dirname, "..", "auth");
// Persistent profile directory — the browser accumulates real state here over time.
// This is what makes X's bot detector treat it as a real browser.
const X_PROFILE_DIR = path.join(AUTH_DIR, "x-profile");

async function main(): Promise<void> {
  if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  }

  console.log("Abriendo Chromium con perfil persistente...");
  console.log("Inicia sesión en X manualmente. El script espera hasta x.com/home (timeout: 120s).\n");

  // launchPersistentContext keeps a real browser profile on disk.
  // Unlike newContext({ storageState }), this profile accumulates history,
  // cache, IndexedDB and other signals that castle.js uses to verify legitimacy.
  const context = await chromium.launchPersistentContext(X_PROFILE_DIR, {
    headless: false,
    slowMo: 50,
    viewport: { width: 1280, height: 800 },
    locale: "es-ES",
    args: [
      "--disable-blink-features=AutomationControlled",
      "--no-first-run",
      "--no-default-browser-check",
    ],
  });

  const page = await context.newPage();
  await page.goto("https://x.com/login");

  await page.waitForURL("**/home", { timeout: 120_000 });
  await page.waitForLoadState("networkidle").catch(() => {});

  await context.close();

  console.log(`\n✅ Perfil guardado en ${X_PROFILE_DIR}`);
  console.log("Ya puedes usar la tool post_to_x desde Claude.\n");
}

main().catch((err: unknown) => {
  console.error("Error durante el setup:", err);
  process.exit(1);
});
