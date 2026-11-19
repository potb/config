import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, watchFile, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

const BASE = process.env.RAKAZO_URL || "https://app.rakazo.com";
const STATE_DIR = join(homedir(), ".local/share/rakazo");
const SESSION = join(STATE_DIR, "session.json");
const SCRIPT = fileURLToPath(import.meta.url);
const HERDR_SPACE = "rakazo";
const HISTORY = 200;
const HERDR_HOME = join(homedir(), ".config/herdr-app");
const CHATS = join(HERDR_HOME, "data/rakazo");
const CHAT_MOD = "rakazo-chat";
const PROGRAMS = join(HERDR_HOME, "programs.json");
const ICONS = join(HERDR_HOME, "my-icons");
const appOf = (botId) => `rakazo-${botId}`.slice(0, 32);
const tabOf = (botId) => `tbrk${botId}`;
const chatFile = (botId) => join(CHATS, `${botId}.json`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const b64 = (s) => Buffer.from(String(s ?? ""), "utf8").toString("base64");
const out = (s) => process.stdout.write(s);

function loadSession() {
  try {
    return JSON.parse(readFileSync(SESSION, "utf8"));
  } catch {
    return null;
  }
}

function saveSession(session) {
  mkdirSync(STATE_DIR, { recursive: true, mode: 0o700 });
  chmodSync(STATE_DIR, 0o700);
  writeFileSync(SESSION, JSON.stringify(session), { mode: 0o600 });
  chmodSync(SESSION, 0o600);
}

class AuthError extends Error {}

function headers(token, spaceId, extra = {}) {
  return {
    "content-type": "application/json",
    origin: "rakazo://",
    ...(token ? { authorization: `Bearer ${token}` } : {}),
    ...(spaceId ? { "x-rakazo-space-id": spaceId } : {}),
    ...extra,
  };
}

async function rpc(proc, input, { spaceId, signal } = {}) {
  const session = loadSession();
  if (!session?.token) throw new AuthError("Not signed in to Rakazo.");
  const res = await fetch(`${BASE}/rpc/${proc}`, {
    method: "POST",
    headers: headers(session.token, spaceId),
    body: JSON.stringify({ json: input ?? {} }),
    signal,
  });
  const text = await res.text();
  let body = {};
  try {
    body = JSON.parse(text);
  } catch {}
  if (res.status === 401) throw new AuthError("Rakazo session expired.");
  if (!res.ok) throw new Error(`${proc}: ${body?.json?.message || res.status}`);
  return body.json;
}

async function* subscribe(proc, input, { spaceId, signal }) {
  const session = loadSession();
  if (!session?.token) throw new AuthError("Not signed in to Rakazo.");
  const res = await fetch(`${BASE}/rpc/${proc}`, {
    method: "POST",
    headers: headers(session.token, spaceId, { accept: "text/event-stream" }),
    body: JSON.stringify({ json: input }),
    signal,
  });
  if (res.status === 401) throw new AuthError("Rakazo session expired.");
  if (!res.ok || !res.body) throw new Error(`${proc}: ${res.status}`);
  const decoder = new TextDecoder();
  let buffer = "";
  for await (const chunk of res.body) {
    buffer += decoder.decode(chunk, { stream: true }).replace(/\r\n/g, "\n");
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("");
      if (!data || data === "[DONE]") continue;
      try {
        const parsed = JSON.parse(data);
        if (parsed.json?.type) yield parsed.json;
      } catch {}
    }
  }
}

async function postAuth(path, input) {
  const res = await fetch(`${BASE}/api/auth/${path}`, {
    method: "POST",
    headers: headers(null, null),
    body: JSON.stringify(input),
  });
  let body = {};
  try {
    body = await res.json();
  } catch {}
  if (!res.ok) throw new Error(body?.message || `connexion refusee (${res.status})`);
  const cookie = res.headers.get("set-cookie") ?? "";
  const raw =
    res.headers.get("set-auth-token") ||
    cookie.match(/(?:^|,\s*)(?:__Secure-)?better-auth\.session_token=([^;,]*)/)?.[1] ||
    body?.token;
  return raw ? decodeURIComponent(raw) : null;
}

function ask(rl, question, hidden = false) {
  return new Promise((resolve) => {
    if (!hidden) return rl.question(question, (a) => resolve(a.trim()));
    const write = rl._writeToOutput;
    rl._writeToOutput = (s) => {
      if (s.includes(question)) write.call(rl, s);
    };
    rl.question(question, (a) => {
      rl._writeToOutput = write;
      out("\n");
      resolve(a.trim());
    });
  });
}

