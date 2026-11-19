import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { readTextFile, theme, run, exec, notify } from "herdr";

const DIR = "/home/potb/.config/herdr-app/data/ship-core/";
const TOOLS = "/home/potb/.config/herdr-app/tools/";
const SHIP_EVERY = 90000, LINEAR_EVERY = 180000, SLACK = 8000, SCAN_TIMEOUT = 60000;
const HEADER_H = 41;
const BORDER = 1;
const LABEL_H = 30;
const LINE_H = 18;
const CHARS_PER_LINE = 64;
const MAX_LINES = 3;
const MORE_H = 28;
const NOTE_H = 26;
const BOTTOM_PAD = 10;
const CI_STUCK_MIN = 20;
const STALE_MIN = 10;
const REASON = { conflict: "conflict", red: "CI red", "cancelled-required": "cancelled", "pending-long": "CI pending", "draft-forgotten": "old draft", "ready-unmerged": "unmerged", "stack-waiting": "stack" };
const PLURAL = { conflict: "conflicts", red: "CI red", "pending-long": "CI pending" };

async function load(name) {
  try {
    const text = await readTextFile(DIR + name);
    return text ? JSON.parse(text) : null;
  } catch { return null; }
}

const openUrl = (url) => { if (url) exec("xdg-open", [url]).catch(() => {}); };
const age = (h) => (h >= 48 ? `${Math.round(h / 24)}d` : h >= 1 ? `${Math.round(h)}h` : `${Math.max(1, Math.round(h * 60))}m`);
const shortTitle = (s) => String(s ?? "").replace(/^[a-z]+(\([^)]*\))?!?:\s*/i, "");
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const mix = (a, b, w) => `#${rgb(a).map((v, i) => Math.round(v * (1 - w) + rgb(b)[i] * w).toString(16).padStart(2, "0")).join("")}`;
const ink = (t, color) => mix(color, t.foreground, 0.45);
const tint = (color) => `${color}33`;

function wrapTitle(s) {
  const words = String(s ?? "").split(/\s+/).filter(Boolean);
  const lines = [""];
  for (const w of words) {
    const cur = lines[lines.length - 1];
    if (!cur) lines[lines.length - 1] = w;
    else if (cur.length + 1 + w.length <= CHARS_PER_LINE) lines[lines.length - 1] = `${cur} ${w}`;
    else lines.push(w);
  }
  if (lines.length <= MAX_LINES) return { text: lines.join(" "), lines: lines.length };
  const kept = lines.slice(0, MAX_LINES);
  const last = kept[MAX_LINES - 1].split(" ");
  while (last.length > 1 && last.join(" ").length + 3 > CHARS_PER_LINE) last.pop();
  kept[MAX_LINES - 1] = `${last.join(" ").replace(/[,;:]$/, "")}...`;
  return { text: kept.join(" "), lines: MAX_LINES };
}

export default class ShipSide extends View {
  init(_props, cx) {
    this.prs = null;
    this.linear = null;
    this.loaded = false;
    this.height = 0;
    this.expanded = new Set();
    this.load(cx);
    cx.timer.every(15000, (cx) => this.load(cx));
    this.scanning = false;
    this.scanned = { ship: 0, linear: 0 };
    this.scan(cx);
    cx.timer.every(2000, (cx) => this.scan(cx));
  }

  scan(cx) {
    const now = Date.now();
    if (this.scanning || now - this.scanned.ship < SHIP_EVERY - SLACK) return;
    const linear = now - this.scanned.linear >= LINEAR_EVERY - SLACK;
    this.scanning = true;
    cx.spawn(async (cx) => {
      try {
        const r = await exec("python3", ["-I", `${TOOLS}scan-ship.py`, ...(linear ? ["--linear"] : [])], { timeout: SCAN_TIMEOUT });
        const data = r.code === 0 ? JSON.parse(r.stdout) : null;
        if (data?.ok) for (const ev of data.events ?? []) notify({ title: ev.title, body: ev.body, level: "warning" });
      } catch {}
      this.scanned.ship = Date.now();
      if (linear) this.scanned.linear = this.scanned.ship;
      this.scanning = false;
      this.load(cx);
    });
  }

  load(cx) {
    cx.spawn(async (cx) => {
      this.prs = await load("prs.json");
      this.linear = await load("linear.json");
      this.loaded = true;
      this.resize();
      cx.notify();
    });
  }

