/**
 * Health check for browser-based tools.
 * Opens each site with the stored session and verifies the session is still valid.
 * Nothing is published. Outputs a single JSON line to stdout.
 *
 * Usage: node build/check.js
 */
import { chromium } from "./browser";
import * as path from "path";
import * as fs from "fs";

const AUTH_DIR = path.join(__dirname, "..", "auth");
const AUTH_X = path.join(AUTH_DIR, "x-session.json");
const AUTH_FB = path.join(AUTH_DIR, "fb-session.json");

const TIMEOUT_MS = 20_000;

async function checkX(): Promise<{ success: boolean; data?: object; error?: string }> {
  if (!fs.existsSync(AUTH_X)) {
    return { success: false, error: "auth/x-session.json not found — run: npm run import-x-cookies" };
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: AUTH_X });
  const page = await context.newPage();
  try {
    await page.goto("https://x.com/home", { waitUntil: "domcontentloaded", timeout: TIMEOUT_MS });
    const url = page.url();
    if (url.includes("/login") || url.includes("/i/flow")) {
      return { success: false, error: "Session expired — run: npm run import-x-cookies" };
    }
    const title = await page.title().catch(() => "");
    return { success: true, data: { page_title: title } };
  } finally {
    await context.close();
    await browser.close();
  }
}

async function checkFb(): Promise<{ success: boolean; data?: object; error?: string }> {
  if (!fs.existsSync(AUTH_FB)) {
    return { success: false, error: "auth/fb-session.json not found — run: npm run setup-fb" };
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: AUTH_FB });
  const page = await context.newPage();
  try {
    await page.goto("https://www.facebook.com/", { waitUntil: "domcontentloaded", timeout: TIMEOUT_MS });
    const url = page.url();
    if (url.includes("/login") || url.includes("checkpoint")) {
      return { success: false, error: "Session expired — run: npm run setup-fb" };
    }
    const title = await page.title().catch(() => "");
    return { success: true, data: { page_title: title } };
  } finally {
    await context.close();
    await browser.close();
  }
}

async function main(): Promise<void> {
  const [x, fb] = await Promise.all([checkX(), checkFb()]);
  process.stdout.write(JSON.stringify({ x, facebook_personal: fb }) + "\n");
}

main().catch((err) => {
  process.stderr.write(String(err) + "\n");
  process.exit(1);
});