async function login() {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  out("Sign in to Rakazo (rakazo.com)\n\n");
  const email = await ask(rl, "Email: ");
  const mode = (await ask(rl, "Email code (c) or password (p)? [c]: ")).toLowerCase();
  let token;
  if (mode === "p") {
    const password = await ask(rl, "Password: ", true);
    token = await postAuth("sign-in/email", { email, password });
  } else {
    await postAuth("email-otp/send-verification-otp", { email, type: "sign-in" });
    const otp = await ask(rl, "Code from the email: ");
    token = await postAuth("sign-in/email-otp", { email, otp });
  }
  rl.close();
  if (!token) throw new Error("Rakazo returned no session.");
  saveSession({ token, email, at: new Date().toISOString() });
  out("\nSigned in. Opening your bots in herdr...\n");
  await sync();
  out("Done: your bots are in the Rakazo space of the sidebar.\n");
}

async function logout() {
  const session = loadSession();
  if (session?.token) {
    await fetch(`${BASE}/api/auth/sign-out`, { method: "POST", headers: headers(session.token, null), body: "{}" }).catch(() => {});
  }
  rmSync(SESSION, { force: true });
  for (const t of rakazoTerminals()) spawnSync("hc", ["kill", t.address]);
  out("Signed out.\n");
}

function hcJson(args) {
  const r = spawnSync("hc", [...args, "--json"], { encoding: "utf8" });
  try {
    return JSON.parse(r.stdout);
  } catch {
    return null;
  }
}

function rakazoTerminals() {
  const list = hcJson(["ls", "--label", `herdr.space=${HERDR_SPACE}`]);
  const rows = Array.isArray(list) ? list : (list?.terminals ?? []);
  return rows;
}

function herdr(command, args) {
  const r = spawnSync("herdr-app", ["do", command, JSON.stringify(args)], { encoding: "utf8", timeout: 5000 });
  try {
    return JSON.parse(r.stdout);
  } catch {
    return null;
  }
}

function herdrPaneOf(terminal) {
  const r = spawnSync("herdr-app", ["ls"], { encoding: "utf8", timeout: 5000 });
  try {
    for (const space of JSON.parse(r.stdout).spaces ?? [])
      for (const tab of space.tabs ?? []) for (const t of tab.terminals ?? []) if (t.terminal === terminal) return t.pane;
  } catch {}
  return null;
}

async function allBots() {
  const nav = await rpc("spaces/list", {});
  const spaces = nav?.spaces?.length ? nav.spaces : [{ id: nav.current.id, name: nav.current.name }];
  const bots = [];
  for (const space of spaces) {
    const list = space.id === nav.current.id ? nav.current.bots : await rpc("bots/list", {}, { spaceId: space.id });
    for (const bot of list ?? []) if (!bot.archivedAt) bots.push({ ...bot, spaceId: space.id, spaceName: space.name });
  }
  return { bots, many: spaces.length > 1 };
}

async function bubbleOf(bot) {
  try {
    const { chatUserBubbleColors } = await import(join(HERDR_HOME, "tools/rakazo-avatar.mjs"));
    return chatUserBubbleColors(bot.color ?? "", bot.id) ?? null;
  } catch {
    return null;
  }
}

async function writeLooks(bots) {
  let avatar = null;
  try {
    avatar = (await import(join(HERDR_HOME, "tools/rakazo-avatar.mjs"))).notificationAvatarSource;
  } catch {}
  let config = { programs: {} };
  try {
    config = JSON.parse(readFileSync(PROGRAMS, "utf8"));
  } catch {}
  config.programs ??= {};
  for (const key of Object.keys(config.programs)) if (key.startsWith("rakazo-") && key !== "rakazo-login") delete config.programs[key];
  mkdirSync(ICONS, { recursive: true });
  for (const bot of bots) {
    let icon = "my-icons/rakazo.png";
    try {
      const src = avatar?.({ id: bot.id, color: bot.color, avatarSet: bot.avatarSet ?? null });
      if (src?.startsWith("data:image/svg+xml,")) {
        writeFileSync(join(ICONS, `rakazo-${bot.id}.svg`), decodeURIComponent(src.slice(19)));
        icon = `my-icons/rakazo-${bot.id}.svg`;
      }
    } catch {}
    config.programs[appOf(bot.id)] = { name: bot.name, icon, tint: false };
  }
  const next = `${JSON.stringify(config, null, 2)}\n`;
  let previous = "";
  try {
    previous = readFileSync(PROGRAMS, "utf8");
  } catch {}
  if (next !== previous) writeFileSync(PROGRAMS, next);
}

