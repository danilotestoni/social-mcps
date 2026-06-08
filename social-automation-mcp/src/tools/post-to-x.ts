import { chromium } from "../browser";
import * as path from "path";
import * as fs from "fs";

// Persistent profile created by npm run setup-x
const X_PROFILE_DIR = path.join(__dirname, "..", "..", "auth", "x-profile");

// TODO: Update these selectors if X changes its UI — they break occasionally after redesigns.
// All selectors use data-testid attributes which are more stable than class names.
const SELECTORS = {
  // Main tweet compose area visible at the top of the home feed
  composeBox: '[data-testid="tweetTextarea_0"]',
  // Floating "Post" / "+" button in the left sidebar (opens a dialog compose box)
  postFab: '[data-testid="SideNav_NewTweet_Button"]',
  // "Post" submit button inside the compose area
  tweetButton: '[data-testid="tweetButtonInline"]',
  // Success toast shown after a tweet is published
  successToast: '[data-testid="toast"]',
};

const TIMEOUT_MS = 30_000;

export async function postToX(text: string): Promise<{
  success: boolean;
  url?: string;
  error?: string;
}> {
  if (!fs.existsSync(X_PROFILE_DIR)) {
    return {
      success: false,
      error:
        "No se encontró el perfil de X. Ejecuta 'npm run setup-x' primero para autenticar.",
    };
  }

  // Reuse the same persistent profile from setup — already logged in, real browser state.
  const context = await chromium.launchPersistentContext(X_PROFILE_DIR, {
    headless: true,
    viewport: { width: 1280, height: 800 },
    locale: "es-ES",
    args: [
      "--disable-blink-features=AutomationControlled",
      "--no-first-run",
      "--no-default-browser-check",
    ],
  });

  const page = await context.newPage();

  try {
    page.setDefaultTimeout(TIMEOUT_MS);

    await page.goto("https://x.com/home", {
      waitUntil: "domcontentloaded",
      timeout: TIMEOUT_MS,
    });

    // Detect session expiry
    const currentUrl = page.url();
    if (currentUrl.includes("/login") || currentUrl.includes("/i/flow")) {
      return {
        success: false,
        error:
          "La sesión ha expirado. Ejecuta 'npm run setup-x' de nuevo para renovar la autenticación.",
      };
    }

    // Try to locate the inline compose box at the top of the home feed.
    // If not immediately visible, click the sidebar "+ Post" FAB to open a dialog.
    let composeBox = page.locator(SELECTORS.composeBox).first();
    const isVisible = await composeBox.isVisible().catch(() => false);

    if (!isVisible) {
      await page.locator(SELECTORS.postFab).click({ timeout: 10_000 });
      composeBox = page.locator(SELECTORS.composeBox).first();
    }

    // Click the compose area and fill the tweet text.
    // If X changes its rich-text editor, switch to:
    //   await composeBox.click(); await page.keyboard.type(text);
    await composeBox.click({ timeout: 10_000 });
    await composeBox.fill(text);

    const publishButton = page.locator(SELECTORS.tweetButton).first();
    await publishButton.waitFor({ state: "visible", timeout: 10_000 });
    await publishButton.click();

    let tweetUrl: string | undefined;
    try {
      const toast = page.locator(SELECTORS.successToast).first();
      await toast.waitFor({ state: "visible", timeout: 15_000 });

      const viewLink = toast.locator("a").first();
      const href = await viewLink.getAttribute("href").catch(() => null);
      if (href) {
        tweetUrl = href.startsWith("http") ? href : `https://x.com${href}`;
      }
    } catch {
      // Toast not found — tweet was probably still published
    }

    return { success: true, ...(tweetUrl ? { url: tweetUrl } : {}) };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      error: `Error durante la publicación en X: ${message}`,
    };
  } finally {
    await context.close();
  }
}
