// Мини-разбор markdown из разборов ИИ: секции "##", списки, **жирный**. Только текст, без HTML.

export interface MdInline {
  text: string;
  bold: boolean;
}
export interface MdSection {
  heading: string | null;
  blocks: ({ kind: 'p'; parts: MdInline[] } | { kind: 'ul'; items: MdInline[][] })[];
}

export function mdInline(s: string): MdInline[] {
  const out: MdInline[] = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push({ text: s.slice(last, m.index), bold: false });
    out.push({ text: m[1], bold: true });
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push({ text: s.slice(last), bold: false });
  return out;
}

export function mdLite(src: string): MdSection[] {
  const secs: MdSection[] = [];
  let list: MdInline[][] | null = null;
  const sec = (): MdSection => {
    if (!secs.length) secs.push({ heading: null, blocks: [] });
    return secs[secs.length - 1];
  };
  const flush = () => {
    if (list) {
      sec().blocks.push({ kind: 'ul', items: list });
      list = null;
    }
  };
  for (const raw of (src || '').split('\n')) {
    const line = raw.trim();
    let m: RegExpMatchArray | null;
    if (!line) flush();
    else if ((m = line.match(/^#{2,3}\s+(.*)/))) {
      flush();
      secs.push({ heading: m[1], blocks: [] });
    } else if ((m = line.match(/^[-*]\s+(.*)/))) {
      (list ??= []).push(mdInline(m[1]));
    } else {
      flush();
      sec().blocks.push({ kind: 'p', parts: mdInline(line) });
    }
  }
  flush();
  return secs;
}

const ASTRO_MARKERS = ['🔮 Астро-разбор от Месье Клода:', '🔮 Astro reading by Monsieur Claude:'];
const ASTRO_END = ['СОВЕТ:', 'ADVICE:', 'РАЗБОР:', 'BREAKDOWN:'];

/** Вырезает астро-блок из текста разбора. */
export function splitAstro(text: string): { main: string; astro: string | null } {
  const t = text || '';
  for (const m of ASTRO_MARKERS) {
    const i = t.indexOf(m);
    if (i < 0) continue;
    let rest = t.slice(i + m.length);
    let tail = '';
    let end = -1;
    for (const e of ASTRO_END) {
      const j = rest.indexOf(e);
      if (j >= 0 && (end < 0 || j < end)) end = j;
    }
    if (end >= 0) {
      tail = rest.slice(end);
      rest = rest.slice(0, end);
    }
    return { main: (t.slice(0, i).trim() + '\n\n' + tail).trim(), astro: rest.trim() };
  }
  return { main: t, astro: null };
}