function tabTerminals(botId) {
  const list = hcJson(["ls", "--label", `herdr.tab=${tabOf(botId)}`]);
  return Array.isArray(list) ? list : (list?.terminals ?? []);
}

async function openTab(bot, title) {
  const started = hcJson([
    "run", "--bg", "--no-parent", "--keep", "--cwd", homedir(),
    "--label", `herdr.space=${HERDR_SPACE}`, "--label", `herdr.tab=${tabOf(bot.id)}`,
    "--", process.execPath, SCRIPT, "bridge", bot.spaceId, bot.id,
  ]);
  const address = started?.address ?? started?.terminal ?? tabTerminals(bot.id)[0]?.address;
  let pane = null;
  for (let i = 0; i < 20 && !pane && address; i++) {
    await sleep(250);
    pane = herdrPaneOf(address);
  }
  if (!pane) return;
  const split = herdr("pane.split", { direction: "right", pane, mod: CHAT_MOD, props: { botId: bot.id, spaceId: bot.spaceId } });
  if (split?.pane) herdr("pane.zoom", { pane: split.pane });
  herdr("tab.rename", { id: tabOf(bot.id), name: title });
}

async function sync() {
  const { bots, many } = await allBots();
  await writeLooks(bots);
  const wanted = new Set(bots.map((b) => appOf(b.id)));
  for (const bot of bots) {
    const mine = tabTerminals(bot.id);
    const healthy = mine.filter((t) => t.state === "live" && t.agent === appOf(bot.id));
    if (healthy.length === 1 && mine.length === 1) continue;
    for (const t of mine) spawnSync("hc", ["kill", t.address]);
    herdr("tab.close", { id: tabOf(bot.id), confirmed: true });
    await sleep(500);
    await openTab(bot, many ? `${bot.name} (${bot.spaceName})` : bot.name);
  }
  for (const t of rakazoTerminals()) if (String(t.agent ?? "").startsWith("rakazo-") && !wanted.has(t.agent)) spawnSync("hc", ["kill", t.address]);
  bots.forEach((bot, index) => herdr("tab.move", { id: tabOf(bot.id), index }));
  herdr("space.rename", { id: HERDR_SPACE, name: "Rakazo" });
  return bots.length;
}

const ANSWERS = { allow: "allowed once", always: "always allowed", deny: "denied" };
const reviewed = (text) => String(text ?? "").replace(/^Review before\s+/i, "");

function partsOf(blocks = []) {
  const md = [];
  const chips = [];
  const bots = [];
  for (const b of blocks) {
    if (b.kind === "text") md.push(b.text);
    else if (b.kind === "child_bot") {
      if (b.status === "created") bots.push({ id: b.botId, name: b.name });
      else chips.push(`${b.status === "archived" ? "Archived" : "Deleted"} bot ${b.name}`);
    }
    else if (b.kind === "ask" && b.input === "secret") {
      const site = hostOf(b.credential?.origin ?? b.oneTimeCode?.origin) ?? b.text ?? "";
      const what = b.oneTimeCode ? "Code" : "Login";
      const done = b.status && b.status !== "pending";
      chips.push(!done ? `${what} requested: ${site}` : b.dismissed ? `${what} declined: ${site}` : b.oneTimeCode || b.remembered === false ? `${what} sent: ${site}` : `${what} saved: ${site}`);
    } else if (b.kind === "ask") {
      const tool = /^Review before/i.test(b.text ?? "");
      if (!tool) md.push([b.text, b.detail].filter(Boolean).join("\n\n"));
      if (tool && b.status && b.status !== "pending") chips.push(`${reviewed(b.text)}: ${ANSWERS[b.answer] ?? b.answer ?? "answered"}`);
      const picked = (b.actions ?? []).find((a) => a.id === b.answer);
      if (!tool && picked) chips.push(`Chose: ${picked.label}`);
    } else if (b.kind === "choice") {
      if (b.answerId || (b.status && b.status !== "pending")) chips.push(`${b.question}: answered`);
    } else if (b.kind === "card") md.push((b.lines ?? []).map((l) => `- **${l.k}** : ${l.v}`).join("\n"));
    else if (b.kind === "computer") md.push(`> **Shared screen** (${String(b.state ?? "").toLowerCase()})\n>\n> ${String(b.text ?? "").replace(/\n/g, "\n> ")}`);
    else if (b.kind === "mcp_approval") chips.push(`Connector ${b.name}: ${b.status === "connected" ? "connected" : (b.status ?? "pending")}`);
    else if (b.kind === "app_connect") chips.push(`Connect ${b.name ?? "an app"} in the Rakazo app`);
    else if (b.kind === "bot_message_sent") chips.push(`Messaged ${b.toBotName ?? "a bot"}`);
    else if (b.kind === "bot_message_received") chips.push(`Message from ${b.fromBotName ?? "a bot"}`);
    else if (b.kind === "image") chips.push(`Image: ${b.name ?? "untitled"}`);
    else if (b.kind === "file" || b.kind === "artifact") chips.push(`File: ${b.name ?? b.title ?? "untitled"}`);
    else if (b.kind === "import_setup") chips.push(`Import: ${(b.items ?? []).map((i) => i.name).filter(Boolean).join(", ")}`);
    else if (!QUIET.has(b.kind)) chips.push(`${b.kind}: open the Rakazo app to see it`);
  }
  return { md: md.filter(Boolean).join("\n\n"), chips, bots };
}