  sections(t) {
    const projects = this.linear?.projects ?? [];
    const all = (key) => projects.flatMap((p) => p[key] ?? []);
    const mine = this.prs?.prs ?? [];
    const prOf = new Map(mine.filter((p) => p.ticket).map((p) => [p.ticket, p]));
    const blocks = new Map(all("rootBlockers").map((b) => [b.issue.identifier, b.blocksTransitively]));
    const issues = new Map();
    for (const i of [...all("rootBlockers").map((b) => b.issue), ...all("noPr"), ...all("startable"), ...all("stale")]) issues.set(i.identifier, i);
    const seen = new Set();

    const item = (ident, issue, pr) => {
      if (ident) seen.add(ident);
      const ci = pr?.ciRunningMin;
      return {
        key: pr ? `pr-${pr.number}` : ident,
        title: issue?.title ?? pr?.ticketTitle ?? shortTitle(pr?.title),
        wrap: wrapTitle(issue?.title ?? pr?.ticketTitle ?? shortTitle(pr?.title)),
        ref: [ident, pr && `#${pr.number}`].filter(Boolean).join("  "),
        reason: pr?.reason ?? null, draft: Boolean(pr?.isDraft), blocks: blocks.get(ident) ?? 0, age: pr?.ageH ?? 0,
        meta: ci != null ? { text: `CI ${age(ci / 60)}`, color: ci >= CI_STUCK_MIN ? t.blocked : t.working }
          : pr?.idleH != null ? { text: `idle ${age(pr.idleH)}`, color: t.muted } : null,
        url: pr ? (pr.linearUrl ?? pr.url) : issue?.url,
      };
    };
    const byImpact = (a, b) => b.blocks - a.blocks || b.age - a.age;

    const stuck = mine.filter((p) => p.reason).map((p) => item(p.ticket, issues.get(p.ticket), p)).sort(byImpact);
    const blockers = all("rootBlockers").map((b) => b.issue)
      .filter((i) => !seen.has(i.identifier) && prOf.has(i.identifier))
      .map((i) => item(i.identifier, i, prOf.get(i.identifier))).sort(byImpact);
    const flight = mine.filter((p) => !p.reason && !(p.ticket && seen.has(p.ticket)))
      .map((p) => item(p.ticket, issues.get(p.ticket), p)).sort((a, b) => a.age - b.age);
    const reasons = new Set(stuck.map((i) => i.reason));
    const shared = reasons.size === 1 && stuck.length > 1 ? [...reasons][0] : null;
    return [
      { id: "prs", label: shared ? `Needs you, ${PLURAL[shared] ?? REASON[shared] ?? shared}` : "Needs you", color: t.blocked, max: 5, board: "prs", items: stuck, hideReason: shared },
      { id: "blockers", label: "Blocking others", color: t.ansi3, max: 3, board: "linear", items: blockers, hideReason: null },
      { id: "flight", label: "In flight", color: t.muted, max: 5, board: "prs", items: flight, hideReason: null },
    ].filter((s) => s.items.length > 0);
  }

  state() {
    if (!this.loaded) return "loading";
    if (!this.prs) return "error";
    const mins = this.prs.ts ? (Date.now() - this.prs.ts) / 60000 : 0;
    return mins > STALE_MIN ? "stale" : "ok";
  }

  measure(h) {
    this.contentH = Math.ceil(h);
    this.resize();
  }

  resize() {
    const st = this.state();
    const px = BORDER + HEADER_H + (st === "error" ? NOTE_H : 0) + (this.contentH ?? 0);
    if (px === this.height) return;
    this.height = px;
    try { run("layout.resize", { id: "ship-side", px }); } catch {}
  }

  chip(t, text, color, strong) {
    const c = div().flex_none().px(6).h(18).flex().items_center().rounded(5).text_size(11).bg(tint(color)).text_color(ink(t, color)).child(text);
    return strong ? c.font_semibold() : c;
  }

  shown(s) {
    return this.expanded.has(s.id) ? s.items.length : Math.min(s.items.length, s.max);
  }

  toggle(s, cx) {
    if (this.expanded.has(s.id)) this.expanded.delete(s.id);
    else this.expanded.add(s.id);
    this.resize();
    cx.notify();
  }

  sectionHeader(t, s) {
    const overflow = s.items.length > s.max;
    const open = this.expanded.has(s.id);
    const hidden = open ? 0 : s.items.slice(s.max).reduce((n, i) => n + i.blocks, 0);
    return h_flex().id(`sec-${s.id}`).h(LABEL_H).pt(8).mx(8).px(8).gap(6).items_center().text_size(12).font_medium()
      .when(overflow, (e) => e.cursor_pointer().on_click((_e, cx) => this.toggle(s, cx)))
      .child(div().truncate().text_color(s.color).child(s.label))
      .child(div().text_color(t.muted).child(String(s.items.length)))
      .child(div().flex_1())
      .when(hidden > 0, (e) => e.child(div().text_color(t.muted).child(`blocks ${hidden} more`)))
      .when(overflow, (e) => e.child(svg(`mods/workspace-chrome/chevron-${open ? "down" : "right"}.svg`).size(11).flex_none().text_color(t.dim)));
  }

