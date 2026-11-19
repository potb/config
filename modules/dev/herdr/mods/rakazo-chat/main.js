import { View, div, image } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, TextView } from "gpui-base";
import { exec, home, readTextFile, writeTextFile, theme, props, panes } from "herdr";
import { prose } from "./prose.js";

const DATA = `${home()}/.config/herdr-app/data/rakazo`;
const SESSION = `${home()}/.local/share/rakazo/session.json`;
const BASE = "https://app.rakazo.com";
const POLL = 300;
const HIDDEN = /pass|mot de passe|code|pin|secret|clé|key/i;
const FR = { allow: "Allow once", always: "Always allow", deny: "Deny" };
const TITLES = { permission: "Approval needed", secret: "Login requested", takeover: "Screen handoff", choice: "Choice" };

const when = (iso) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (new Date().toDateString() === d.toDateString()) return hm;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[d.getMonth()]} ${d.getDate()}, ${hm}`;
};
const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const mention = (md, bot) => {
  const link = `[${bot.name}](${BASE}/app/${bot.id})`;
  const parts = md.split(/(`[^`]*`)/);
  const bold = new RegExp(`\\*\\*${escape(bot.name)}\\*\\*`);
  const bare = new RegExp(`(^|[^\\p{L}\\p{N}_\\[])${escape(bot.name)}(?![\\p{L}\\p{N}_])`, "u");
  for (const re of [bold, bare]) {
    const i = parts.findIndex((p, k) => k % 2 === 0 && re.test(p));
    if (i >= 0) {
      parts[i] = parts[i].replace(re, (m, pre) => (re === bold ? link : `${pre}${link}`));
      return parts.join("");
    }
  }
  return `${link} ${md}`;
};
const COLUMN = 760;
const GLIDE = { duration: 180, easing: "ease-out" };
const WHEEL_GAIN = 2;
const center = (el) => h_flex().w_full().flex_none().justify_center().child(el.flex_1().min_w(0).max_w(COLUMN));
const nonce = () => `herdr-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
const kind = (x) => (x && x.role !== "typing" && !x.md && x.chips?.length ? "chips" : x?.role);
const avatar = (botId, size) => image(`my-icons/rakazo-${botId}.svg`).size(size).flex_none().rounded_full();

class RakazoRow extends View {
  init(p) {
    this.p = p;
  }

  update(p) {
    this.p = p;
  }

  chips(t, m) {
    return v_flex().gap(4).items_center()
      .children((m.chips ?? []).map((c) => div().px(10).py(3).rounded(999).bg(t.raised).border_1().border_color(t.border)
        .text_size(11.5).text_color(t.dim).child(c)));
  }

  row(t) {
    const { m, grouped, bot, botId } = this.p;
    const top = grouped ? 4 : 18;
    if (kind(m) === "chips") return h_flex().pt(12).px(28).justify_center().child(this.chips(t, m));
    if (m.role === "typing")
      return h_flex().pt(top).px(28).gap(10).items_center()
        .child(avatar(botId, 26))
        .child(div().text_size(13).text_color(t.dim).italic().child(`${bot.name ?? "The bot"} is typing…`));
    if (m.role === "system")
      return h_flex().pt(14).px(28).justify_center()
        .child(div().text_size(12).text_color(t.dim).child(TextView.markdown(`rk-m-${m.id}`, m.md).selectable(true)));
    if (m.role === "user") {
      const b = bot.bubble;
      const on = b ? { ...t, foreground: b.foreground, accent: b.foreground, dim: b.foreground, hover: "#FFFFFF2E", border: "#FFFFFF40" } : t;
      return h_flex().pt(top).px(28).justify_end()
        .child(v_flex().max_w(560).px(14).py(9).rounded(14)
          .bg(b ? b.background : t.raised).border_1().border_color(b ? b.background : t.border)
          .opacity(m.sending ? 0.6 : 1)
          .text_size(14).line_height(1.5).text_color(on.foreground)
          .when(Boolean(m.md), (el) => el.child(prose(on, `rk-m-${m.id}`, m.md)))
          .when(Boolean(m.chips?.length), (el) => el.child(this.chips(t, m))));
    }
    return h_flex().pt(top).px(28).gap(10).items_start()
      .child(grouped ? div().w(26).flex_none() : avatar(botId, 26))
      .child(v_flex().flex_1().min_w(0).max_w(680).gap(3)
        .when(!grouped, (el) => el.child(h_flex().gap(8).items_baseline()
          .child(div().text_size(13).font_semibold().text_color(t.foreground).child(bot.name ?? "Bot"))
          .child(div().text_size(11).text_color(t.dim).child(m.live ? "" : when(m.at)))))
        .when(Boolean(m.md), (el) => el.child(h_flex().child(div().min_w(0).px(14).py(10).rounded(14).bg(t.raised)
          .text_size(14).line_height(1.55).text_color(m.live ? t.muted : t.foreground)
          .child(prose(t, `rk-m-${m.id}`, m.md)))))
        .when(Boolean(m.chips?.length), (el) => el.child(h_flex().pt(4).child(this.chips(t, m)))));
  }

  render() {
    return center(this.row(theme()));
  }
}

export default class RakazoChat extends View {
  init(_props, cx) {
    const p = props() ?? {};
    this.botId = p.botId;
    this.spaceId = p.spaceId;
    this.chat = null;
    this.raw = "";
    this.outbox = [];
    this.busy = false;
    this.notice = null;
    this.secret = null;
    this.visible = false;
    this.lift = 0;
    this.viewH = 0;
    this.contentH = 0;
    this.views = new Map();
    this.items = [];
    this.heights = new Map();
    this.viewW = 0;
    this.input = InputState.new({ placeholder: "Write a message" });
    this.input.on("submit", (_e, cx) => this.submit(cx));
    this.input.focus();
    this.handle = cx.focus_handle();
    this.poll(cx);
    cx.timer.every(POLL, (cx) => this.poll(cx));
  }

  async rpc(proc, input) {
    const session = JSON.parse((await readTextFile(SESSION)) ?? "{}");
    if (!session.token) throw new Error("Not signed in to Rakazo: use + then \"Rakazo: sign in\".");
    const res = await fetch(`${BASE}/rpc/${proc}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        origin: "rakazo://",
        authorization: `Bearer ${session.token}`,
        ...(this.spaceId ? { "x-rakazo-space-id": this.spaceId } : {}),
      },
      body: JSON.stringify({ json: input }),
    });
    let body = {};
    try {
      body = JSON.parse(await res.text());
    } catch {}
    if (res.status === 401) throw new Error("Rakazo session expired: sign in again from the + menu.");
    if (!res.ok) throw new Error(body?.json?.message || `Rakazo rejected the request (${res.status}).`);
    return body.json;
  }

  ourPane() {
    const all = panes();
    const bridge = all.find((q) => q.terminal && q.app === `rakazo-${this.botId}`.slice(0, 32));
    return bridge ? all.find((q) => q.mod && q.tab === bridge.tab) : null;
  }

  poll(cx) {
    if (this.polling || !this.botId) return;
    this.polling = true;
    const seen = Boolean(this.ourPane()?.focused);
    if (seen && !this.visible) this.input.focus();
    this.visible = seen;
    cx.spawn(async (cx) => {
      try {
        const text = await readTextFile(`${DATA}/${this.botId}.json`);
        if (text && text !== this.raw) {
          this.raw = text;
          this.chat = JSON.parse(text);
          const sent = new Set(this.chat.messages.filter((m) => m.role === "user").map((m) => m.md.trim()));
          this.outbox = this.outbox.filter((o) => !sent.has(o.md.trim()));
          if (this.secret && this.chat.pending?.messageId !== this.secret.id) this.dropSecret();
          this.sync(cx);
          cx.notify();
        }
        if (this.visible && this.chat?.unread && !this.marking) await this.markRead();
      } catch {}
      this.polling = false;
    });
  }

  async markRead() {
    this.marking = true;
    try {
      await this.rpc("threads/markRead", { botId: this.botId });
      const mark = `${DATA}/${this.botId}.json.read`;
      const current = await readTextFile(mark);
      await writeTextFile(mark, String(Date.now()), current);
    } catch {}
    this.marking = false;
  }

  act(cx, work, after) {
    this.busy = true;
    this.notice = null;
    cx.notify();
    cx.spawn(async (cx) => {
      let ok = true;
      try {
        await work();
      } catch (e) {
        ok = false;
        this.notice = String(e?.message ?? e);
      }
      this.busy = false;
      after?.(ok);
      this.sync(cx);
      cx.notify();
    });
  }

  answer(cx, value) {
    const p = this.chat?.pending;
    if (!p) return;
    this.act(cx, () => this.rpc("threads/answer", { botId: this.botId, runId: p.runId, messageId: p.messageId, answer: value, clientNonce: nonce() }));
  }

  submit(cx) {
    const text = this.input.value().trim();
    if (!text || !this.botId) return;
    this.input.set_value("");
    this.lift = 0;
    const p = this.chat?.pending;
    if (p && p.kind === "question" && this.chat?.state === "blocked") return this.answer(cx, text);
    const entry = { id: `out-${Date.now()}`, role: "user", md: text, at: new Date().toISOString(), sending: true };
    this.outbox.push(entry);
    this.sync(cx);
    this.act(cx, () => this.rpc("threads/send", { botId: this.botId, text, clientNonce: nonce() }), (ok) => {
      if (!ok) this.outbox = this.outbox.filter((o) => o !== entry);
    });
  }

  dropSecret() {
    for (const f of this.secret?.fields ?? []) {
      f.state.set_value("");
      f.state.release();
    }
    this.secret = null;
  }

  secretFor(p) {
    if (this.secret?.id === p.messageId) return this.secret;
    this.dropSecret();
    const labels = p.secret?.fields ?? ["Secret"];
    const fields = labels.map((label, i) => {
      const hidden = !p.secret?.login || HIDDEN.test(label) || (i === labels.length - 1 && !labels.some((l) => HIDDEN.test(l)));
      const state = InputState.new({ placeholder: label });
      if (hidden) state.set_masked(true);
      return { label, hidden, state };
    });
    this.secret = { id: p.messageId, fields, remember: true };
    return this.secret;
  }

  sendSecret(cx, p) {
    const s = this.secret;
    if (!s) return;
    const values = s.fields.map((f) => ({ label: f.label, hidden: f.hidden, value: f.state.value() }));
    for (const f of s.fields) f.state.set_value("");
    if (values.some((v) => !v.value.trim())) {
      this.notice = "Fill in every field.";
      return cx.notify();
    }
    const base = { botId: this.botId, runId: p.runId, messageId: p.messageId };
    const input = p.secret?.login
      ? { ...base, answer: "", fields: values, ...(s.remember ? {} : { remember: false }) }
      : { ...base, answer: p.secret?.otp ? values[0].value.replace(/\s+/g, "") : values[0].value };
    values.length = 0;
    this.act(cx, () => this.rpc("threads/answer", input));
  }

  measured() {
    return this.viewH > 0 && this.contentH > 0;
  }

  maxLift() {
    return Math.max(0, this.contentH - this.viewH);
  }

  setLift(cx, lift) {
    const next = Math.min(Math.max(0, lift), this.maxLift());
    if (next === this.lift) return;
    this.lift = next;
    cx.notify();
  }

  wheel(e, cx) {
    this.precise = !e.delta_lines;
    const dy = e.delta.y * (this.precise ? 1 : WHEEL_GAIN);
    if (dy) this.setLift(cx, this.lift + dy);
  }

  measureView(s, cx) {
    if (s.width !== this.viewW) {
      this.viewW = s.width;
      this.heights.clear();
      cx.notify();
    }
    if (s.height === this.viewH) return;
    this.viewH = s.height;
    this.setLift(cx, this.lift);
    cx.notify();
  }

  measureContent(h, cx) {
    if (h === this.contentH) return;
    const grown = this.lift > 0 && this.contentH ? h - this.contentH : 0;
    this.contentH = h;
    this.setLift(cx, this.lift + grown);
    cx.notify();
  }

  measureRow(id, h, cx) {
    if (this.heights.get(id) === h) return;
    this.heights.set(id, h);
    cx.notify();
  }

  windowed() {
    const margin = Math.max(800, this.viewH);
    const low = this.lift - margin;
    const high = this.lift + this.viewH + margin;
    const out = [];
    let gap = 0;
    let y = 14;
    for (let i = this.items.length - 1; i >= 0; i--) {
      const id = this.items[i];
      const h = this.heights.get(id);
      const hidden = this.viewH > 0 && h !== undefined && (y > high || y + h < low);
      y += h ?? 0;
      if (hidden) {
        gap += h;
        continue;
      }
      if (gap) out.push(div().flex_none().h(gap));
      gap = 0;
      out.push(div().id(`rk-r-${id}`).flex_none()
        .on_size_change((s, cx) => this.measureRow(id, s.height, cx))
        .child(this.views.get(id).entity));
    }
    if (gap) out.push(div().flex_none().h(gap));
    return out.reverse();
  }

  sync(cx) {
    const rows = this.rows();
    const bot = { name: this.chat?.bot?.name ?? null, bubble: this.chat?.bot?.bubble ?? null };
    const keep = new Set();
    this.items = rows.map((m, i) => {
      const prev = rows[i - 1];
      const p = { m, grouped: Boolean(prev && kind(prev) === kind(m) && m.role !== "system"), bot, botId: this.botId };
      const key = JSON.stringify(p);
      const v = this.views.get(m.id);
      if (!v) this.views.set(m.id, { entity: cx.new(RakazoRow, p), key });
      else if (v.key !== key) {
        v.entity.set_props(p);
        v.key = key;
      }
      keep.add(m.id);
      return m.id;
    });
    for (const [id, v] of this.views) {
      if (keep.has(id)) continue;
      v.entity.release();
      this.views.delete(id);
    }
  }

  thumb(t) {
    const max = this.maxLift();
    if (!max || !this.viewH) return null;
    const h = Math.max(32, (this.viewH * this.viewH) / this.contentH);
    const top = ((max - this.lift) / max) * (this.viewH - h);
    return div().id("rk-thumb").absolute().right(3).top(top).transition("top", GLIDE).w(4).h(h).rounded(2).bg(t.border);
  }

  rows() {
    const c = this.chat;
    const rows = [];
    let waiting = [];
    for (const m of c?.messages ?? []) {
      const announce = m.role === "bot" && m.bots?.length && !m.md && !m.chips?.length;
      if (announce) {
        waiting.push(...m.bots);
        continue;
      }
      if (waiting.length && m.role === "bot" && m.md) {
        rows.push({ ...m, md: waiting.reduce((md, b) => mention(md, b), m.md) });
        waiting = [];
        continue;
      }
      if (waiting.length && m.role !== "bot") {
        rows.push({ id: `bots-${m.id}`, role: "bot", md: "", chips: waiting.map((b) => `Created bot ${b.name}`) });
        waiting = [];
      }
      rows.push(m);
    }
    if (waiting.length) rows.push({ id: "bots-tail", role: "bot", md: "", chips: waiting.map((b) => `Created bot ${b.name}`) });
    rows.push(...this.outbox);
    if (c?.streaming) rows.push({ id: "streaming", role: "bot", md: c.streaming, live: true });
    else if (c?.state === "working") rows.push({ id: "typing", role: "typing" });
    return rows;
  }

  avatar(size) {
    return avatar(this.botId, size);
  }

  button(t, id, label, primary, action) {
    return h_flex().id(id).h(30).px(12).items_center().rounded(8).border_1()
      .border_color(primary ? t.solid : t.input).bg(primary ? t.solid : t.raised)
      .text_color(primary ? t.solid_foreground : t.foreground).text_size(12.5).font_medium()
      .opacity(this.busy ? 0.5 : 1)
      .cursor_pointer().hover((s) => s.opacity(0.88)).on_click((_e, cx) => { if (!this.busy) action(cx); }).child(label);
  }

  openRakazo() {
    exec("xdg-open", [`${BASE}/app/${this.botId}`]).catch(() => {});
  }

  actions(t, p) {
    const row = (items) => h_flex().gap(8).flex_wrap().children(items.map(([label, primary, action], i) => this.button(t, `rk-a-${i}`, label, primary, action)));
    if (p.kind === "choice")
      return row(p.options.map((o, i) => [o.label, i === 0, (cx) => this.act(cx, () => this.rpc("onboarding/choose", { botId: this.botId, optionId: o.id }))]));
    if (p.kind === "takeover")
      return row([
        ["Open screen in Rakazo", true, () => this.openRakazo()],
        ["Done", false, (cx) => this.act(cx, () => this.rpc("computer/release", { botId: this.botId, runId: p.runId, reason: "done" }))],
        ["Skip", false, (cx) => this.act(cx, () => this.rpc("computer/release", { botId: this.botId, runId: p.runId, reason: "skipped" }))],
      ]);
    if (p.kind === "secret") {
      if (!p.secret?.supported) return row([["Open in Rakazo", true, () => this.openRakazo()]]);
      const s = this.secretFor(p);
      return v_flex().gap(8)
        .children(s.fields.map((f) => v_flex().gap(4)
          .child(div().text_size(11.5).text_color(t.dim).child(f.label))
          .child(h_flex().px(10).py(4).rounded(8).border_1().border_color(t.input).bg(t.background)
            .child(Input.new(f.state).flex_1().h(28).text_size(13.5).text_color(t.foreground)))))
        .child(row([
          ["Send", true, (cx) => this.sendSecret(cx, p)],
          ...(p.secret?.login ? [[s.remember ? "Save to vault" : "This run only", false, (cx) => { s.remember = !s.remember; cx.notify(); }]] : []),
          ["Decline", false, (cx) => { this.dropSecret(); this.act(cx, () => this.rpc("threads/answer", { botId: this.botId, runId: p.runId, messageId: p.messageId, answer: "", dismiss: true })); }],
        ]))
        .child(div().text_size(11).text_color(t.dim).child("Sent encrypted to Rakazo. The bot never sees the value, and herdr does not keep it."));
    }
    const options = p.options?.length ? p.options : p.kind === "permission" ? [{ id: "allow" }, { id: "always" }, { id: "deny" }] : [];
    if (!options.length) return div().text_size(12).text_color(t.dim).child("Reply in the field below.");
    return row(options.map((o, i) => [FR[o.id] ?? o.label ?? o.id, i === 0, (cx) => this.answer(cx, o.id)]));
  }

  asking(t) {
    const p = this.chat?.pending;
    if (!p) return null;
    const last = this.chat.messages.at(-1)?.id;
    if (p.kind === "choice" ? p.messageId !== last : this.chat.state !== "blocked") return null;
    return v_flex().mx(28).mt(12).p(14).gap(10).rounded(12).border_1().border_color(t.accent).bg(t.popover)
      .child(div().text_size(12).font_semibold().text_color(t.accent).child(TITLES[p.kind] ?? "Question"))
      .when(Boolean(p.text), (el) => el.child(div().text_size(14).line_height(1.5).text_color(t.foreground).child(TextView.markdown("rk-ask", p.text))))
      .child(this.actions(t, p));
  }

  composer(t) {
    const working = this.chat?.state === "working";
    return v_flex().flex_none().px(20).pt(10).pb(16).gap(6)
      .when(Boolean(this.notice || this.chat?.error), (el) => el.child(div().px(4).text_size(12).text_color(t.blocked)
        .child(this.notice ?? this.chat.error)))
      .child(h_flex().gap(8).items_center().pl(14).pr(6).py(6).rounded(12).border_1().border_color(t.input).bg(t.raised)
        .child(Input.new(this.input).flex_1().h(30).text_size(14).text_color(t.foreground))
        .child(working
          ? this.button(t, "rk-stop", "Stop", false, (cx) => this.act(cx, () => this.rpc("threads/stop", { botId: this.botId })))
          : this.button(t, "rk-send", "Send", true, (cx) => this.submit(cx))));
  }

  render() {
    const t = theme();
    const body = !this.chat
      ? v_flex().flex_1().items_center().justify_center().text_size(13).text_color(t.dim).child("Connecting to Rakazo…")
      : !this.items.length
      ? v_flex().flex_1().items_center().justify_center().gap(10).px(40)
        .child(this.avatar(48))
        .child(div().text_size(15).font_semibold().child(this.chat.bot?.name ?? "Rakazo"))
        .child(div().max_w(420).text_size(13).text_color(t.dim).text_center()
          .child(String(this.chat.bot?.description || "No messages yet.").split("\n")[0]))
      : v_flex().id("rk-view").flex_1().min_h(0).relative().overflow_hidden()
        .on_size_change((s, cx) => this.measureView(s, cx))
        .on_scroll_wheel((e, cx) => this.wheel(e, cx))
        .child(v_flex().id("rk-msgs").absolute().left(0).right(0)
          .when(!this.measured(), (el) => el.bottom(0))
          .when(this.measured(), (el) => el.top(this.viewH - this.contentH + this.lift).when(!this.precise, (el) => el.transition("top", GLIDE)))
          .on_size_change((s, cx) => this.measureContent(s.height, cx))
          .children(this.windowed())
          .child(div().h(14).flex_none()))
        .when(Boolean(this.thumb(t)), (el) => el.child(this.thumb(t)));
    const card = this.asking(t);
    return v_flex().id("rakazo-chat").track_focus(this.handle).size_full().bg(t.background).text_color(t.foreground)
      .child(body)
      .when(Boolean(card), (el) => el.child(center(card)))
      .child(center(this.composer(t)));
  }
}