const QUIET = new Set(["steps", "reaction", "reactions", "meta", "progress"]);
const hostOf = (origin) => {
  try {
    return new URL(origin).host;
  } catch {
    return null;
  }
};
const pendingAsk = (b) => !b.status || b.status === "pending";

function askOf(m) {
  for (const b of m.blocks ?? []) {
    if (b.kind === "choice" && !b.answerId)
      return { messageId: m.id, kind: "choice", text: `**${b.question}**${b.subtitle ? `\n\n${b.subtitle}` : ""}`, options: (b.options ?? []).map((o) => ({ id: o.id, letter: o.letter, label: o.label })) };
    if (!m.runId || b.kind !== "ask" || !pendingAsk(b)) continue;
    if (b.input === "secret") {
      const login = b.credential?.auth?.type === "login";
      const site = hostOf(b.credential?.origin ?? b.oneTimeCode?.origin);
      const supported = login || b.oneTimeCode || !b.credential || b.credential?.auth?.type === "api_key";
      return {
        runId: m.runId, messageId: m.id, kind: "secret", options: [],
        text: `**${b.text}**${site ? `\n\nSite : ${site}` : ""}${b.detail ? `\n\n${b.detail}` : ""}`,
        secret: {
          login,
          otp: Boolean(b.oneTimeCode),
          supported: Boolean(supported),
          fields: login ? (b.loginFields?.length ? b.loginFields : ["Username", "Password"]) : [b.oneTimeCode ? "Code" : b.purpose === "api_key" ? "API key" : "Secret"],
        },
      };
    }
    const tool = /^Review before/i.test(b.text ?? "") || Boolean(b.approvalEffectId);
    const detail = b.detail ? `\n\n${b.detailFormat === "code" || tool ? "```\n" + String(b.detail).slice(0, 1500) + "\n```" : b.detail}` : "";
    return {
      runId: m.runId, messageId: m.id, kind: tool ? "permission" : "question", text: `**${tool ? reviewed(b.text) : b.text}**${detail}`,
      options: (b.actions ?? []).map((a) => ({ id: a.id, label: a.label })),
    };
  }
  return null;
}

