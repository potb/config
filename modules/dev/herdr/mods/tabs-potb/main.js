import { View, div, svg, image } from "gpui-kit";
import { h_flex } from "gpui-base";
import { spaces, panes, run, exec, openOverlay, theme, window, layout, settings } from "herdr";

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) {
    const found = find(child, id);
    if (found) return found;
  }
  return null;
}

const clean = (s) => (s ?? "").replace(/^[^\p{L}\p{N}]+/u, "").trim();

const CHAR_W = 6.5;
const TAB_GAP = 3;
const MIN_TAB = 90;

function chromeWidth(c, program) {
  let w = 22;
  if (program?.icon) w += 21;
  if (c.status === "working") w += 19;
  if (c.status === "blocked" || c.status === "done") w += 13;
  if (c.active) w += 19;
  return w;
}

function fairCap(widths, avail) {
  const total = widths.reduce((a, b) => a + b, 0);
  if (total <= avail) return Infinity;
  let remaining = avail;
  let left = widths.length;
  for (const w of [...widths].sort((a, b) => a - b)) {
    if (w > remaining / left) break;
    remaining -= w;
    left -= 1;
  }
  return Math.max(MIN_TAB, remaining / Math.max(1, left));
}

const TITLES ="/home/potb/.config/herdr-app/tools/tab-titles.py";

function autoTitle(tab, lead, session) {
  const prog = lead?.program?.name;
  const live = clean(lead?.title);
  const telling = live && live !== prog && !/^[~/]|^[A-Za-z]:\\/.test(live) && !live.includes("@") && live.toLowerCase() !== lead?.program?.key;
  const unnamed = !tab.named || /^tb\d+$/.test(tab.name) || tab.name === prog;
  if (!unnamed) return tab.name;
  return session || (telling ? live : prog ?? "Terminal");
}

export default class Tabs extends View {
  init(_props, cx) {
    this.pressed = null;
    this.titles = {};
    this.poll(cx);
    cx.timer.every(10000, (cx) => this.poll(cx));
  }

  poll(cx) {
    cx.spawn(async (cx) => {
      try {
        const r = await exec("python3", ["-I", TITLES], { timeout: 10000 });
        const next = JSON.parse(r.stdout);
        if (JSON.stringify(next) === JSON.stringify(this.titles)) return;
        this.titles = next;
        cx.notify();
      } catch {}
    });
  }

  render() {
    const t = theme();
    const space = spaces().find(p => p.active);
    const shown = space?.tabs ?? [];
    const all = panes();
    const stop = (_e, cx) => cx.stop_propagation();
    const button = (id, label, action) => div().id(id).size(26).flex_none().flex().items_center().justify_center().rounded(6).text_color(t.dim).hover(s => s.bg(t.hover).text_color(t.foreground))
      .on_mouse_down("left", stop).on_click(action).child(label);
    const root = layout(), sidebar = find(root, "sidebar"), w = window();
    const lightsPadding = w?.platform === "macos" && w.titlebar === "none" && !w.fullscreen && root?.traffic_lights
      ? Math.max(10, (root.traffic_lights[0] + 64) / settings().zoom - (sidebar?.hidden ? 0 : sidebar?.size?.px ?? 0))
      : 10;
    const info = shown.map((c) => {
      const lead = all.find(p => p.tab === c.id && p.program?.agent) ?? all.find(p => p.tab === c.id && p.focused) ?? all.find(p => p.tab === c.id);
      const name = autoTitle(c, lead, lead?.terminal ? this.titles[lead.terminal] : null);
      const label = c.zoomed && !all.some(p => p.tab === c.id && p.mod) ? `${name} Z` : name;
      const chrome = chromeWidth(c, lead?.program);
      return { lead, label, chrome, want: chrome + Math.ceil(label.length * CHAR_W) + 4 };
    });
    const viewport = globalThis.window?.viewport_size?.()?.width ?? 0;
    const zoom = settings()?.zoom || 1;
    const avail = viewport / zoom - (sidebar?.hidden ? 0 : sidebar?.size?.px ?? 0) - 10 - lightsPadding - TAB_GAP - 26 - (w?.buttons ? 3 * 29 : 0) - TAB_GAP * Math.max(0, shown.length - 1);
    const cap = viewport > 0 ? fairCap(info.map((x) => x.want), avail) : Infinity;
    const item = (c, i) => {
      const { lead, label, chrome } = info[i];
      const program = lead?.program;
      return h_flex().id(`tab-${c.id}`).h(29).px(10).gap(7).rounded(7).items_center().flex_shrink_1().min_w(90).text_size(12.8)
        .border(1).border_color(c.active ? t.border : t.chrome).bg(c.active ? t.raised : t.chrome).text_color(c.active ? t.foreground : t.muted)
        .hover(s => s.bg(t.hover))
        .on_mouse_down("left", (e, cx) => { cx.stop_propagation(); this.pressed = i; if (e.click_count === 2) run("tab.rename", { id: c.id }); })
        .on_mouse_up("left", () => {
          const from = this.pressed; this.pressed = null;
          if (from !== null && from !== i) run("tab.move", { id: shown[from].id, index: space.tabs.findIndex(x => x.id === c.id) + 1 });
          else run("tab.select", { id: c.id });
        })
        .on_mouse_down("right", (_e, cx) => { cx.stop_propagation(); openOverlay({ mod: "menu-potb", kind: "popup", width: 200, props: { tab: "tab", target: { id: c.id, space: space.id } } }); })
        .when(Boolean(program?.icon), el => el.child(program.tint ? svg(program.icon).size(14).text_color(t.muted) : image(program.icon).size(14)))
        .child(div().min_w(0).when(cap !== Infinity, el => el.max_w(Math.max(24, cap - chrome))).truncate().child(label))
        .when(c.status === "working", el => el.child(svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900)))
        .when(c.status === "blocked" || c.status === "done", el => el.child(div().size(6).rounded(3).bg(t[c.status])))
        .when(c.active, el => el.child(div().id(`close-${c.id}`).text_color(t.dim).on_mouse_down("left", stop).on_click((_e, cx) => { cx.stop_propagation(); run("tab.close", { id: c.id }); }).child(svg("mods/pane-potb/close.svg").size(12))));
    };
    return h_flex().size_full().min_w(0).px(10).pl(lightsPadding).gap(3).items_center().bg(t.chrome).border_b(1).border_color(t.border)
      .on_mouse_up("left", () => { this.pressed = null; })
      .on_scroll_wheel(e => { if (Math.abs(e.delta.y) >= 1) run(e.delta.y > 0 ? "tab.prev" : "tab.next"); })
      .child(h_flex().id("tab-scroll").flex_1().min_w(0).h_full().items_center().gap(3).overflow_hidden().children(shown.map(item)))
      .child(button("tab-new", "+", () => openOverlay({ mod: "new-menu-potb", kind: "popup", width: 250, height: 200 })))
      .when(w?.buttons, el => el.child(button("minimize", w.platform === "windows" ? svg("mods/tabs-potb/win-min.svg").size(16) : "−", () => run("window.minimize")))
        .child(button("maximize", w.platform === "windows" ? svg(`mods/tabs-potb/${w.maximized ? "win-restore" : "win-max"}.svg`).size(16) : "□", () => run("window.maximize")))
        .child(button("close-window", w.platform === "windows" ? svg("mods/tabs-potb/win-close.svg").size(16) : svg("mods/pane-potb/close.svg").size(13), () => run("window.close"))));
  }
}
