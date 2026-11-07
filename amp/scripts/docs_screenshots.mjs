#!/usr/bin/env node
/**
 * Screenshots for the documentation site (docs/assets/screenshots/*.webp).
 *
 * Drives headless Edge/Chrome over the DevTools protocol (Node >= 22: built-in WebSocket,
 * no dependency). Needs, already running:
 *   - a backend on :8000 with a SCRATCH data dir (this script adds history entries and saved queues):
 *       python -m backend.main --data-dir <tmp dir>
 *   - the Vite dev server on :1420:  cd frontend && npm run dev
 *
 * Usage (from amp/):  node scripts/docs_screenshots.mjs [--browser <path>] [--out <dir>]
 */
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) =>
  (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const BROWSER = args.browser ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const OUT = resolve(args.out ?? "../docs/assets/screenshots");
const APP = "http://127.0.0.1:1420";
const API = "http://127.0.0.1:8000";
const PORT = 9333;
const WIDTH = 1440;
const HEIGHT = 900;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- Minimal CDP client -----------------------------------------------------

async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { ok, fail } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? fail(new Error(msg.error.message)) : ok(msg.result);
    }
  };
  const send = (method, params = {}) => new Promise((ok, fail) => {
    pending.set(++id, { ok, fail });
    ws.send(JSON.stringify({ id, method, params }));
  });
  return { send, close: () => ws.close() };
}

async function openPage(url) {
  const res = await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent(url)}`, { method: "PUT" });
  const target = await res.json();
  const page = await connect(target.webSocketDebuggerUrl);
  await page.send("Emulation.setDeviceMetricsOverride", { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  return page;
}

async function evaluate(page, expression) {
  const r = await page.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`${r.exceptionDetails.text}: ${r.exceptionDetails.exception?.description}`);
  return r.result.value;
}

async function go(page, path, settleMs = 2500) {
  await page.send("Page.navigate", { url: APP + path });
  await sleep(settleMs);
}

/** In-app navigation (keeps playback, unlike Page.navigate). */
async function route(page, path, settleMs = 1800) {
  await evaluate(page, `(() => { history.pushState({}, "", ${JSON.stringify(path)}); dispatchEvent(new PopStateEvent("popstate")); })()`);
  await sleep(settleMs);
}

async function shot(page, name, clip) {
  const { data } = await page.send("Page.captureScreenshot", { format: "webp", quality: 88, ...(clip ? { clip: { ...clip, scale: 1 } } : {}) });
  writeFileSync(join(OUT, `${name}.webp`), Buffer.from(data, "base64"));
  console.log(`  ${name}.webp`);
}

// --- Seed data (through the API, into the scratch backend) -----------------

async function api(path, init) {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

async function seed() {
  const queries = ["Daft Punk", "Dua Lipa", "Ava Max", "The Weeknd", "Billie Eilish", "Stromae"];
  const lists = [];
  for (const q of queries) lists.push(await api(`/api/search?q=${encodeURIComponent(q)}&type=songs&limit=8`));
  const mix = lists.flatMap((l) => l.slice(0, 3));
  const now = Date.now();
  const reasons = ["finished", "finished", "skipped", "finished", "stopped", "finished", "skipped", "finished"];
  for (let i = 0; i < 16; i++) {
    const song = mix[i % mix.length];
    const pct = reasons[i % reasons.length] === "finished" ? 0.97 + (i % 3) * 0.01 : 0.2 + (i % 5) * 0.12;
    await api("/api/history", { method: "POST", body: JSON.stringify({
      song, duration_ms: song.duration_ms, listened_ms: Math.round(song.duration_ms * pct),
      started_at: new Date(now - (i < 9 ? i * 14 : 26 * 60 + i * 9) * 60_000).toISOString(),
      end_reason: reasons[i % reasons.length],
    }) });
  }
  for (const [name, idx] of [["Morning run", 1], ["Focus", 4], ["Throwbacks", 0], ["Late night", 3]]) {
    await api("/api/queues", { method: "POST", body: JSON.stringify({ name, songs: lists[idx] }) });
  }
  return lists[0];
}

// --- Scenario --------------------------------------------------------------

async function main() {
  mkdirSync(OUT, { recursive: true });
  const profile = mkdtempSync(join(tmpdir(), "amp-shots-"));
  const browser = spawn(BROWSER, [
    "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--autoplay-policy=no-user-gesture-required", "--mute-audio", "--hide-scrollbars",
    `--window-size=${WIDTH},${HEIGHT}`, "about:blank",
  ], { stdio: "ignore" });
  try {
    for (let i = 0; i < 50; i++) {
      try { await fetch(`http://127.0.0.1:${PORT}/json/version`); break; } catch { await sleep(200); }
    }
    console.log("Seeding history and saved queues…");
    const songs = await seed();

    const page = await openPage(APP + "/");
    await sleep(2500);

    console.log("Dark theme:");
    // Search for real results, then play the list from the 2nd song
    await evaluate(page, `(() => {
      const input = document.querySelector(".search-input");
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "Daft Punk");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.form.requestSubmit();
    })()`);
    await sleep(3000);
    await evaluate(page, `(async () => {
      const { store } = await import("/src/state.ts");
      store.playList(${JSON.stringify(songs)}, 1);
    })()`);
    await sleep(9000);
    await evaluate(page, `(async () => { const { store } = await import("/src/state.ts"); store.setAudioTime(74); })()`);
    await sleep(2500);
    await shot(page, "search");

    // OBS widget, transparent, while the song plays
    const widget = await openPage("http://127.0.0.1:8001/?w=420&h=96");
    await widget.send("Emulation.setDefaultBackgroundColorOverride", { color: { r: 0, g: 0, b: 0, a: 0 } });
    await sleep(2500);
    const { data } = await widget.send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: 420, height: 96, scale: 2 } });
    writeFileSync(join(OUT, "widget.png"), Buffer.from(data, "base64"));
    console.log("  widget.png");
    widget.close();

    for (const [path, name] of [["/history", "history"], ["/queues", "saved-queues"], ["/settings", "settings"], ["/developer", "developer"]]) {
      await route(page, path, path === "/developer" ? 3500 : 2000);
      await shot(page, name);
    }

    console.log("Light theme:");
    await evaluate(page, `localStorage.setItem("amp.settings.v1", JSON.stringify({ theme: "light", accent: "#b47cff", fadeSec: 3 }))`);
    await go(page, "/history", 3000);
    await shot(page, "history-light");
    await route(page, "/settings");
    await shot(page, "settings-light");
    await evaluate(page, `localStorage.setItem("amp.settings.v1", JSON.stringify({ theme: "dark", accent: "#ff4d67", fadeSec: 0 }))`);
    page.close();
  } finally {
    browser.kill();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
