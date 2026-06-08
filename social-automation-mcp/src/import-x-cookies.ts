/**
 * Converts a Cookie-Editor JSON export into Playwright's storageState format
 * and saves it to auth/x-session.json.
 *
 * Usage:
 *   1. Install Cookie-Editor extension in Chrome/Edge
 *   2. Go to x.com while logged in
 *   3. Click Cookie-Editor → Export → Export as JSON  (copies to clipboard)
 *   4. Paste clipboard into auth/cookies-export.json
 *   5. Run: npm run import-x-cookies
 */
import * as fs from "fs";
import * as path from "path";

const AUTH_DIR = path.join(__dirname, "..", "auth");
const INPUT_FILE = path.join(AUTH_DIR, "cookies-export.json");
const OUTPUT_FILE = path.join(AUTH_DIR, "x-session.json");

// Cookie-Editor sameSite values → Playwright sameSite values
const SAME_SITE_MAP: Record<string, "Strict" | "Lax" | "None"> = {
  strict: "Strict",
  lax: "Lax",
  no_restriction: "None",
  unspecified: "None",
};

interface CookieEditorCookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  expirationDate?: number;
  session?: boolean;
  httpOnly: boolean;
  secure: boolean;
  sameSite: string;
}

interface PlaywrightCookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  expires: number;
  httpOnly: boolean;
  secure: boolean;
  sameSite: "Strict" | "Lax" | "None";
}

function convert(raw: CookieEditorCookie[]): PlaywrightCookie[] {
  return raw.map((c) => ({
    name: c.name,
    value: c.value,
    domain: c.domain.startsWith(".") ? c.domain : `.${c.domain}`,
    path: c.path ?? "/",
    expires: c.session || !c.expirationDate ? -1 : Math.floor(c.expirationDate),
    httpOnly: c.httpOnly,
    secure: c.secure,
    sameSite: SAME_SITE_MAP[c.sameSite?.toLowerCase()] ?? "None",
  }));
}

function main(): void {
  if (!fs.existsSync(INPUT_FILE)) {
    console.error(`\nNo se encontró ${INPUT_FILE}`);
    console.error("Pasos:");
    console.error("  1. Instala Cookie-Editor en Chrome/Edge");
    console.error("  2. Ve a x.com con tu sesión activa");
    console.error("  3. Cookie-Editor → Export → Export as JSON");
    console.error(`  4. Guarda el JSON en ${INPUT_FILE}`);
    console.error("  5. Vuelve a ejecutar este script\n");
    process.exit(1);
  }

  const raw: CookieEditorCookie[] = JSON.parse(fs.readFileSync(INPUT_FILE, "utf-8"));

  if (!Array.isArray(raw) || raw.length === 0) {
    console.error("El archivo de cookies está vacío o no tiene el formato esperado.");
    process.exit(1);
  }

  const cookies = convert(raw);
  const storageState = { cookies, origins: [] };

  if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  }

  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(storageState, null, 2));

  // Verify the essential X session cookies are present
  const names = new Set(cookies.map((c) => c.name));
  const missing = ["auth_token", "ct0"].filter((n) => !names.has(n));

  if (missing.length > 0) {
    console.warn(`\n⚠️  Faltan cookies clave: ${missing.join(", ")}`);
    console.warn("Asegúrate de exportar desde x.com estando logueado.\n");
  } else {
    console.log(`\n✅ ${cookies.length} cookies importadas → ${OUTPUT_FILE}`);
    console.log("Ya puedes usar la tool post_to_x desde Claude.\n");
  }
}

main();
