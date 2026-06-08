/**
 * One-time setup script: opens a visible Chromium window so you can log in to
 * Facebook manually with your personal account, then saves the session to
 * auth/fb-session.json for reuse by the share_to_fb_feed tool.
 *
 * Run once with:  npm run setup-fb
 */
import { chromium } from "./browser";
import * as path from "path";
import * as fs from "fs";

const AUTH_DIR = path.join(__dirname, "..", "auth");
const AUTH_FILE = path.join(AUTH_DIR, "fb-session.json");

async function main(): Promise<void> {
  if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  }

  console.log("Abriendo Chromium. Inicia sesión en Facebook con tu cuenta PERSONAL...");
  console.log("El script espera hasta que llegues a facebook.com/home o al feed (timeout: 120s).\n");

  const browser = await chromium.launch({
    headless: false,
    slowMo: 50,
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });
  const page = await context.newPage();

  await page.goto("https://www.facebook.com/login");

  // Wait until the URL leaves the login flow (home feed, or any non-login page)
  await page.waitForURL(
    (url) => !url.pathname.includes("/login") && !url.pathname.includes("/checkpoint"),
    { timeout: 120_000 }
  );

  // Let the page settle so cookies and storage are fully written
  await page.waitForLoadState("networkidle").catch(() => {});

  await context.storageState({ path: AUTH_FILE });

  console.log(`\n✅ Sesión guardada en ${AUTH_FILE}`);
  console.log("Ya puedes usar la tool share_to_fb_feed desde Claude.\n");

  await browser.close();
}

main().catch((err: unknown) => {
  console.error("Error durante el setup:", err);
  process.exit(1);
});