async function bridge(spaceId, botId) {
  mkdirSync(CHATS, { recursive: true });
  const file = chatFile(botId);
  const chat = { botId, spaceId, bot: { name: "Rakazo", description: "" }, state: "idle", pending: null, streaming: null, messages: [], error: null };
  let cursor = -1;
  let writeTimer = null;
  let osc = "";

  const flush = () => {
    writeTimer = null;
    const tmp = `${file}.tmp`;
    writeFileSync(tmp, JSON.stringify({ ...chat, at: Date.now() }));
    renameSync(tmp, file);
  };
  const save = (now = false) => {
    if (now) {
      clearTimeout(writeTimer);
      return flush();
    }
    if (!writeTimer) writeTimer = setTimeout(flush, 80);
  };

  const report = (next, extra = {}) => {
    chat.state = next;
    const fields = [`state=${next}`, `app=${appOf(botId)}`, `title=${b64(chat.bot.name)}`];
    if (extra.kind) fields.push(`kind=${extra.kind}`);
    if (extra.msg) fields.push(`msg=${b64(extra.msg.replace(/\s+/g, " ").slice(0, 300))}`);
    const line = `\x1b]7501;${fields.join(":")}\x1b\\`;
    if (line !== osc) out(line);
    osc = line;
    save();
  };

  const upsert = (m) => {
    if (!m?.id || m.id.startsWith("progress:") || m.id.startsWith("subagent:")) return;
    const { md, chips, bots } = partsOf(m.blocks);
    const entry = { id: m.id, role: m.role ?? "bot", md, chips, bots, author: m.author?.name ?? null, at: m.createdAt ?? new Date().toISOString() };
    const i = chat.messages.findIndex((x) => x.id === m.id);
    if (i >= 0) chat.messages[i] = { ...chat.messages[i], ...entry, at: chat.messages[i].at };
    else if (md || chips.length || bots.length) chat.messages.push(entry);
    if (chat.messages.length > HISTORY) chat.messages = chat.messages.slice(-HISTORY);
    const pending = askOf(m);
    if (pending) chat.pending = pending;
    else if (chat.pending?.messageId === m.id) chat.pending = null;
    save();
  };

  const oscKind = () => (chat.pending?.kind === "permission" ? "permission" : "question");
  const takeover = (runId) => {
    chat.pending = { kind: "takeover", runId, text: "**The bot is handing you its screen.**\n\nOpen the screen in Rakazo, do what it asks, then tell it here when you are done." };
    report("blocked", { kind: "question", msg: "Screen handoff requested" });
  };
  const fromRun = (run) => {
    const s = run?.status;
    if (s === "queued" || s === "leased" || s === "running") report("working");
    else if (s === "waiting_input") report("blocked", { kind: oscKind(), msg: chat.pending?.text });
    else if (s === "waiting_takeover") takeover(run.id);
    else report("idle");
  };
  const refreshUnread = async () => {
    try {
      const bot = await rpc("bots/get", { botId }, { spaceId });
      chat.unread = Boolean(bot.unread);
      if (chat.state === "done" && !chat.unread) report("idle");
      else save();
    } catch {}
  };
  setInterval(refreshUnread, 60000);
  const readMark = `${file}.read`;
  writeFileSync(readMark, "");
  watchFile(readMark, { interval: 500 }, () => refreshUnread());

  const load = async () => {
    const bot = await rpc("bots/get", { botId }, { spaceId });
    chat.bot = { name: bot.name, description: bot.description ?? "", bubble: await bubbleOf(bot) };
    chat.unread = Boolean(bot.unread);
    out(`\x1b]2;${bot.name}\x07\x1b[2J\x1b[HRakazo bridge for ${bot.name}.\nThe chat is in the pane next to this one.\n`);
    const snap = await rpc("threads/get", { botId }, { spaceId });
    cursor = snap.cursor;
    chat.messages = [];
    chat.pending = null;
    chat.streaming = null;
    chat.error = null;
    for (const m of snap.messages) upsert(m);
    if (snap.run?.status !== "waiting_input" && chat.pending?.kind !== "choice") chat.pending = null;
    fromRun(snap.run);
    if (snap.run?.status !== "queued" && snap.run?.status !== "running" && snap.run?.status !== "leased" && chat.state === "idle" && chat.unread) report("done");
    save(true);
  };

  const onEvent = (ev) => {
    if (typeof ev.seq === "number" && ev.seq > cursor) cursor = ev.seq;
    const p = ev.payload ?? {};
    switch (ev.type) {
      case "thread.progress":
        if (p.reset === true) chat.streaming = null;
        else if (typeof p.delta === "string") chat.streaming = (chat.streaming ?? "") + p.delta;
        else if (typeof p.text === "string") chat.streaming = p.text;
        if (chat.state !== "working") report("working");
        else save();
        return;
      case "thread.message.created":
      case "thread.message.updated":
        if ((p.role ?? "bot") === "bot") chat.streaming = null;
        upsert({ id: String(p.messageId ?? ev.id), role: p.role ?? "bot", blocks: p.blocks ?? [], runId: ev.runId, createdAt: ev.createdAt, author: p.author });
        return;
      case "thread.cleared":
        chat.messages = [];
        save();
        return;
      case "run.started":
        chat.error = null;
        report("working");
        return;
      case "run.waiting_input":
        report("blocked", { kind: oscKind(), msg: chat.pending?.text ?? "The bot is waiting for you" });
        return;
      case "computer.takeover.requested":
        takeover(ev.runId ?? p.runId);
        return;
      case "run.completed":
        chat.pending = null;
        chat.streaming = null;
        chat.unread = true;
        report("done");
        return;
      case "computer.takeover.released":
        if (chat.pending?.kind === "takeover") chat.pending = null;
        report("working");
        return;
      case "run.failed":
        chat.pending = null;
        chat.streaming = null;
        chat.error = String(p.error ?? p.message ?? "The bot hit an error.");
        report("error", { msg: chat.error });
        return;
      case "run.cancelled":
        chat.pending = null;
        chat.streaming = null;
        report("idle");
        return;
      case "bot.updated":
        if (typeof p.name === "string") chat.bot.name = p.name;
        save();
        return;
      default:
    }
  };

  const authLost = async (e) => {
    chat.error = `${e.message} Sign in again: + then "Rakazo: sign in".`;
    report("blocked", { kind: "auth", msg: "Sign in to Rakazo again" });
    await sleep(60000);
  };

  for (;;) {
    try {
      await load();
      break;
    } catch (e) {
      if (e instanceof AuthError) await authLost(e);
      else {
        chat.error = e.message;
        report("error", { msg: e.message });
        await sleep(30000);
      }
    }
  }

  let wait = 1000;
  for (;;) {
    const controller = new AbortController();
    let silence;
    const arm = () => {
      clearTimeout(silence);
      silence = setTimeout(() => controller.abort(), 90000);
    };
    try {
      arm();
      for await (const ev of subscribe("threads/subscribe", { botId, cursor }, { spaceId, signal: controller.signal })) {
        arm();
        wait = 1000;
        if (ev.type !== "heartbeat") onEvent(ev);
      }
    } catch (e) {
      if (e instanceof AuthError) {
        await authLost(e);
        continue;
      }
    } finally {
      clearTimeout(silence);
    }
    await sleep(wait);
    wait = Math.min(wait * 2, 30000);
  }
}

