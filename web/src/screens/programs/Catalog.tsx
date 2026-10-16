import { Link, useParams } from 'react-router-dom';
import { programsApi, type Enrollment, type TreeNode } from '../../api/programs';
import { Async, SecTitle } from '../../components/ui';
import { useI18n } from '../../i18n';
import { useFetch } from '../../lib/useFetch';
import { Crumbs } from './parts';
import { countPrograms, findNode, isOpenableProgram, isPlanned, nodeTitle, pathTo, visibleChildren } from './tree';
import './programs.css';

function nodeHref(n: TreeNode): string | null {
  if (n.kind === 'program') return isOpenableProgram(n) ? `/programs/p/${n.slug}` : null;
  return `/programs/node/${n.slug}`; // спорт/система, в т.ч. «скоро»: откроется заглушка
}

export function NodeRow({ n }: { n: TreeNode }) {
  const { t, lang } = useI18n();
  const soon = isPlanned(n);
  const href = nodeHref(n);
  const total = n.kind === 'program' ? 0 : countPrograms(n);
  const inner = (
    <>
      <div className="pg-t">
        {nodeTitle(n, lang)}
        {n.kind !== 'program' && total > 0 && <div className="pg-s">{t('pg.n_programs', { n: total })}</div>}
      </div>
      {soon && <span className="pg-badge">{t('pg.soon')}</span>}
      {href && <span className="mut">›</span>}
    </>
  );
  if (!href) {
    return <div className="pg-row soon" aria-disabled="true" data-slug={n.slug}>{inner}</div>;
  }
  return <Link className={`pg-row${soon ? ' soon' : ''}`} to={href} data-slug={n.slug}>{inner}</Link>;
}

function MyPrograms({ list }: { list: Enrollment[] }) {
  const { t, lang } = useI18n();
  const live = list.filter((e) => e.status === 'active' || e.status === 'paused');
  if (!live.length) return null;
  return (
    <>
      <SecTitle>{t('pg.my')}</SecTitle>
      {live.map((e) => {
        const done = e.sessions.done ?? 0;
        const total = e.sessions.total || 1;
        return (
          <Link key={e.id} className="pg-row" to={`/programs/my/${e.id}`}>
            <div className="pg-t">
              {lang === 'en' ? e.title_en || e.title_ru : e.title_ru || e.title_en}
              <div className="pg-s">{t('pg.progress', { done, total: e.sessions.total })}</div>
              <div className="pg-bar"><i style={{ width: `${Math.round((done / total) * 100)}%` }} /></div>
            </div>
            <span className={`pg-badge ${e.status === 'active' ? 'ok' : 'warn'}`}>{t(`pg.status.${e.status}`)}</span>
          </Link>
        );
      })}
    </>
  );
}

/** Вкладка «Программы»: мои записи + корень каталога (Кроссфит / ТА / Бег). */
export function ProgramsHome() {
  const { t } = useI18n();
  const tree = useFetch(() => programsApi.tree(), 'pg-tree');
  const mine = useFetch(() => programsApi.enrollments(), 'pg-enrollments');
  return (
    <>
      <h1>{t('pg.title')}</h1>
      <div className="sub">{t('pg.subtitle')}</div>
      {mine.data && <MyPrograms list={mine.data} />}
      <SecTitle>{t('pg.catalog')}</SecTitle>
      <Async state={tree}>{(nodes) => <>{visibleChildren({ children: nodes }).map((n) => <NodeRow key={n.slug} n={n} />)}</>}</Async>
    </>
  );
}

/** Уровень каталога: спорт или система. planned-узел показывается заглушкой «наполняется». */
export function NodeScreen() {
  const { slug = '' } = useParams();
  const { t, lang } = useI18n();
  const tree = useFetch(() => programsApi.tree(), 'pg-tree');
  return (
    <Async state={tree}>
      {(nodes) => {
        const node = findNode(nodes, slug);
        if (!node) return <div className="msg err">{t('err.not_found')}</div>;
        const crumbs = [{ to: '/programs', label: t('pg.title') }, ...pathTo(nodes, slug).map((n, i, a) => ({ to: i < a.length - 1 ? `/programs/node/${n.slug}` : undefined, label: nodeTitle(n, lang) }))];
        const kids = visibleChildren(node);
        return (
          <>
            <Crumbs items={crumbs} />
            <h1>{nodeTitle(node, lang)}</h1>
            {isPlanned(node) && (
              <div className="pg-stub" role="note">
                <div style={{ fontSize: 30 }}>🚧</div>
                <b>{t('pg.filling')}</b>
                <div>{t('pg.filling_text')}</div>
              </div>
            )}
            {kids.map((n) => <NodeRow key={n.slug} n={n} />)}
          </>
        );
      }}
    </Async>
  );
}
