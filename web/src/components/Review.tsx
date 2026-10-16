import { useT } from '../i18n';
import { mdLite, splitAstro } from '../lib/markdown';

function Md({ text }: { text: string }) {
  return (
    <>
      {mdLite(text).map((s, i) => (
        <div className="mdsec" key={i}>
          {s.heading && <div className="mdh">{s.heading}</div>}
          {s.blocks.map((b, j) =>
            b.kind === 'p' ? (
              <p key={j}>{b.parts.map((p, k) => (p.bold ? <b key={k}>{p.text}</b> : p.text))}</p>
            ) : (
              <ul key={j}>
                {b.items.map((it, k) => (
                  <li key={k}>{it.map((p, n) => (p.bold ? <b key={n}>{p.text}</b> : p.text))}</li>
                ))}
              </ul>
            ),
          )}
        </div>
      ))}
    </>
  );
}

/** Текст разбора ИИ (markdown-lite) с отдельным астро-блоком. */
export function ReviewText({ text, className }: { text: string; className: string }) {
  const t = useT();
  const { main, astro } = splitAstro(text);
  return (
    <>
      <div className={className}><Md text={main} /></div>
      {astro && (
        <div className="astro">
          <div className="astrohd">🔮 {t('astro.title')}</div>
          <div className="astrobody"><Md text={astro} /></div>
        </div>
      )}
    </>
  );
}
