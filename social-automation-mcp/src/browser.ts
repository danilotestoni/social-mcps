import { chromium as chromiumExtra } from "playwright-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";

// Register stealth plugin once. It patches ~10 fingerprinting vectors that social
// platforms use to detect automated browsers: navigator.webdriver, Chrome runtime
// properties, user-agent inconsistencies, permissions API, plugins list, etc.
chromiumExtra.use(StealthPlugin());

export const chromium = chromiumExtra;