function readChat(botId) {
  try {
    return JSON.parse(readFileSync(chatFile(botId), "utf8"));
  } catch {
    return null;
  }
}

async function send(spaceId, botId, text) {
  const chat = readChat(botId);
  const pending = chat?.pending;
  if (pending?.kind === "question" && !(pending.options?.length)) {
    await rpc("threads/answer", { botId, runId: pending.runId, messageId: pending.messageId, answer: text, clientNonce: randomUUID() }, { spaceId });
    return;
  }
  await rpc("threads/send", { botId, text, clientNonce: randomUUID() }, { spaceId });
}

async function answer(spaceId, botId, value) {
  const pending = readChat(botId)?.pending;
  if (!pending) throw new Error("No pending question.");
  await rpc("threads/answer", { botId, runId: pending.runId, messageId: pending.messageId, answer: value, clientNonce: randomUUID() }, { spaceId });
}

const [cmd, ...rest] = process.argv.slice(2);
try {
  if (cmd === "login") await login();
  else if (cmd === "logout") await logout();
  else if (cmd === "sync") {
    if (!existsSync(SESSION)) process.exit(0);
    const n = await sync();
    out(`${n} bot${n > 1 ? "s" : ""}\n`);
  } else if (cmd === "bridge") await bridge(rest[0], rest[1]);
  else if (cmd === "send") await send(rest[0], rest[1], rest.slice(2).join(" "));
  else if (cmd === "answer") await answer(rest[0], rest[1], rest.slice(2).join(" "));
  else if (cmd === "stop") await rpc("threads/stop", { botId: rest[1] }, { spaceId: rest[0] });
  else if (cmd === "bots") {
    const { bots } = await allBots();
    for (const b of bots) out(`${b.id}  ${b.status.padEnd(16)} ${b.name}\n`);
  } else {
    out("usage : rakazo.mjs login | logout | sync | bots | bridge|send|answer|stop <spaceId> <botId> [texte]\n");
  }
} catch (e) {
  process.stderr.write(`${e.message}\n`);
  if (cmd === "login") await sleep(15000);
  process.exit(1);
}
