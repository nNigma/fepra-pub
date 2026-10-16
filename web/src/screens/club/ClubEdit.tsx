import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { clubApi, type ClubPreview, type DictEntry } from '../../api/club';
import { recordApi } from '../../api/record';
import { pollJob } from '../../lib/jobs';
import { Card, Loading, SecTitle } from '../../components/ui';
import { useT } from '../../i18n';
import { canManageClub } from '../../lib/roles';
import { useSession } from '../../lib/session';
import { BackLink, Guard, apiMessage, todayIso } from '../ui5';
import { GymPicker, useClubGym } from './clubGym';

/** Нераспознанная фраза: новое движение «как есть» или сопоставить с существующим. */
function Unknown({ phrase, canons, onResolved }: { phrase: string; canons: string[]; onResolved: () => void }) {
  const t = useT();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function resolve(n?: string) {
    setBusy(true);
    setErr(null);
    try {
      await clubApi.resolve(phrase, n);
      onResolved();
    } catch (e) {
      setErr(apiMessage(e, t));
      setBusy(false);
    }
  }
  return (
    <Card>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>«{phrase}»</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input list="club-canons" aria-label={t('club.match_to')} placeholder={t('club.match_to')} value={name} onChange={(e) => setName(e.target.value)}
          style={{ flex: 1, minWidth: 140, minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 10px', background: 'var(--bg)' }} />
        <button type="button" className="btn" disabled={busy || !name.trim()} onClick={() => void resolve(name.trim())}>{t('club.match')}</button>
        <button type="button" className="btn" disabled={busy} onClick={() => void resolve()}>{t('club.new_movement')}</button>
      </div>
      <datalist id="club-canons">{canons.map((c) => <option key={c} value={c} />)}</datalist>
      {err && <div className="msg err" role="alert">{err}</div>}
    </Card>
  );
}

function Dictionary({ dict }: { dict: DictEntry[] }) {
  const t = useT();
  const [f, setF] = useState('');
  const [alias, setAlias] = useState('');
  const [canon, setCanon] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const shown = dict.filter((d) => !f || d.canon.includes(f.toLowerCase()) || d.aliases.some((a) => a.toLowerCase().includes(f.toLowerCase()))).slice(0, 30);
  return (
    <details style={{ marginTop: 14 }}>
      <summary style={{ minHeight: 44, display: 'flex', alignItems: 'center', cursor: 'pointer' }}>{t('club.dictionary')} ({dict.length})</summary>
      <input aria-label={t('club.search')} placeholder={t('club.search')} value={f} onChange={(e) => setF(e.target.value)}
        style={{ width: '100%', minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 10px', background: 'var(--card)', margin: '6px 0' }} />
      {shown.map((d) => <div key={d.canon} className="kv"><b>{d.canon}</b><span style={{ textAlign: 'right' }}>{d.aliases.slice(0, 4).join(', ')}</span></div>)}
      <form style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }} onSubmit={(e) => {
        e.preventDefault();
        if (!alias.trim() || !canon.trim()) return;
        clubApi.addAliases([{ alias: alias.trim(), canon: canon.trim() }]).then(() => { setMsg(t('club.alias_added')); setAlias(''); }, (er) => setMsg(apiMessage(er, t)));
      }}>
        <input aria-label={t('club.alias')} placeholder={t('club.alias')} value={alias} onChange={(e) => setAlias(e.target.value)} style={{ flex: 1, minWidth: 120, minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 10px', background: 'var(--card)' }} />
        <input aria-label={t('club.canon')} list="club-canons2" placeholder={t('club.canon')} value={canon} onChange={(e) => setCanon(e.target.value)} style={{ flex: 1, minWidth: 120, minHeight: 44, borderRadius: 10, border: '1px solid var(--bd)', padding: '0 10px', background: 'var(--card)' }} />
        <datalist id="club-canons2">{dict.map((d) => <option key={d.canon} value={d.canon} />)}</datalist>
        <button type="submit" className="btn">{t('club.alias_add')}</button>
      </form>
      {msg && <div className="msg info" role="status">{msg}</div>}
    </details>
  );
}

function Editor() {
  const t = useT();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const day = sp.get('day') || todayIso();
  // программа пишется в выбранный зал; выбирать можно только из залов, где есть право менять
  const { gym, gyms, pick, ready, failed, canAdd, add } = useClubGym('manage');
  const [text, setText] = useState<string | null>(null);
  const [prev, setPrev] = useState<ClubPreview | null>(null);
  const [dict, setDict] = useState<DictEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState<{ unknown: string[]; verifying: boolean } | null>(null);
  const [photoBusy, setPhotoBusy] = useState<null | 'upload' | 'parse'>(null);
  const [photoMsg, setPhotoMsg] = useState<string | null>(null);
  const camRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!ready || (!gym && !failed)) return;
    let alive = true;
    setText(null);
    setPrev(null);
    setSaved(null);
    clubApi.program(day, gym).then((d) => { if (alive) { setText(d.program?.raw_text ?? ''); } }, (e) => { if (alive) { setText(''); setErr(apiMessage(e, t)); } });
    clubApi.dictionary().then((d) => alive && setDict(d), () => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day, gym, ready]);

  // фото доски: тренер грузит один раз, распознанный текст попадает в редактор, дальше — проверка и сохранение
  async function onPhoto(file: File | undefined) {
    if (!file) return;
    setErr(null);
    setPhotoMsg(null);
    if (file.size > 10 * 1024 * 1024) { setErr(t('club.photo_big')); return; }
    if (file.type && !file.type.startsWith('image/')) { setErr(t('club.photo_type')); return; }
    try {
      setPhotoBusy('upload');
      const up = await recordApi.upload(file, 'board');
      setPhotoBusy('parse');
      const { job_id } = await clubApi.parsePhoto(up.id, 'fast', gym);
      const job = await pollJob(job_id, { intervalMs: 1500 });
      const res = job.result as { recognized?: boolean; board_text?: string | null } | null;
      if (!res?.recognized || !res.board_text) { setPhotoMsg(t('club.photo_fail')); return; }
      setText(res.board_text);
      setSaved(null);
      setPhotoMsg(t('club.photo_ok'));
      setPrev(await clubApi.preview(res.board_text, gym));
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setPhotoBusy(null);
    }
  }
  async function preview() {
    setBusy(true);
    setErr(null);
    try {
      setPrev(await clubApi.preview(text ?? '', gym));
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const r = await clubApi.save({ day, raw_text: text ?? '', gym });
      setSaved({ unknown: r.unknown, verifying: !!r.job_id });
      if (r.unknown.length === 0) nav(`/club?day=${day}&gym=${encodeURIComponent(gym ?? '')}`);
    } catch (e) {
      setErr(apiMessage(e, t));
    } finally {
      setBusy(false);
    }
  }
  if (ready && !failed && gyms.length === 0) return <div className="msg err" role="alert">{t('club.no_manage_gym')}</div>;
  if (text == null) return <Loading />;
  return (
    <>
      <GymPicker gym={gym} gyms={gyms} onPick={pick} canAdd={canAdd} onAdd={add} />
      <div className="sub">{gym ?? ''} · {day}</div>
      <div className="sec">{t('club.photo_title')}</div>
      <input ref={camRef} type="file" accept="image/*" capture="environment" className="hidden-file" data-testid="club-cam"
        onChange={(e) => { void onPhoto(e.target.files?.[0]); e.target.value = ''; }} />
      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" className="hidden-file" data-testid="club-file"
        onChange={(e) => { void onPhoto(e.target.files?.[0]); e.target.value = ''; }} />
      <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
        <button type="button" className="btn" style={{ flex: 1 }} disabled={!!photoBusy} onClick={() => camRef.current?.click()}>📷 {t('club.photo_take')}</button>
        <button type="button" className="btn" style={{ flex: 1 }} disabled={!!photoBusy} onClick={() => fileRef.current?.click()}>🖼 {t('club.photo_choose')}</button>
      </div>
      {photoBusy && <div className="loading" role="status">{photoBusy === 'upload' ? t('club.photo_uploading') : t('club.photo_recognizing')}</div>}
      {photoMsg && <div className="msg info" role="status">{photoMsg}</div>}
      <div className="mut" style={{ fontSize: 12.5, marginBottom: 8 }}>{t('club.photo_hint')}</div>
      <label className="field">
        <span>{t('club.program_text')}</span>
        <textarea rows={10} value={text} placeholder={t('club.program_ph')} onChange={(e) => { setText(e.target.value); setPrev(null); setSaved(null); }} />
      </label>
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="btn" style={{ flex: 1 }} disabled={busy || !text.trim()} onClick={() => void preview()}>{t('club.preview')}</button>
        <button type="button" className="btn primary" style={{ flex: 1 }} disabled={busy || !text.trim()} onClick={() => void save()}>{t('club.save')}</button>
      </div>
      {err && <div className="msg err" role="alert">{err}</div>}
      {prev && (
        <>
          <SecTitle>{t('club.preview_title')}</SecTitle>
          <Card>
            <div className="mut" style={{ fontSize: 12 }}>{t('club.format')}: {prev.format}</div>
            <div style={{ margin: '6px 0' }}>{prev.canon.map((c) => <span key={c} className="wchip" style={{ marginRight: 4 }}>{c}</span>)}</div>
            <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{prev.annotated}</div>
          </Card>
          {prev.unknown.length > 0 && (
            <>
              <SecTitle>{t('club.unknown')}</SecTitle>
              {prev.unknown.map((u) => <Unknown key={u} phrase={u} canons={dict.map((d) => d.canon)} onResolved={() => void preview()} />)}
            </>
          )}
        </>
      )}
      {saved && (
        <div className="msg ok" role="status">
          {t('club.saved')}{saved.verifying ? ` ${t('club.verifying')}` : ''}
          {saved.unknown.length > 0 && <div>{t('club.saved_unknown', { list: saved.unknown.join(', ') })}</div>}
          <div style={{ marginTop: 8 }}><button type="button" className="btn" onClick={() => nav(`/club?day=${day}&gym=${encodeURIComponent(gym ?? '')}`)}>{t('club.to_program')}</button></div>
        </div>
      )}
      <Dictionary dict={dict} />
    </>
  );
}

export function ClubEditScreen() {
  const t = useT();
  const { me } = useSession();
  return (
    <>
      <BackLink to="/club" />
      <h1>{t('club.edit')}</h1>
      <Guard ok={canManageClub(me)}><Editor /></Guard>
    </>
  );
}