  row(t, s, it) {
    const showReason = it.reason && it.reason !== s.hideReason;
    return h_flex().id(it.key).py(7).mx(8).px(8).gap(8).items_center().rounded(8).cursor_pointer()
      .on_click(() => openUrl(it.url))
      .child(v_flex().flex_1().min_w(0).gap(3)
        .child(div().whitespace_normal().text_size(13).line_height(`${LINE_H}px`).text_color(t.foreground).child(it.wrap.text))
        .child(h_flex().gap(6).items_center().text_size(12)
          .child(div().flex_none().text_color(t.muted).child(it.ref))
          .child(div().flex_1())
          .when(it.blocks > 0, (e) => e.child(this.chip(t, `blocks ${it.blocks}`, t.ansi3, true)))
          .when(Boolean(showReason), (e) => e.child(this.chip(t, REASON[it.reason] ?? it.reason, t.blocked, false)))
          .when(!it.reason && it.draft, (e) => e.child(this.chip(t, "draft", t.muted, false)))
          .when(Boolean(it.meta), (e) => e.child(div().flex_none().text_color(it.meta.color).child(it.meta.text)))));
  }

  more(t, s) {
    return h_flex().id(`more-${s.id}`).h(MORE_H).mx(8).px(8).items_center().rounded(6).cursor_pointer()
      .on_click((_e, cx) => this.toggle(s, cx))
      .child(div().text_size(12).text_color(t.accent).child(this.expanded.has(s.id) ? "Show fewer" : `${s.items.length - s.max} more`));
  }

  note(t, id, text, color) {
    return div().id(id).h(NOTE_H).px(16).flex().items_center().text_size(12).text_color(color).child(text);
  }

  render(cx) {
    const t = theme();
    const st = this.state();
    if (this.loaded) this.resize();
    const secs = st === "error" ? [] : this.sections(t);
    const count = (id) => secs.find((s) => s.id === id)?.items.length ?? 0;
    const parts = [count("prs") && `${count("prs")} stuck`, count("blockers") && plural(count("blockers"), "blocker"), count("flight") && `${count("flight")} in flight`].filter(Boolean);
    const mins = this.prs?.ts ? (Date.now() - this.prs.ts) / 60000 : null;
    const summary = st === "loading" ? { text: "Loading", color: t.muted }
      : st === "error" ? { text: "Scan failed", color: t.ansi3 }
      : st === "stale" ? { text: `stale ${age(mins / 60)}`, color: t.ansi3 }
      : parts.length ? { text: parts.join(", "), color: t.muted }
      : { text: "All clear", color: t.done };
    return v_flex().w_full().size_full().bg(t.chrome).border_t(BORDER).border_color(t.border)
      .child(h_flex().id("ship-header").px(16).h(HEADER_H).pt(14).pb(5).flex_none().gap(8).items_center()        .child(div().flex_1().text_size(12).font_medium().text_color(t.muted).child("Shipping"))
        .child(div().text_size(12).text_color(summary.color).child(summary.text)))
      .when(st === "error", (e) => e.child(this.note(t, "ship-error", "Shipping data could not be read", t.muted)))
      .child(v_flex().id("ship-body").flex_1().min_h(0)
        .on_size_change((size, cx) => { if (Math.ceil(size.height) !== this.viewH) { this.viewH = Math.ceil(size.height); cx.notify(); } })
        .map((e) => ((this.contentH ?? 0) > (this.viewH ?? Infinity) ? e.overflow_y_scrollbar() : e.overflow_y_scroll()))
        .when(st === "stale", (e) => e.opacity(0.55))
        .child(v_flex().id("ship-content").flex_none().w_full().on_size_change((size, _cx) => this.measure(size.height))
          .when(secs.length > 0 || (st !== "error" && st !== "loading" && !this.linear), (e) => e.pb(BOTTOM_PAD))
          .children(secs.map((s) => v_flex()
            .child(this.sectionHeader(t, s))
            .children(s.items.slice(0, this.shown(s)).map((it) => this.row(t, s, it)))
            .when(s.items.length > s.max, (e) => e.child(this.more(t, s)))))
          .when(st !== "error" && st !== "loading" && !this.linear, (e) => e.child(this.note(t, "lin-missing", "Linear data unavailable", t.ansi3)))));
  }
}
