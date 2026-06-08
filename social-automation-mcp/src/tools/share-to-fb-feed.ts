import { chromium } from "../browser";
import * as path from "path";
import * as fs from "fs";

const AUTH_FILE = path.join(__dirname, "..", "..", "auth", "fb-session.json");

const TIMEOUT_MS = 30_000;

// TODO: Update these selectors if Facebook changes its UI.
// Facebook does NOT use data-testid consistently; role + text selectors are more stable.
const SELECTORS = {
  // Cookie/consent banner accept button (common in Europe)
  cookieAccept: '[data-cookiebanner="accept_button"], [data-testid="cookie-policy-manage-dialog-accept-button"]',
  // "Share" button in the post action bar (below a post)
  shareButton: '[aria-label="Send this to friends or post it on your profile."], [aria-label="Share"], [aria-label="Compartir"]',
  // "Share to Feed" menu item in the dropdown that appears after clicking Share
  shareToFeedItem: '[role="menuitem"]',
  // Text area inside the share compose dialog (contenteditable)
  composeArea: '[role="dialog"] [contenteditable="true"]',
  // "Post" / "Publicar" submit button inside the share dialog
  postButton: '[role="dialog"] [role="button"]',
};

// Text patterns for "Share to Feed" in different Facebook languages
const SHARE_TO_FEED_TEXT = /share to feed|compartir en el feed|compartir en el muro/i;

// Text patterns for the final "Post" button
const POST_BUTTON_TEXT = /^(post|publicar)$/i;

export async function shareToFbFeed(
  postUrl: string,
  message?: string,
  dryRun = false
): Promise<{ success: boolean; dry_run?: boolean; payload?: object; error?: string }> {
  if (dryRun) {
    return {
      success: true,
      dry_run: true,
      payload: { post_url: postUrl, message: message ?? null, platform: "facebook_personal" },
    };
  }

  if (!fs.existsSync(AUTH_FILE)) {
    return {
      success: false,
      error:
        "No se encontró la sesión de Facebook. Ejecuta 'npm run setup-fb' primero para autenticar.",
    };
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    storageState: AUTH_FILE,
    viewport: { width: 1280, height: 800 },
  });
  const page = await context.newPage();

  try {
    page.setDefaultTimeout(TIMEOUT_MS);

    await page.goto(postUrl, { waitUntil: "domcontentloaded", timeout: TIMEOUT_MS });

    // Detect session expiry
    const currentUrl = page.url();
    if (currentUrl.includes("/login") || currentUrl.includes("/checkpoint")) {
      return {
        success: false,
        error:
          "La sesión de Facebook ha expirado. Ejecuta 'npm run setup-fb' de nuevo para renovar la autenticación.",
      };
    }

    // Dismiss cookie/GDPR banner if present (common in EU)
    const cookieBanner = page.locator(SELECTORS.cookieAccept).first();
    if (await cookieBanner.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await cookieBanner.click().catch(() => {});
      await page.waitForTimeout(500);
    }

    // --- Step 1: Click the Share button on the post ---
    // Try aria-label selectors first, then fall back to role+text
    let shareButton = page.locator(SELECTORS.shareButton).first();
    const shareButtonVisible = await shareButton.isVisible({ timeout: 8_000 }).catch(() => false);

    if (!shareButtonVisible) {
      // Fallback: find by button role with matching text
      shareButton = page.getByRole("button", { name: /^(share|compartir)$/i }).last();
      await shareButton.waitFor({ state: "visible", timeout: 8_000 });
    }

    await shareButton.click();

    // --- Step 2: Click "Share to Feed" in the dropdown ---
    // Wait for menu to appear and find the right item by text
    const shareToFeedItem = page
      .locator(SELECTORS.shareToFeedItem)
      .filter({ hasText: SHARE_TO_FEED_TEXT })
      .first();

    await shareToFeedItem.waitFor({ state: "visible", timeout: 8_000 });
    await shareToFeedItem.click();

    // --- Step 3: Optionally type a message in the compose area ---
    if (message) {
      const composeArea = page.locator(SELECTORS.composeArea).first();
      await composeArea.waitFor({ state: "visible", timeout: 8_000 });
      await composeArea.click();
      await composeArea.fill(message);
    }

    // --- Step 4: Click the Post / Publicar button ---
    // The dialog has multiple buttons; the primary one matches "Post" or "Publicar"
    const postButton = page
      .locator(SELECTORS.postButton)
      .filter({ hasText: POST_BUTTON_TEXT })
      .last();

    await postButton.waitFor({ state: "visible", timeout: 8_000 });
    await postButton.click();

    // Wait for the dialog to close as confirmation that the post was submitted
    await page
      .locator('[role="dialog"]')
      .waitFor({ state: "hidden", timeout: 15_000 })
      .catch(() => {
        // Dialog might already be gone or use a different transition
      });

    return { success: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      error: `Error al compartir en Facebook: ${message}`,
    };
  } finally {
    await context.close();
    await browser.close();
  }
}
