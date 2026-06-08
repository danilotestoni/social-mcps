import { chromium } from "../browser";
import * as path from "path";
import * as fs from "fs";

const AUTH_FILE = path.join(__dirname, "..", "..", "auth", "x-session.json");

const SELECTORS = {
  composeBox: '[data-testid="tweetTextarea_0"]',
  tweetButton: '[data-testid="tweetButtonInline"]',
  successToast: '[data-testid="toast"]',
};

const TIMEOUT_MS = 30_000;

export async function postToX(
  text: string,
  dryRun = false
): Promise<{ success: boolean; url?: string; dry_run?: boolean; payload?: object; error?: string }> {
  if (dryRun) {
    return {
      success: true,
      dry_run: true,
      payload: { text, length: text.length, platform: "x" },
    };
  }

  if (!fs.existsSync(AUTH_FILE)) {
    return {
      success: false,
      error:
        "No se encontró la sesión de X. Ejecuta 'npm run import-x-cookies' o 'npm run setup-x' primero.",
    };
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    storageState: AUTH_FILE,
    viewport: { width: 1280, height: 800 },
    locale: "es-ES",
  });
  const page = await context.newPage();

  try {
    page.setDefaultTimeout(TIMEOUT_MS);

    await page.goto("https://x.com/compose/post", {
      waitUntil: "domcontentloaded",
      timeout: TIMEOUT_MS,
    });

    await page.waitForTimeout(2000);

    const currentUrl = page.url();
    if (currentUrl.includes("/login") || currentUrl.includes("/i/flow")) {
      return {
        success: false,
        error:
          "La sesión ha expirado. Ejecuta 'npm run import-x-cookies' de nuevo para renovar la autenticación.",
      };
    }

    // compose/post has two tweetTextarea_0 instances: inline home feed + modal dialog.
    // .last() targets the modal compose box (inside #layers).
    // The mask overlay in #layers blocks coordinate-based clicks, so we use focus()
    // which calls JS element.focus() directly — bypasses the overlay entirely.
    const composeBox = page.locator(SELECTORS.composeBox).last();
    await composeBox.waitFor({ state: "visible", timeout: TIMEOUT_MS });
    await composeBox.focus();

    // Give React time to process the focus event before we start typing
    await page.waitForTimeout(200);

    // keyboard.type() fires individual key events which DraftJS/React picks up.
    // fill() bypasses synthetic events (Post button stays disabled).
    await page.keyboard.type(text, { delay: 30 });

    const publishButton = page.locator(SELECTORS.tweetButton).last();
    await publishButton.waitFor({ state: "visible", timeout: 10_000 });

    // Poll until React enables the button.
    // waitForFunction with a string eval is blocked by X's CSP (unsafe-eval).
    const deadline = Date.now() + 10_000;
    let buttonEnabled = false;
    while (Date.now() < deadline) {
      if (await publishButton.isEnabled()) {
        buttonEnabled = true;
        break;
      }
      await page.waitForTimeout(200);
    }

    if (!buttonEnabled) {
      const debugPath = path.join(__dirname, "..", "..", "auth", "debug-no-text.png");
      await page.screenshot({ path: debugPath });
      return {
        success: false,
        error: `El texto no llegó al cuadro de composición (botón no se habilitó). Screenshot: ${debugPath}`,
      };
    }

    // The button is inside the modal inside #layers — evaluate() calls the DOM's
    // native .click() directly on the element, bypassing any z-index overlap check.
    await publishButton.evaluate((el) => (el as HTMLElement).click());

    // Wait for the confirmation toast — X always shows it on successful post.
    // If no toast appears, the tweet was not published.
    const toast = page.locator(SELECTORS.successToast).first();
    await toast.waitFor({ state: "visible", timeout: 20_000 });

    const viewLink = toast.locator("a").first();
    const href = await viewLink.getAttribute("href").catch(() => null);
    const tweetUrl = href
      ? href.startsWith("http")
        ? href
        : `https://x.com${href}`
      : undefined;

    return { success: true, ...(tweetUrl ? { url: tweetUrl } : {}) };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      error: `Error durante la publicación en X: ${message}`,
    };
  } finally {
    await context.close();
    await browser.close();
  }
}
