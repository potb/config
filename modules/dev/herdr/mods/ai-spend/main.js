import { View, div } from "gpui-kit";
import { v_flex, h_flex } from "gpui-base";
import { theme, run, exec, home } from "herdr";

const NODE = `${home()}/.local/share/fnm/aliases/default/bin/node`;
const SCRIPT = `${home()}/.config/herdr-app/tools/ai-spend.mjs`;
const POLL_MS = 5 * 60 * 1000;
const HEADER_H = 41;
const ROW_H = 46;
const BOTTOM_PAD = 10;

const usd = (v) => (v == null ? "?" : v > 0 && v < 0.01 ? "< $0.01" : `$${v < 10 ? v.toFixed(2) : Math.round(v)}`);
const span = (v) => usd(v ?? null);

export default class AiSpend extends View {
  init(_props, cx) {
    this.data = null;
    this.height = 0;
    this.poll(cx);
    cx.timer.every(POLL_MS, (cx) => this.poll(cx));
  }

  poll(cx) {
    cx.spawn(async (cx) => {
      try {
        const r = await exec(NODE, [SCRIPT], { timeout: 40000 });
        this.data = JSON.parse(r.stdout);
      } catch {
        this.data = { error: true, providers: [] };
      }
      cx.notify();
    });
  }

  resize(rows) {
    const px = HEADER_H + (rows ? rows * ROW_H + BOTTOM_PAD : 0);
    if (px === this.height) return;
    this.height = px;
    try { run("layout.resize", { id: "ai-spend", px }); } catch {}
  }

  row(t, p) {
    const detail = p.missing ? "key missing" : p.error ? p.error
      : `month ${span(p.month)}`;
    return v_flex().id(`sp-${p.id}`).h(ROW_H).mx(8).px(8).gap(3).justify_center()
      .child(h_flex().gap(6).items_baseline()
        .child(div().flex_1().text_size(13).text_color(p.missing ? t.muted : t.foreground).child(p.name))
        .when(!p.missing && !p.error, (el) => el.child(div().text_size(14).font_semibold().text_color(t.foreground).child(span(p.week)))))
      .child(div().text_size(11.5).truncate().text_color(p.error ? t.ansi3 : t.muted).child(detail));
  }

  render() {
    const t = theme();
    const d = this.data;
    const list = d?.providers ?? [];
    this.resize(list.length);
    const month = list.filter((p) => p.month != null).reduce((a, p) => a + p.month, 0);
    const known = list.some((p) => p.month != null);
    return v_flex().w_full().size_full().bg(t.chrome).border_t(1).border_color(t.border)
      .child(h_flex().id("spend-header").px(16).h(HEADER_H).pt(14).pb(5).flex_none().gap(8).items_center()
        .child(div().flex_1().text_size(12).font_medium().text_color(t.muted).child("AI spend"))
        .child(div().text_size(12).text_color(t.muted).child(!d ? "Loading" : d.error ? "Unavailable" : known ? `this month ${usd(month)}` : "")))
      .children(list.map((p) => this.row(t, p)));
  }
}
