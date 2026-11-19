import { div, image } from "gpui-kit";
import { v_flex, h_flex, TextView } from "gpui-base";
import { exec } from "herdr";

const MENTION = /^https:\/\/app\.rakazo\.com\/app\/([a-z0-9]+)$/;
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|(\[[^\]\n]+\]\([^)\s]+\))|(\*[^*\s][^*\n]*\*)|(https?:\/\/[^\s)]+)/g;
const GLUED = /^[:;!?»%)\].,]/;
const ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const CHUNK = 4;

function blocks(md) {
  const out = [];
  let buf = [];
  let fence = false;
  const flush = (kind) => {
    if (buf.length) out.push({ kind, text: buf.join("\n") });
    buf = [];
  };
  for (const line of md.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) {
      if (!fence) flush("prose");
      buf.push(line);
      fence = !fence;
      if (!fence) flush("raw");
      continue;
    }
    if (fence) {
      buf.push(line);
      continue;
    }
    if (!line.trim()) flush("prose");
    else buf.push(line);
  }
  flush(fence ? "raw" : "prose");
  return out.flatMap((b) => (b.kind === "prose" ? classify(b.text) : [b]));
}

function classify(text) {
  const lines = text.split("\n");
  if (lines.some((l) => /^\s*(#|>|\|)/.test(l) || /^\s*([-*_])\s*\1\s*\1\s*$/.test(l) || /^\s+([-*+]|\d+[.)])\s/.test(l)))
    return [{ kind: "raw", text }];
  const out = [];
  for (const l of lines) {
    const m = l.match(ITEM);
    const cur = out[out.length - 1];
    if (m) {
      const item = { marker: /\d/.test(m[2]) ? m[2] : "•", text: m[3] };
      if (cur?.kind === "list") cur.items.push(item);
      else out.push({ kind: "list", items: [item] });
    } else if (cur?.kind === "list" && /^\s/.test(l)) cur.items[cur.items.length - 1].text += ` ${l.trim()}`;
    else if (cur?.kind === "para") cur.text += ` ${l.trim()}`;
    else out.push({ kind: "para", text: l.trim() });
  }
  return out;
}

function atoms(text) {
  const out = [];
  const words = (chunk, style) => {
    for (const part of chunk.split(/([ \t\n]+)/)) {
      if (!part) continue;
      if (/^[ \t\n]+$/.test(part)) {
        if (out.length) out[out.length - 1].space = true;
      } else out.push({ kind: "text", style, text: part, space: false });
    }
  };
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    words(text.slice(last, m.index), null);
    const [all, code, bold, link, italic, url] = m;
    if (code) out.push({ kind: "code", text: code.slice(1, -1), space: false });
    else if (bold) words(bold.slice(2, -2), "bold");
    else if (italic) words(italic.slice(1, -1), "italic");
    else if (link) {
      const [, label, href] = link.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const bot = href.match(MENTION)?.[1];
      out.push({ kind: bot ? "mention" : "link", text: label.replace(/\\(.)/g, "$1"), href, bot, space: false });
    } else if (url) out.push({ kind: "link", text: url, href: url, space: false });
    last = m.index + all.length;
  }
  words(text.slice(last), null);
  const runs = [];
  for (const a of out) {
    const prev = runs[runs.length - 1];
    if (prev && a.kind === "text" && prev.kind === "text" && prev.style === a.style && prev.space && prev.n < CHUNK) {
      prev.text += ` ${a.text}`;
      prev.space = a.space;
      prev.n += 1;
    } else runs.push({ ...a, n: 1 });
  }
  const groups = [];
  for (const a of runs) {
    const prev = groups[groups.length - 1];
    const before = prev?.[prev.length - 1];
    if (prev && (GLUED.test(a.text) || (before && !before.space) || before?.text === "«")) prev.push(a);
    else groups.push([a]);
  }
  return groups;
}

function atom(t, a, key) {
  const space = a.space ? 4 : 0;
  if (a.kind === "code")
    return div().mr(space).px(5).py(1).rounded(5).bg(t.hover).border_1().border_color(t.border)
      .font_family("JetBrains Mono").text_size(12.5).line_height(1.35).child(a.text);
  if (a.kind === "mention")
    return h_flex().id(key).mr(space).gap(4).items_center().cursor_pointer()
      .on_click(() => exec("xdg-open", [a.href]).catch(() => {}))
      .child(image(`my-icons/rakazo-${a.bot}.svg`).size(16).flex_none().rounded_full())
      .child(div().font_semibold().text_color(t.accent).child(a.text));
  if (a.kind === "link")
    return div().id(key).mr(space).text_color(t.accent).cursor_pointer().hover((s) => s.underline())
      .on_click(() => exec("xdg-open", [a.href]).catch(() => {})).child(a.text);
  const el = div().mr(space).child(a.text);
  if (a.style === "bold") return el.font_bold();
  if (a.style === "italic") return el.italic();
  return el;
}

function plain(groups) {
  const flat = groups.flat();
  const style = flat[0]?.style ?? null;
  return flat.every((a) => a.kind === "text" && a.style === style) ? style ?? "plain" : null;
}

function line(t, text, key) {
  const groups = atoms(text);
  const style = plain(groups);
  if (style) {
    const el = div().min_w(0).child(groups.flat().map((a) => a.text).join(" "));
    if (style === "bold") return el.font_bold();
    if (style === "italic") return el.italic();
    return el;
  }
  return h_flex().flex_wrap().items_center().min_w(0)
    .children(groups.map((g, i) => (g.length === 1
      ? atom(t, g[0], `${key}-${i}`)
      : h_flex().items_center().flex_none().children(g.map((a, j) => atom(t, a, `${key}-${i}-${j}`))))));
}

export function prose(t, id, md) {
  return v_flex().gap(10).min_w(0).children(blocks(md).map((b, i) => {
    const key = `${id}-${i}`;
    if (b.kind === "raw") return TextView.markdown(key, b.text).selectable(true);
    if (b.kind === "para") return line(t, b.text, key);
    return v_flex().gap(4).children(b.items.map((it, j) => h_flex().items_start().gap(8)
      .child(div().flex_none().w(14).text_color(t.dim).child(it.marker))
      .child(div().flex_1().min_w(0).child(line(t, it.text, `${key}-${j}`)))));
  }));
}
