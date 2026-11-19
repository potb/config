import { chmodSync, existsSync, mkdirSync, readdirSync, readFileSync, realpathSync } from "node:fs";
import { execFile } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);
const DIR = join(homedir(), ".config/herdr-app/data/ai-spend");
const VERCEL_TEAM = "potb-team";
const VERSIONS = join(homedir(), ".local/share/fnm/node-versions");
const VERCEL = (existsSync(VERSIONS) ? readdirSync(VERSIONS) : [])
  .map((v) => join(VERSIONS, v, "installation/bin/vercel"))
  .filter((p) => existsSync(p))
  .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
  .at(-1) ?? "vercel";

const keyOf = (name) => {
  const file = join(DIR, `${name}.key`);
  if (!existsSync(file)) return null;
  chmodSync(file, 0o600);
  return readFileSync(file, "utf8").trim() || null;
};

const num = (v) => (v == null || v === "" || Number.isNaN(Number(v)) ? null : Number(v));

const windows = () => {
  const now = new Date();
  const day = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const week = new Date(day.getTime() - ((day.getUTCDay() + 6) % 7) * 86400000);
  const month = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  return { today: day, week, month };
};

async function openrouter() {
  const key = keyOf("openrouter");
  if (!key) return { id: "openrouter", name: "OpenRouter", missing: true };
  const get = async (path) => {
    const r = await fetch(`https://openrouter.ai/api/v1/${path}`, { headers: { authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(15000) });
    if (r.status === 401 || r.status === 403) throw new Error("key rejected, needs a management key");
    if (!r.ok) throw new Error(`OpenRouter HTTP ${r.status}`);
    return (await r.json()).data;
  };
  const [keys, credits] = await Promise.all([get("keys"), get("credits").catch(() => null)]);
  const sum = (field) => (keys ?? []).reduce((a, k) => a + (num(k[field]) ?? 0), 0);
  const balance = credits && num(credits.total_credits) != null ? num(credits.total_credits) - num(credits.total_usage) : null;
  return { id: "openrouter", name: "OpenRouter", today: sum("usage_daily"), week: sum("usage_weekly"), month: sum("usage_monthly"), balance };
}

async function vercel() {
  const cost = async (since) => {
    const { stdout } = await run(process.execPath, [realpathSync(VERCEL),"--scope", VERCEL_TEAM, "metrics", "vercel.ai_gateway.request.cost", "--all", "--since", since.toISOString(), "--json"], { timeout: 30000 });
    return num(JSON.parse(stdout.slice(stdout.indexOf("{"))).summary?.[0]?.vercel_ai_gateway_request_cost_sum) ?? 0;
  };
  const w = windows();
  const [today, week, month] = await Promise.all([cost(w.today), cost(w.week), cost(w.month)]);
  let balance = null;
  const key = keyOf("vercel");
  if (key) {
    try {
      const r = await fetch("https://ai-gateway.vercel.sh/v1/credits", { headers: { authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(15000) });
      if (r.ok) balance = num((await r.json()).balance);
    } catch {}
  }
  return { id: "vercel", name: "Vercel AI Gateway", today, week, month, balance };
}

mkdirSync(DIR, { recursive: true, mode: 0o700 });
const names = { openrouter: "OpenRouter", vercel: "Vercel AI Gateway" };
const providers = await Promise.all(Object.entries({ openrouter, vercel }).map(([id, f]) =>
  f().catch((e) => ({ id, name: names[id], error: String(e?.stderr || e?.message || e).trim().split("\n").pop().slice(0, 120) }))));
process.stdout.write(JSON.stringify({ at: Date.now(), providers }));
