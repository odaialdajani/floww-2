/**
 * docs/solstice/capture-solstice.mjs — R8-06 browser capture receipt script.
 *
 * Captures real pixels of the RUNNING app (backend + frontend dev servers)
 * at desktop + narrow viewports: single grid, selected-wall inspector,
 * GEX+VEX compare. Requires: backend on $BACKEND_URL (default
 * http://127.0.0.1:8000), frontend on $FRONTEND_URL (default
 * http://127.0.0.1:3000), playwright-core + a Chromium executable
 * (PW_CHROMIUM_EXE) installed. Not part of product flows or test gates.
 *
 * Usage:
 *   npm i -g playwright-core   # or local install; browsers NOT needed
 *   PW_CHROMIUM_EXE=/path/to/chrome node docs/solstice/capture-solstice.mjs
 *
 * R8 environment notes (25 Sep 2026, macOS):
 * - playwright `page.screenshot()` hangs on webfont load; this script uses
 *   CDP Page.captureScreenshot instead (no font wait).
 * - The repo's kill-switch service-worker.js reloads pages on 127.0.0.1
 *   unless loopback is excluded (fixed R8-06 in frontend/public/index.html);
 *   without that fix every capture lands mid-reload and all data fetches
 *   abort. If captures come back blank, check for a reload loop first.
 */
import { chromium } from "playwright-core";
import fs from "node:fs";

const BASE = process.env.FRONTEND_URL || "http://127.0.0.1:3007";
const OUT = process.env.SHOTS_DIR || "docs/solstice/r8-shots";
const EXE = process.env.PW_CHROMIUM_EXE;
if (!EXE) {
  console.error("Set PW_CHROMIUM_EXE to a Chromium executable path.");
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });

async function shot(ctx, page, path) {
  const cdp = await ctx.newCDPSession(page);
  const { data } = await cdp.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path, Buffer.from(data, "base64"));
}

const browser = await chromium.launch({
  executablePath: EXE,
  headless: true,
  args: ["--disable-dev-shm-usage", "--no-sandbox",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows"],
});
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
const page = await ctx.newPage();
page.on("pageerror", (e) => console.log("PAGEERROR:", String(e).slice(0, 160)));
await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForSelector(".skylit-main-area", { timeout: 100000 });
await page.waitForTimeout(15000);
// Click the 30th grid cell to mount the selected-wall inspector.
const cells = page.locator("td.trin-cell");
if (await cells.count()) await cells.nth(30).click({ timeout: 8000 });
await page.waitForTimeout(3000);
await shot(ctx, page, `${OUT}/inspector-desktop.png`);
console.log("inspector ok");
const toggle = page.getByTestId("skylit-compare-toggle");
if (await toggle.count()) {
  await toggle.first().click();
  await page.waitForTimeout(4000);
  await shot(ctx, page, `${OUT}/compare-desktop.png`);
  console.log("compare ok");
  await toggle.first().click();
  await page.waitForTimeout(1500);
}
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(3000);
await shot(ctx, page, `${OUT}/single-narrow.png`);
console.log("narrow ok");
await browser.close();
