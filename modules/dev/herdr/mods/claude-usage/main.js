import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { theme, run, exec } from "herdr";

const SCRIPT = "/home/potb/.config/herdr-app/tools/scan-usage.py";
const POLL_MS = 5 * 60 * 1000;
const HEADER_H = 41;
const ROW_H = 46;
const NOTE_H = 26;
const BOTTOM_PAD = 10;

const until = (iso) => {
  const ms = Date.parse(iso) - Date.now();
  if (!(ms > 0)) return "now";
  const h = ms / 3600000;
  return h >= 24 ? `${Math.floor(h / 24)}d ${Math.floor(h % 24)}h` : h >= 1 ? `${Math.floor(h)}h ${Math.floor((ms / 60000) % 60)}m` : `${Math.max(1, Math.round(ms / 60000))}m`;
};

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const mix = (a, b, w) => `#${rgb(a).map((v, i) => Math.round(v * (1 - w) + rgb(b)[i] * w).toString(16).padStart(2, "0")).join("")}`;

const elapsed = (l) => {
  const end = Date.parse(l.resetsAt);
  if (!end || !l.windowH) return null;
  const span = l.windowH * 3600000;
  return Math.min(100, Math.max(0, 100 * (1 - (end - Date.now()) / span)));
};

export default class ClaudeUsage extends View {
  init(_props, cx) {
    this.data = null;
    this.height = 0;
    this.poll(cx);
    cx.timer.every(POLL_MS, (cx) => this.poll(cx));
    cx.timer.every(60000, (cx) => cx.notify());
  }

  poll(cx) {
    cx.spawn(async (cx) => {
      try {
        const r = await exec("python3", ["-I", SCRIPT], { timeout: 30000 });
        this.data = JSON.parse(r.stdout);
      } catch {
        this.data = { error: "scan failed" };
      }
      cx.notify();
    });
  }

  resize(rows, note) {
    const body = rows * ROW_H + (note ? NOTE_H : 0);
    const px = HEADER_H + (body ? body + BOTTOM_PAD : 0);
    if (px === this.height) return;
    this.height = px;
    try { run("layout.resize", { id: "claude-usage", px }); } catch {}
  }

  color(t, l) {
    if (l.percent >= 90) return t.blocked;
    if (l.percent >= 80) return t.ansi3;
    const pace = elapsed(l);
    if (pace != null && l.percent > pace + 10) return t.ansi3;
    return t.done;
  }

  row(t, l) {
    const pct = Math.round(l.percent);
    const fill = Math.min(100, Math.max(0, pct));
    const c = this.color(t, l);
    return v_flex().id(`u-${l.label}`).h(ROW_H).mx(8).px(8).gap(6).justify_center()
      .child(h_flex().gap(6).items_baseline().text_size(13)
        .child(div().text_color(t.foreground).child(l.label))
        .child(div().flex_1().text_size(12).text_color(t.muted).child(`resets in ${until(l.resetsAt)}`))
        .child(div().pl(12).text_size(14).font_semibold().text_color(mix(c, t.foreground, 0.5)).child(`${pct}%`)))
      .child(h_flex().w_full().h(6).rounded(3).bg(t.hover)
        .child(div().w(`${fill}%`).h(6).rounded(3).bg(c)));
  }

  render(cx) {
    const t = theme();
    const d = this.data;
    const limits = (d?.limits ?? []).filter((l) => l.active !== false || l.percent > 0);
    const error = d?.error;
    this.resize(limits.length, Boolean(error));
    const summary = !d ? { text: "Loading", color: t.muted }
      : error ? { text: "Unavailable", color: t.ansi3 }
      : d.staleError ? { text: `as of ${until(new Date(2 * Date.now() - d.ts).toISOString())} ago`, color: t.muted }
      : { text: "", color: t.muted };
    return v_flex().w_full().size_full().bg(t.chrome).border_t(1).border_color(t.border)
      .child(h_flex().id("usage-header").px(16).h(HEADER_H).pt(14).pb(5).flex_none().gap(8).items_center()
        .child(div().flex_1().text_size(12).font_medium().text_color(t.muted).child("Claude usage"))
        .child(div().text_size(12).text_color(summary.color).child(summary.text)))
      .when(Boolean(error), (e) => e.child(div().h(NOTE_H).px(16).flex().items_center().text_size(12).text_color(t.muted).child(error)))
      .children(limits.map((l) => this.row(t, l)));
  }
}
