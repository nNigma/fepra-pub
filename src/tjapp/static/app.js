const tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const app = document.getElementById('app');
const INIT = tg ? tg.initData : '';
let LAST_LIST = null;
let AS = null;
function withAs(path){ if(AS==null) return path; return path + (path.includes('?')?'&':'?') + 'as=' + encodeURIComponent(AS); }

async function api(path){
  const res = await fetch(withAs(path), {headers:{'X-Init-Data':INIT}});
  if(!res.ok) throw new Error(res.status);
  return res.json();
}

async function llmCall(kind, ref, refresh){
  const r = await fetch('/api/llm/'+kind+'/'+encodeURIComponent(ref)+(refresh?'?refresh=1':''),
    {method:'POST', headers:{'X-Init-Data':INIT}});
  if(r.status===403) return {error:'pro'};
  if(r.status===429){ const j=await r.json().catch(()=>({})); return {error:'limit', detail:(j&&j.detail)||''}; }
  if(!r.ok) return {error:'fail'};
  return await r.json();
}
function llmSig(engine){
  if(!engine) return '';
  // agent-хелпер ходит в те же модели Claude — для читателя это тот же Клод
  const s=(engine==='claude'||engine==='agent')?T('llm.by_claude'):T('llm.by_gemini');
  return `<div class="mut" style="font-size:11.5px;margin:1px 0 7px">${s}</div>`;
}
function llmShow(box, kind, ref, text, engine){
  box.innerHTML=`<div class="llmhead">${T('llm.head')}</div>`+llmSig(engine)
    +reviewInner(text,'llmtext')
    +`<button class="llmbtn" onclick="llmGo('${kind}','${ref}',1)">${T('llm.refresh')}</button>`;
  if(kind==='summary') refreshAdvice();
}
async function llmGo(kind, ref, refresh){
  const box=document.getElementById('llm_'+kind);
  const H=`<div class="llmhead">${T('llm.head')}</div>`;
  if(box) box.innerHTML=H+`<div class="mut">${T('llm.thinking')}</div>`;
  const res=await llmCall(kind, ref, refresh);
  if(!box) return;
  if(res.error==='pro'){ box.innerHTML=H+`<div class="mut">${T('llm.need_pro')}</div>`; return; }
  if(res.error==='limit'){ box.innerHTML=H+`<div class="mut">${T('llm.limit_prefix').replace('{detail}',res.detail||T('llm.limit_default'))}</div>`; return; }
  if(res.error){ box.innerHTML=H+`<div class="mut">${T('llm.unavailable')}</div>`; return; }
  if(res.text){ llmShow(box, kind, ref, res.text, res.engine); return; }
  if(!res.pending){ box.innerHTML=H+`<div class="mut">${T('llm.unavailable')}</div>`; return; }
  // генерация в фоне: поллим кэш, пока Месье Клод пишет (туннель не держим)
  box.innerHTML=H+`<div class="mut">${T('llm.pending')}</div>`;
  for(let i=0;i<50;i++){
    await new Promise(r=>setTimeout(r,4000));
    try{
      const d=await api('/api/llm/'+kind+'/'+encodeURIComponent(ref));
      if(d&&d.cached&&d.cached.text){ llmShow(box, kind, ref, d.cached.text, d.cached.engine); return; }
    }catch(e){}
  }
  box.innerHTML=H+`<div class="mut">${T('llm.pending_long')}</div>`;
}
function llmBlock(kind, ref, pro, cached, stale){
  if(!pro) return `<div class="mut" style="margin:10px 2px;font-size:12px">${T('llm.pro_only')}</div>`;
  const head=`<div class="llmhead">${T('llm.head')}</div>`;
  const ctext=cached&&(cached.text||cached);           // объект {text,engine} или строка (старый кэш)
  const inner = ctext
    ? head+(stale?`<span class="review-stale">🟡 ${T('llm.stale')}</span>`:'')+llmSig(cached&&cached.engine)+reviewInner(ctext,'llmtext')
      +`<button class="llmbtn" onclick="llmGo('${kind}','${ref}',1)">${T('llm.refresh')}</button>`
    : head+`<button class="llmbtn" onclick="llmGo('${kind}','${ref}',0)">${T('llm.run')}</button>`;
  return `<div class="llmwrap" id="llm_${kind}">${inner}</div>`;
}
function loadLlm(kind, ref, pro){
  fetch(withAs('/api/llm/'+kind+'/'+encodeURIComponent(ref)), {headers:{'X-Init-Data':INIT}})
    .then(r=>r.ok?r.json():{available:false,cached:null})
    .then(d=>{ const host=document.getElementById('llmhost_'+kind);
      if(host) host.innerHTML=llmBlock(kind, ref, pro, d.cached, d.stale); });
}

function mdEsc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function mdInline(s){return mdEsc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>');}
function mdLite(src){
  const secs=[]; let list=null;
  const sec=()=>{ if(!secs.length) secs.push({h:null,body:[]}); return secs[secs.length-1]; };
  const flush=()=>{ if(list){ sec().body.push('<ul>'+list.join('')+'</ul>'); list=null; } };
  (src||'').split('\n').forEach(raw=>{
    const line=raw.trim(); let m;
    if(!line){ flush(); }
    else if(m=line.match(/^#{2,3}\s+(.*)/)){ flush(); secs.push({h:mdInline(m[1]),body:[]}); }
    else if(m=line.match(/^[-*]\s+(.*)/)){ if(!list)list=[]; list.push('<li>'+mdInline(m[1])+'</li>'); }
    else { flush(); sec().body.push('<p>'+mdInline(line)+'</p>'); }
  });
  flush();
  return secs.map(s=>`<div class="mdsec">${s.h?`<div class="mdh">${s.h}</div>`:''}${s.body.join('')}</div>`).join('');
}
const ASTRO_MARKERS=["🔮 Астро-разбор от Месье Клода:","🔮 Astro reading by Monsieur Claude:"];
const ASTRO_END=["СОВЕТ:","ADVICE:","РАЗБОР:","BREAKDOWN:"];
function splitAstro(text){
  const t=text||'';
  for(const m of ASTRO_MARKERS){
    const i=t.indexOf(m); if(i<0) continue;
    let rest=t.slice(i+m.length), tail='', end=-1;
    for(const e of ASTRO_END){ const j=rest.indexOf(e); if(j>=0 && (end<0||j<end)) end=j; }
    if(end>=0){ tail=rest.slice(end); rest=rest.slice(0,end); }
    return {main:(t.slice(0,i).trim()+'\n\n'+tail).trim(), astro:rest.trim()};
  }
  return {main:t, astro:null};
}
function reviewInner(text, cls){
  const {main,astro}=splitAstro(text);
  let h=`<div class="${cls}">${mdLite(main)}</div>`;
  if(astro) h+=`<div class="astro"><div class="astrohd">🔮 ${T('astro.title')}</div><div class="astrobody">${mdLite(astro)}</div></div>`;
  return h;
}
function claudeBlock(d){
  const head=`<div class="clhead">${T('claude.head')}</div>`;
  const body = d.text
    ? reviewInner(d.text,'cltext')
    : `<div class="mut" style="padding:2px 0">${T('claude.pending')}</div>`;
  return `<div class="clwrap">${head}${body}</div>`;
}
function loadClaude(refKey, pro, slot){
  if(!pro) return;
  fetch(withAs('/api/claude/'+encodeURIComponent(refKey)), {headers:{'X-Init-Data':INIT}})
    .then(r=>r.ok?r.json():{available:false,text:null})
    .then(d=>{ if(!d.available||!d.text) return;
      const host=document.getElementById('claudehost_'+slot);
      if(host) host.innerHTML=claudeBlock(d);
      const g=document.getElementById('llmhost_'+slot); if(g) g.style.display='none'; });
}

const METRIC_IDS=['readiness','hrv','rhr','sleep','bb','sleep_score','spo2','respiration','sleep_deep','sleep_rem','vo2max','acwr','load_debt','monotony','strain'];
function metricInfo(id){ return {name:T('metric.'+id+'.name'), desc:T('metric.'+id+'.desc')}; }

function metricChartSvg(series, base, dir, sparse){
  if(!series||series.length<(sparse?1:2)) return `<div class="mut" style="font-size:12px;padding:6px 0">${T('chart.no_data')}</div>`;
  const w=320,h=112,x1=w-6,y1=h-16,n=series.length;
  const x0=sparse?14:24, y0=sparse?20:8;
  const vals=series.map(p=>p[1]);
  const rawLo=Math.min(...vals),rawHi=Math.max(...vals);
  let lo=rawLo,hi=rawHi;
  if(base!=null){lo=Math.min(lo,base);hi=Math.max(hi,base);}
  if(hi===lo)hi=lo+1;
  const pad=(hi-lo)*0.12;lo-=pad;hi+=pad;
  let X;
  if(sparse){ // редкие точки (вес): раскладка по ДАТАМ, не по индексу
    const t0=Date.parse(series[0][0]);
    const span=(Date.parse(series[n-1][0])-t0)||1;
    X=i=>x0+10+((Date.parse(series[i][0])-t0)/span)*(x1-x0-20);
  } else {
    X=i=>x0+(i/(n-1))*(x1-x0);
  }
  const Y=v=>y1-((v-lo)/(hi-lo))*(y1-y0);
  const yb=base!=null?Y(base):null;
  let area='';
  if(yb!=null){
    const yBad=v=>{const y=Y(v);return dir==='high_bad'?Math.min(y,yb):Math.max(y,yb);};
    let d=`M ${X(0).toFixed(1)} ${yb.toFixed(1)}`;
    for(let i=0;i<n;i++)d+=` L ${X(i).toFixed(1)} ${yBad(series[i][1]).toFixed(1)}`;
    d+=` L ${X(n-1).toFixed(1)} ${yb.toFixed(1)} Z`;
    area=`<path d="${d}" fill="var(--red)" opacity=".2"/>`;
  }
  let line='';
  for(let i=0;i<n-1;i++)line+=`<line x1="${X(i).toFixed(1)}" y1="${Y(series[i][1]).toFixed(1)}" x2="${X(i+1).toFixed(1)}" y2="${Y(series[i+1][1]).toFixed(1)}" stroke="var(--tx)" stroke-width="1.6" opacity=".82"/>`;
  const baseLine=yb!=null?`<line x1="${x0}" y1="${yb.toFixed(1)}" x2="${x1}" y2="${yb.toFixed(1)}" stroke="var(--mut)" stroke-width="1" stroke-dasharray="4 3"/><text x="${x1}" y="${(yb-3).toFixed(1)}" font-size="9" fill="var(--mut)" text-anchor="end">${T('chart.bench').replace('{base}',base)}</text>`:'';
  let marks='', xlabels='', yscale='';
  if(sparse&&n<=12){ // точка + значение над ней + дата под ней
    marks=series.map((p,i)=>{const x=X(i),y=Y(p[1]);
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="var(--tx)"/>`+
        `<text x="${x.toFixed(1)}" y="${(y-8).toFixed(1)}" font-size="10.5" font-weight="600" fill="var(--tx)" text-anchor="middle">${fmt(p[1])}</text>`+
        `<text x="${x.toFixed(1)}" y="${h-3}" font-size="9" fill="var(--mut)" text-anchor="middle">${p[0].slice(5)}</text>`;}).join('');
  } else {
    yscale=`<text x="2" y="${(Y(rawHi)+3).toFixed(1)}" font-size="9" fill="var(--mut)">${fmt(rawHi)}</text>`+
           `<text x="2" y="${(Y(rawLo)+3).toFixed(1)}" font-size="9" fill="var(--mut)">${fmt(rawLo)}</text>`;
    xlabels=`<text x="${x0}" y="${h-3}" font-size="9" fill="var(--mut)">${series[0][0].slice(5)}</text><text x="${x1}" y="${h-3}" font-size="9" fill="var(--mut)" text-anchor="end">${series[n-1][0].slice(5)}</text>`;
  }
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%">${area}${baseLine}${line}${marks}${yscale}${xlabels}</svg>`;
}

function metricOverlaySvg(sA, sB, labA, labB, baseA, baseB){
  const clean=s=>(s||[]).filter(p=>p[1]!=null);
  const a=clean(sA), b=clean(sB);
  if(a.length<2&&b.length<2) return `<div class="mut" style="font-size:12px;padding:6px 0">${T('chart.no_data')}</div>`;
  const w=320,h=112,x1=w-6,y1=h-16,x0=24,y0=8;
  const all=a.concat(b).map(p=>p[1]).concat([baseA,baseB].filter(v=>v!=null));
  let lo=Math.min(...all),hi=Math.max(...all); if(hi===lo)hi=lo+1;
  const pad=(hi-lo)*0.12; lo-=pad; hi+=pad;
  const ds=[...new Set(a.concat(b).map(p=>p[0]))].sort();
  const t0=Date.parse(ds[0]), span=(Date.parse(ds[ds.length-1])-t0)||1;
  const X=d=>x0+((Date.parse(d)-t0)/span)*(x1-x0);
  const Y=v=>y1-((v-lo)/(hi-lo))*(y1-y0);
  // низкий сон = плохо: красная заливка там, где линия НИЖЕ своей базы
  const badArea=(s,base)=>{if(base==null||s.length<2)return '';const yb=Y(base);
    let d=`M ${X(s[0][0]).toFixed(1)} ${yb.toFixed(1)}`;
    for(const p of s)d+=` L ${X(p[0]).toFixed(1)} ${Math.max(Y(p[1]),yb).toFixed(1)}`;
    d+=` L ${X(s[s.length-1][0]).toFixed(1)} ${yb.toFixed(1)} Z`;
    return `<path d="${d}" fill="var(--red)" opacity=".16"/>`;};
  const baseLine=(base,col)=>base==null?'':`<line x1="${x0}" y1="${Y(base).toFixed(1)}" x2="${x1}" y2="${Y(base).toFixed(1)}" stroke="${col}" stroke-width="1" stroke-dasharray="4 3" opacity=".6"/>`;
  const draw=(s,col)=>{let l='';for(let i=0;i<s.length-1;i++)l+=`<line x1="${X(s[i][0]).toFixed(1)}" y1="${Y(s[i][1]).toFixed(1)}" x2="${X(s[i+1][0]).toFixed(1)}" y2="${Y(s[i+1][1]).toFixed(1)}" stroke="${col}" stroke-width="1.8"/>`;return l;};
  const cA='#378ADD', cB='#4aaa99';
  const yscale=`<text x="2" y="${(Y(hi-pad)+3).toFixed(1)}" font-size="9" fill="var(--mut)">${fmt(hi-pad)}</text><text x="2" y="${(Y(lo+pad)+3).toFixed(1)}" font-size="9" fill="var(--mut)">${fmt(lo+pad)}</text>`;
  const legend=`<div style="display:flex;gap:14px;justify-content:center;font-size:11px;margin-top:2px"><span><span style="display:inline-block;width:10px;height:3px;background:${cA};vertical-align:middle"></span> ${labA}</span><span><span style="display:inline-block;width:10px;height:3px;background:${cB};vertical-align:middle"></span> ${labB}</span></div>`;
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%">${badArea(a,baseA)}${badArea(b,baseB)}${baseLine(baseA,cA)}${baseLine(baseB,cB)}${draw(a,cA)}${draw(b,cB)}${yscale}</svg>${legend}`;
}

function toggleMetric(id){
  const host=document.getElementById('metricDetail');
  if(!host) return;
  if(host.dataset.open===id){host.innerHTML='';host.dataset.open='';return;}
  host.dataset.open=id;
  const info=id?metricInfo(id):{name:id,desc:''};
  const md=(window.SUMMARY_METRICS||{})[id];
  const dm=window.SUMMARY_METRICS||{};
  let chart=md?metricChartSvg(md.series,md.base,md.dir):'';
  if(id==='sleep_deep'||id==='sleep_rem')
    chart=metricOverlaySvg((dm.sleep_deep||{}).series,(dm.sleep_rem||{}).series,T('metric.sleep_deep.name'),T('metric.sleep_rem.name'),(dm.sleep_deep||{}).base,(dm.sleep_rem||{}).base);
  let extraLine='';
  if(id==='hrv'&&window.HRV_STATUS_CUR)extraLine=hrvStatusHtml(window.HRV_STATUS_CUR);
  if(id==='sleep'&&window.SLEEP_STRUCT)extraLine=sleepStructHtml(window.SLEEP_STRUCT);
  host.innerHTML=`<div class="mdetail"><div class="mdetail-hd">${info.name}${md&&md.base!=null?T('mdetail.bench').replace('{base}',md.base):''}</div><div class="mdetail-desc">${info.desc}</div>${extraLine}${chart}<div class="mdetail-hint">${T('mdetail.hint')}</div></div>`;
  host.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function metricsHelpHtml(){
  return `<details class="methelp"><summary>${T('methelp.title')}</summary>${METRIC_IDS.map(id=>{const info=metricInfo(id);return `<div class="methelp-it"><b>${info.name}</b> - ${info.desc}</div>`}).join('')}</details>`;
}

const NUTRW_LABELS=()=>({kcal:T('nut.kcal'),protein_g:T('nut.protein'),fat_g:T('nut.fat'),carb_g:T('nut.carb'),fiber_g:T('nut.m_fiber'),sugar_g:T('nut.m_sugar'),sodium_mg:T('nut.m_sodium'),iron_mg:T('nut.m_iron'),calcium_mg:T('nut.m_calcium'),magnesium_mg:T('nut.m_magnesium'),potassium_mg:T('nut.m_potassium')});

function toggleNutrMetric(id){
  const host=document.getElementById('nutrWeekDetail');
  const nw=window.NUTR_WEEK;
  if(!host||!nw)return;
  if(host.dataset.open===id){host.innerHTML='';host.dataset.open='';return;}
  host.dataset.open=id;
  const m=(nw.metrics||{})[id]||{};
  const chart=metricChartSvg(m.series||[],m.base,m.dir,true);
  const bench=m.base!=null?` · ${T('nutw.bench').replace('{v}',m.base)}`:'';
  host.innerHTML=`<div class="mdetail"><div class="mdetail-hd">${NUTRW_LABELS()[id]||id}${bench}</div>${chart}<div class="mdetail-hint">${T('mdetail.hint')}</div></div>`;
  host.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function nutrWeekSection(nw){
  if(!nw)return '';
  const clsC={green:'var(--green)',amber:'var(--amber)',red:'var(--red)'};
  const k=nw.kcal||{};
  const dTxt=k.delta==null?'':(k.cls==='green'?T('nutw.on_target'):(k.delta<0?T('nutw.under').replace('{v}',-k.delta):T('nutw.over').replace('{v}',k.delta)));
  const kcalCard=`<div class="card" style="margin-bottom:8px;cursor:pointer" onclick="toggleNutrMetric('kcal')">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <div><span style="font-size:26px;font-weight:700">${k.sum!=null?k.sum:'—'}</span><span style="font-size:12px;opacity:.6;margin-left:4px">${k.target_week?'/ '+k.target_week+' ':''}${T('nut.kcal')} ›</span></div>
      <div style="font-size:13px;font-weight:600;color:${clsC[k.cls]||'var(--mut)'}">${dTxt}</div>
    </div>
    <div style="font-size:12px;color:var(--mut);margin-top:3px">${T('nutw.avg_day').replace('{v}',k.avg+' '+T('nut.kcal'))}</div>
  </div>`;
  const mbarW=(id,label,color)=>{
    const m=(nw.metrics||{})[id];
    if(!m)return '';
    const pct=m.target_week?Math.min(100,Math.round(m.sum/m.target_week*100)):0;
    return `<div style="flex:1;background:rgba(128,128,128,.08);border-radius:10px;padding:8px;cursor:pointer" onclick="toggleNutrMetric('${id}')">
      <div style="font-size:11px;color:var(--mut)">${label} ›</div>
      <div style="font-weight:700">${Math.round(m.sum)}${m.target_week?'/'+m.target_week:''} ${T('nut.g')}</div>
      ${m.target_week?`<div style="height:4px;background:rgba(128,128,128,.25);border-radius:2px;margin-top:4px"><div style="width:${pct}%;height:4px;background:${color};border-radius:2px"></div></div>`:''}
      <div style="font-size:11px;color:var(--mut);margin-top:4px">${T('nutw.avg_day').replace('{v}',Math.round(m.avg)+' '+T('nut.g'))}</div>
    </div>`;
  };
  const microTiles=[['fiber_g',T('nut.g')],['sugar_g',T('nut.g')],['sodium_mg',T('nut.mg')],['iron_mg',T('nut.mg')],['calcium_mg',T('nut.mg')],['magnesium_mg',T('nut.mg')],['potassium_mg',T('nut.mg')]]
    .map(([id,unit])=>{
      const m=(nw.metrics||{})[id];
      if(!m)return '';
      const lim=m.dir==='high_bad'?'≤':'';
      return `<div class="det-tile" style="cursor:pointer" onclick="toggleNutrMetric('${id}')">
        <div class="det-tile-v"${m.flag?' style="color:var(--red)"':''}>${Math.round(m.sum)}/${lim}${m.target_week}</div>
        <div class="det-tile-l">${NUTRW_LABELS()[id]}, ${unit} · ${T('nutw.avg_day').replace('{v}',Math.round(m.avg))} ›</div></div>`;
    }).join('');
  const listCard=(title,items)=>items&&items.length?`
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin:14px 0 8px">${title}</div>
    <div class="card">${items.map(x=>`<div style="font-size:13px;margin:3px 0">• ${x}</div>`).join('')}</div>`:'';
  const ppk=nw.protein_per_kg_avg;
  const d1=nw.range[0].slice(8)+'.'+nw.range[0].slice(5,7),d2=nw.range[1].slice(8)+'.'+nw.range[1].slice(5,7);
  return `<h2>${T('nutw.title')}</h2>
  <div class="sub">${T('nutw.sub').replace('{a}',d1).replace('{b}',d2).replace('{n}',nw.days_recorded)}</div>
  ${kcalCard}
  <div style="display:flex;gap:8px;margin-bottom:8px">${mbarW('protein_g',T('nut.protein'),'#e5484d')}${mbarW('fat_g',T('nut.fat'),'#b088f9')}${mbarW('carb_g',T('nut.carb'),'#4c8dff')}</div>
  ${ppk!=null?`<div style="font-size:12px;color:${nw.protein_ok?'var(--green)':'var(--amber)'};margin:-2px 0 8px">${T('nutw.protein_per_kg').replace('{v}',ppk)}</div>`:''}
  <div id="nutrWeekDetail" data-open=""></div>
  <div class="det-tiles" style="grid-template-columns:repeat(2,1fr)">${microTiles}</div>
  ${listCard(T('nutw.conclusions_hd'),nw.conclusions)}
  ${listCard(T('nut.advice_hd'),nw.advice)}`;
}

const V = {green:['var(--greenb)','var(--green)'],amber:['var(--amberb)','var(--amber)'],red:['var(--redb)','var(--red)']};

function adviceCard(adv){
  if(!adv) return '';
  const c=V[adv.level]||V.green;
  const src=adv.source==='claude'?T('summary.advice_src_claude'):adv.source==='gemini'?T('summary.advice_src_gemini'):T('summary.advice_src_rules');
  const dot=adv.level==='red'?'🔴':adv.level==='amber'?'🟡':'🟢';
  const dt=adv.date?adv.date.slice(8,10)+'.'+adv.date.slice(5,7)+' · ':'';
  const stale=adv.stale?`<div class="advice-stale">${T('summary.advice_stale')}</div>`:'';
  return `<div class="advice" style="background:${c[0]}">
    <div class="advice-hd"><span>${T('summary.advice_hd')}</span><span class="advice-src">${dt}${src}</span></div>
    <div class="advice-ttl" style="color:${c[1]}">${dot} ${mdEsc(adv.title)}</div>
    <div class="advice-txt">${mdEsc(adv.text)}</div>
    ${stale}
  </div>`;
}

async function refreshAdvice(){
  const host=document.getElementById('advicehost');
  if(!host) return;
  try{
    const d=await api('/api/summary');
    if(d&&d.advice){ DATA.advice=d.advice; host.innerHTML=adviceCard(d.advice); }
  }catch(e){}
}
function tier(r){return r==null?['var(--card)','var(--mut)']:r>=70?V.green:r>=45?V.amber:V.red}
function fmt(x){return x==null?'—':(Math.round(x*10)/10)}
function delta(d){return d==null?'':(d>=0?'+':'')+fmt(d)}
function dcol(d,hiBad){if(d==null)return 'var(--mut)';const bad=hiBad?d>0:d<0;return bad?'var(--red)':'var(--green)'}
function scoreSec(s){const m=/^(\d+):(\d{2})$/.exec(s||'');return m?(+m[1]*60+ +m[2]):null}
function qEmoji(key){ const s=T(key); const i=s.indexOf(' '); return i>0?s.slice(0,i):s; }
function qLabel(key){ const s=T(key); const i=s.indexOf(' '); return i>0?s.slice(i+1):s; }
function microFlagsLine(flags){
  if(!flags||!flags.length)return '';
  const MICRO_LIMIT=new Set(['sugar_g','sodium_mg']);
  const txt=flags.map(k=>T('nut.m_'+k.replace('_g','').replace('_mg',''))+(MICRO_LIMIT.has(k)?'↑':'↓')).join(', ');
  return `<div style="font-size:12px;color:var(--mut);margin-top:6px">⚗️ ${txt}</div>`;
}

function tabbar(active){
  const t=(v,icon,label)=>`<a class="${active===v?'on':''}" onclick="go('${v}')"><span class="ti">${icon}</span>${label}</a>`;
  return `<div class="tabbar">${t('summary','📊',T('tab.summary'))}${t('workouts','🏋️',T('tab.workouts'))}${t('nutrition','🍽',T('tab.nutrition'))}${t('competitions','🏆',T('tab.competitions'))}${t('goals','🎯',T('tab.goals'))}${t('leaderboard','🥇',T('tab.leaderboard'))}</div>`;
}
function go(view){ history.replaceState(null,'',`?view=${view}`); load(); }

const HRV_STATUS_COL={BALANCED:'var(--green)',UNBALANCED:'var(--amber)',LOW:'var(--red)',POOR:'var(--red)'};
function hrvStatusHtml(st){
  const key='hrv.status.'+String(st).toLowerCase();
  const label=T(key); if(label===key) return '';
  const col=HRV_STATUS_COL[st]||'var(--mut)';
  return `<div style="margin-top:8px;font-size:13px">${T('metric.hrv.name')}: <b style="color:${col}">${label}</b></div>`;
}
function sleepStructHtml(s){
  const bits=[];
  if(s.deep!=null)bits.push(`${T('sleep.deep')} <b>${s.deep}</b> ${T('common.h')}`);
  if(s.rem!=null)bits.push(`${T('sleep.rem')} <b>${s.rem}</b> ${T('common.h')}`);
  return bits.length?`<div style="margin-top:8px;font-size:13px">${bits.join(' · ')}</div>`:'';
}
function renderSummary(DATA){
  window.SUMMARY_METRICS=DATA.metrics||{};
  window.HRV_STATUS_CUR=DATA.hrv_status||null;
  window.SLEEP_STRUCT=(DATA.sleep_deep_h!=null||DATA.sleep_rem_h!=null)?{deep:DATA.sleep_deep_h,rem:DATA.sleep_rem_h}:null;
  window.NUTR_WEEK=DATA.nutrition_week||null;
  const m=DATA.m, vd=DATA.verdict, S=DATA.series;
  const st=DATA.state||{};
  const mc=DATA.microcycle||{};
  const n30=DATA.narrative30||[];
  const risk=st.risk||{};
  const sigs=st.signals||{};
  const form=st.form||{};
  const rdy=st.readiness||{};

  function metric(id,label,b,note,hiBad){const val=b?fmt(b.latest):'—';const dl=b?delta(b.delta):'';
   const tap=id?`onclick="toggleMetric('${id}')" style="cursor:pointer"`:'';
   return `<div class="mc" ${tap}><div class="l">${label}${id?' ›':''}</div><div class="v">${val} <span class="d" style="color:${b?dcol(b.delta,hiBad):'var(--mut)'}">${dl}</span></div><div class="n">${note}</div></div>`}

  function metricCard(id,hiBad,unit){const md=(DATA.metrics||{})[id];
   if(!md||!md.series||!md.series.length)return '';
   const latest=md.series[md.series.length-1][1];
   const dl=md.base!=null?Math.round((latest-md.base)*10)/10:null;
   return metric(id,metricInfo(id).name,{latest,delta:dl},unit||'',hiBad)}

  function lensDiv(label,col){return `<div class="lens-hd"><span style="color:${col}">${label}</span><div class="lens-line" style="background:${col}22"></div></div>`}

  let heroHtml;
  if(rdy.items&&rdy.items.length){
    const base=rdy.base!=null?T('summary.your_base').replace('{base}',Math.round(rdy.base)):'';
    const rdyC=tier(rdy.value);
    heroHtml=`<div class="hero" style="background:${rdyC[0]};color:${rdyC[1]}">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><div class="t">${T('summary.readiness')}</div>${base?`<div style="font-size:11px;opacity:.6">${base}</div>`:''}</div>
      <div class="h">${rdy.value!=null?rdy.value:'—'} <span style="font-size:14px;font-weight:400;opacity:.7">${rdy.delta!=null?(rdy.delta>=0?T('summary.above_base'):T('summary.below_base')):''}</span></div>
      <div class="rdy-items">${rdy.items.map(it=>{const pos=it.weight>=0;return `<div class="rdy-row"><span class="rdy-name">${it.name}</span><div class="rdy-bar"><div class="rdy-fill" style="background:${pos?'var(--green)':'var(--red)'};${pos?'left:50%':'right:50%'};width:${Math.min(Math.abs(it.weight)*3,45)}%"></div></div><span class="rdy-w" style="color:${pos?'var(--green)':'var(--red)'}">${it.weight>=0?'+':''}${it.weight}</span></div>`}).join('')}</div>
    </div>`;
  } else {
    const heroC=V[vd.level]||V.green;
    const heroLabel=vd.source==='self'?T('summary.self_readiness').replace('{today}',DATA.today):T('summary.readiness_dated').replace('{today}',DATA.today);
    heroHtml=`<div class="hero" style="background:${heroC[0]};color:${heroC[1]}">
      <div class="t">${heroLabel}</div>
      <div class="h">${vd.title}</div>
      <div class="r">${vd.reason}</div></div>`;
  }

  const riskLv=risk.level||'green';
  const riskC=V[riskLv]||V.green;
  const riskEmpty=riskLv==='green'&&(!risk.title||risk.title==='—');
  const riskHtml=`<div class="card" style="border-left:3px solid ${riskC[1]};margin-bottom:8px">
    <div style="font-weight:700;color:${riskC[1]}">${riskEmpty?T('summary.data_collecting'):risk.title||'—'}</div>
    ${risk.drivers&&risk.drivers.length?`<div style="font-size:12.5px;margin-top:4px;opacity:.85">${risk.drivers.join(' · ')}</div>`:''}
  </div>`;

  const sigEntries=Object.entries(sigs);
  let sigsHtml='';
  if(sigEntries.length){
    sigsHtml=`<div class="card" style="margin-bottom:8px;display:flex;flex-direction:column;gap:9px">${sigEntries.map(([id,sg])=>{const cls=sg.cls||'green';const sgC=V[cls]||V.green;const tap=id?`onclick="toggleMetric('${id}')" style="cursor:pointer"`:'';return `<div ${tap}><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>${sg.label}${id?' ›':''} <b>${sg.value!=null?sg.value:'—'}</b></span><span style="color:${sgC[1]}">${sg.base||''}</span></div>${sg.base?`<div class="sig-bar"><div class="sig-fill" style="background:${sgC[1]}22"></div><div class="sig-cur" style="background:${sgC[1]}"></div></div>`:''}</div>`}).join('')}</div>`;
  }

  const fo=form;
  const wser=((DATA.metrics||{}).weight||{}).series||[];
  const wChart=wser.length>1?`<div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--bd)">
      <div style="font-size:10.5px;opacity:.5;margin-bottom:2px">${T('summary.weight_chart')}</div>
      ${metricChartSvg(wser,null,'low_bad',true)}</div>`:'';
  const formHtml=`<div class="card" style="margin-bottom:8px">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin-bottom:8px">${T('summary.form_direction')}</div>
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div><span style="font-weight:700">${fo.vo2max!=null?fo.vo2max:'—'}</span><span style="font-size:11px;opacity:.55;margin-left:4px">VO₂max</span></div>
      <div style="font-size:13px;color:var(--mut)">${fo.status||'—'}</div>
      <div><span style="font-weight:700">${fo.weight!=null?fo.weight:'—'}</span><span style="font-size:11px;opacity:.55;margin-left:4px">${T('summary.kg')}</span></div>
    </div>
    ${wChart}
  </div>`;

  const wt=DATA.watch_tuning;
  let watchHtml='';
  if(wt&&wt.watch){
    const offItems=(wt.items||[]).filter(i=>i.state==='off');
    const unsup=(wt.items||[]).filter(i=>i.state==='unsupported');
    const okCount=(wt.items||[]).filter(i=>i.state==='ok').length;
    watchHtml=`<div class="card" style="margin-bottom:8px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin-bottom:6px">${T('watch.title')}</div>
      <div style="font-size:12.5px;color:var(--mut)">⌚ ${wt.watch}${wt.others&&wt.others.length?' + '+wt.others.join(', '):''} · ${T('watch.ok_count').replace('{ok}',okCount).replace('{total}',(wt.items||[]).length)}</div>
      ${offItems.map(i=>`<div style="margin-top:9px;padding-top:8px;border-top:1px solid var(--bd)">
        <div style="font-weight:600">⚠️ ${T('watch.'+i.id+'.name')}</div>
        <div style="font-size:12.5px;opacity:.85;margin-top:2px">${T('watch.'+i.id+'.gain')}</div>
        <div style="font-size:12px;color:var(--amber);margin-top:3px">${T('watch.'+i.id+'.how')}</div>
      </div>`).join('')}
      ${offItems.length===0?`<div style="font-size:12.5px;color:var(--green);margin-top:6px">${T('watch.all_ok')}</div>`:''}
      ${unsup.length?`<div style="font-size:11px;color:var(--mut);margin-top:8px">${T('watch.unsupported')}: ${unsup.map(i=>T('watch.'+i.id+'.name')).join(', ')}</div>`:''}
    </div>`;
  }

  const mcDays=mc.days||[];
  let mcHtml;
  if(mcDays.length){
    const maxLoad=Math.max(...mcDays.map(d=>d.load||0),1);
    const dayLabels=[T('day.mon'),T('day.tue'),T('day.wed'),T('day.thu'),T('day.fri'),T('day.sat'),T('day.sun')];
    mcHtml=`<div class="card" style="margin-bottom:8px">
      <div style="height:64px;display:flex;align-items:flex-end;gap:5px;margin-bottom:5px">${mcDays.map(d=>{const h=d.load?Math.round(d.load/maxLoad*100):0;const bg=h===0?'var(--bd)':'var(--amber)';return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%"><div style="width:65%;height:${Math.max(h,4)}%;background:${bg};border-radius:3px"></div></div>`}).join('')}</div>
      <div style="display:flex;gap:5px;font-size:10px;opacity:.55;text-align:center">${mcDays.map((d,i)=>`<span style="flex:1">${d.label||dayLabels[i]||''}</span>`).join('')}</div>
      <div style="display:flex;gap:5px;font-size:9.5px;opacity:.4;text-align:center;margin-top:2px">${mcDays.map(d=>`<span style="flex:1">${d.readiness!=null?d.readiness:'—'}</span>`).join('')}</div>
      ${mc.max_streak>=3?`<div style="font-size:12.5px;margin-top:8px;padding-top:8px;border-top:1px solid var(--bd);color:var(--amber)">${T('summary.microcycle_streak')}</div>`:''}
    </div>`;
  } else {
    mcHtml=`<div class="card" style="margin-bottom:8px;color:var(--mut);font-size:13px">${T('summary.microcycle_soon')}</div>`;
  }

  const acwrHtml=`<div class="card" style="margin-bottom:8px">
    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span>${T('summary.acwr_label')} <b>${fmt(m.acwr)}</b></span><span style="color:${m.acwr==null?'var(--mut)':m.acwr>=0.8&&m.acwr<=1.3?'var(--green)':m.acwr>1.3?'var(--red)':'var(--amber)'}">${m.acwr==null?'—':m.acwr>=0.8&&m.acwr<=1.3?T('summary.acwr_in_zone'):m.acwr>1.3?T('summary.acwr_overload'):T('summary.acwr_underload')}</span></div>
    <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--mut)"><span>${T('summary.acute').replace('{v}',fmt(m.acute7))}</span><span>${T('summary.chronic').replace('{v}',fmt(m.chronic28))}</span></div>
    <div style="display:flex;gap:18px;margin-top:9px;font-size:12px"><span>Monotony <b>${fmt(m.monotony)}</b></span><span>Strain <b>${fmt(m.strain)}</b></span></div>
  </div>`;

  const mw=DATA.muscles_week;
  let musclesHtml='';
  if(mw&&window.BODY){
    const idle=(mw.idle||[]).map(g=>`<span class="sp">${T('muscle.'+g)}</span>`).join('');
    musclesHtml=`<div class="card" style="margin-bottom:8px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin-bottom:8px">${T('summary.muscles_title')}</div>
      ${muscleMapHtml(mw)}
      ${idle?`<div style="font-size:12px;margin-top:9px;padding-top:8px;border-top:1px solid var(--bd)"><span style="color:var(--mut)">${T('summary.muscles_idle')}</span> ${idle}</div>`:''}
    </div>`;
  }


  const n30Html=n30.length?`<h2>${T('summary.narrative_30d')}</h2>${n30.map(b=>`<div class="mdsec"><div class="mdh">${b.title}</div><div>${b.body}</div></div>`).join('')}`:'';

  const picker = DATA.is_admin ? `
    <div class="switcher">
      <span>${T('summary.view_as')}</span>
      <select id="asSel"><option value="">${T('summary.view_as_self')}</option></select>
    </div>` : '';

  const adviceHtml=`<div id="advicehost">${adviceCard(DATA.advice)}</div>`;

  app.innerHTML=tabbar('summary')+`
  ${picker}
  <h1>${T('summary.title')}</h1>
  <div class="sub">${T('summary.on_date').replace('{day}',DATA.last_data_day||DATA.range[1]||'—').replace('{hrmax}',DATA.hr_max)}</div>
  ${heroHtml}
  ${adviceHtml}
  <div class="grid">
    ${metric('sleep',T('metric.sleep.name'),m.sleep,T('summary.sleep_note'),false)}
    ${metric('hrv',T('metric.hrv.name'),m.hrv,T('summary.hrv_note'),false)}
    ${metric('rhr',T('metric.rhr.name'),m.rhr,T('summary.rhr_note'),true)}
    ${metric('vo2max',T('metric.vo2max.name'),m.vo2max,T('summary.vo2max_note'),false)}
    ${metricCard('spo2',false,T('metric.spo2.note'))}
    ${metricCard('respiration',true,T('metric.respiration.note'))}
    ${metricCard('sleep_deep',false,T('metric.sleep_deep.note'))}
    ${metricCard('sleep_rem',false,T('metric.sleep_rem.note'))}
  </div>
  <div id="metricDetail" data-open=""></div>
  ${lensDiv(T('summary.lens_body'),'var(--green)')}
  ${riskHtml}
  ${sigsHtml}
  ${formHtml}
  ${watchHtml}
  ${lensDiv(T('summary.lens_load'),'var(--amber)')}
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin:0 0 8px">${T('summary.microcycle_week')}</div>
  ${mcHtml}
  ${acwrHtml}
  ${musclesHtml}
  <h2>${T('summary.cal_title')}</h2>
  <div class="leg">
    <span><span class="sw" style="background:var(--greenb)"></span>${T('summary.leg_ready')}</span>
    <span><span class="sw" style="background:var(--amberb)"></span>${T('summary.leg_mid')}</span>
    <span><span class="sw" style="background:var(--redb)"></span>${T('summary.leg_tired')}</span>
    <span>${T('summary.leg_dot')}</span></div>
  <div class="cal" id="cal"></div>
  <h2>${T('summary.rdy_load_title')}</h2>
  <div class="leg"><span><span class="sw" style="background:#1D9E75;height:3px;border-radius:0"></span>${T('summary.leg_readiness')}</span><span><span class="sw" style="background:#888780"></span>${T('summary.leg_load')}</span></div>
  <div style="position:relative;height:240px"><canvas id="ch"></canvas></div>
  <h2>${T('summary.sports_title')}</h2>
  <div class="card">${DATA.sports.map(s=>`<span class="sp">${s[0]} · ${s[1]}</span>`).join('')}</div>
  ${nutrWeekSection(DATA.nutrition_week)}
  ${n30Html}
  <div id="llmhost_summary"></div>
  ${metricsHelpHtml()}`;

  loadLlm('summary','30d',!!DATA.pro);

  if(DATA.is_admin){
    const sel=document.getElementById('asSel');
    fetch('/api/users',{headers:{'X-Init-Data':INIT}}).then(r=>r.ok?r.json():[]).then(us=>{
      us.forEach(u=>{ const o=document.createElement('option'); o.value=u.tg_id; o.textContent=u.nick||u.tg_id; if(String(u.tg_id)===String(AS)) o.selected=true; sel.appendChild(o); });
    });
    sel.onchange=()=>{ AS = sel.value || null; load(); };
  }

  if(S.length){
    const Scal=S.slice(-31),Sch=S.slice(-30);
    const cal=document.getElementById('cal');
    [T('day.mon'),T('day.tue'),T('day.wed'),T('day.thu'),T('day.fri'),T('day.sat'),T('day.sun')].forEach(w=>{const h=document.createElement('div');h.className='hd';h.textContent=w;cal.appendChild(h)});
    const pad=(new Date(Scal[0][0]).getDay()+6)%7;
    for(let i=0;i<pad;i++)cal.appendChild(document.createElement('div'));
    Scal.forEach(r=>{const[bg,fg]=tier(r[1]);const c=document.createElement('div');c.className='cell';
     c.title=T('summary.cal_tooltip').replace('{day}',r[0]).replace('{rdy}',r[1]).replace('{sleep}',r[2])+(r[4]?T('summary.cal_tooltip_load').replace('{load}',r[3]):T('summary.cal_tooltip_rest'));
     c.style.background=bg;c.style.color=fg;
     c.innerHTML=`<span class="dd">${+r[0].slice(8)}</span>`+(r[4]?'<span class="bb"></span>':'');cal.appendChild(c)});

    new Chart(document.getElementById('ch'),{data:{labels:Sch.map(r=>r[0].slice(5)),datasets:[
     {type:'bar',data:Sch.map(r=>r[3]),backgroundColor:'#888780',yAxisID:'y1',order:2},
     {type:'line',data:Sch.map(r=>r[1]),borderColor:'#1D9E75',backgroundColor:'#1D9E75',tension:.3,pointRadius:1.5,yAxisID:'y',order:1}]},
     options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
     scales:{y:{position:'left',min:0,max:100,ticks:{font:{size:10}}},
     y1:{position:'right',min:0,grid:{drawOnChartArea:false},ticks:{font:{size:10}}},
     x:{ticks:{font:{size:9},maxRotation:0,autoSkip:true,maxTicksLimit:9}}}}});
  }
}

function wResult(w){return [w.scaling,w.load_kg?`${w.load_kg} ${T('summary.kg')}`:null,w.score?w.score:null,w.rpe?`RPE ${w.rpe}`:null].filter(Boolean).join(' · ')}
function fmtScore(sc){
  const esc=t=>t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  let out=[],first=true;
  for(const raw of (sc||'').split('\n')){
    if(!raw.trim())continue;
    const t=raw.trim(), title=!/^\s/.test(raw)&&t.endsWith(':');
    out.push(title
      ? `<div style="font-weight:600;margin:${first?0:10}px 0 2px">${esc(t)}</div>`
      : `<div style="opacity:.9;padding-left:6px">${esc(t)}</div>`);
    first=false;
  }
  return `<div class="wodresult" style="font-size:13px;line-height:1.5">${out.join('')}</div>`;
}

function renderWorkoutsList(list){
  LAST_LIST=list;
  const now=new Date();
  const thisMonth=list.filter(w=>w.day&&w.day.slice(0,7)===(now.getFullYear()+'-'+(String(now.getMonth()+1).padStart(2,'0'))));
  const sportCounts={};
  list.forEach(w=>{if(w.sport)sportCounts[w.sport]=(sportCounts[w.sport]||0)+1});
  const prCount=list.filter(w=>w.pr).length;
  const sports=Object.keys(sportCounts);
  const statsRow=`<div class="wstats"><span>${T('workouts.this_month').replace('{n}',thisMonth.length)}</span>${sports.map(s=>`<span>${s} ${sportCounts[s]}</span>`).join('')}${prCount?`<span>PR ${prCount}</span>`:''}</div>`;
  const filterAll=T('workouts.filter_all');
  let activeFilter=filterAll;
  function renderRows(filtered){
    return filtered.map(w=>{const[bg]=tier(w.readiness);
     const multi=w.score&&w.score.includes('\n');
     const short=[w.scaling,w.load_kg?`${w.load_kg} ${T('summary.kg')}`:null,(!multi&&w.score)?w.score:null,w.rpe?`RPE ${w.rpe}`:null].filter(Boolean).join(' · ');
     return `<div class="wrow" data-day="${w.day}">
       <div class="wdot" style="background:${bg}"></div>
       <div class="wmain"><div class="wt">${w.wod_name||w.sport}</div>
         <div class="wsub">${w.day} · ${w.sport}${short?' · '+short:''}</div></div>
       <div class="wchev">›</div></div>`}).join('');
  }
  function renderChips(active){
    const chips=[filterAll,...sports];
    return `<div class="wfilters">${chips.map(s=>`<span class="wchip${active===s?' wchip-on':''}" data-sport="${s}">${s}</span>`).join('')}</div>`;
  }
  function render(active){
    const filtered=active===filterAll?list:list.filter(w=>w.sport===active);
    const inner=renderChips(active)+renderRows(filtered);
    document.getElementById('wlist').innerHTML=inner;
    document.querySelectorAll('.wchip').forEach(el=>el.onclick=()=>render(el.dataset.sport));
    app.querySelectorAll('.wrow').forEach(el=>el.onclick=()=>openDetail(el.dataset.day));
  }
  app.innerHTML=tabbar('workouts')+`<h1>${T('workouts.title')}</h1>${statsRow}<div id="wlist"></div>`;
  render(activeFilter);
}

async function openDetail(day){
  app.innerHTML=`<div class="loading">${T('common.loading')}</div>`;
  try{ renderWorkoutDetail(await api('/api/workout/'+day)); }
  catch(e){ app.innerHTML=`<div class="loading">${T('common.error_generic').replace('{msg}',e.message)}</div>`; }
}

function histLine(s,prior){
  if(!prior||prior.length===0) return `<div class="hist">${T('workout.first_time')}</div>`;
  const last=prior[prior.length-1];
  const bits=[T('workout.last_time').replace('{day}',last.day)];
  if(s.load_kg!=null&&last.load_kg!=null){const d=Math.round((s.load_kg-last.load_kg)*10)/10;bits.push(T('workout.weight_change').replace('{from}',last.load_kg).replace('{to}',s.load_kg).replace('{delta}',(d>=0?'+':'')+d))}
  const cs=scoreSec(s.score),ls=scoreSec(last.score);
  if(cs!=null&&ls!=null){const d=cs-ls;bits.push(T('workout.time_change').replace('{from}',last.score).replace('{to}',s.score).replace('{delta}',(d>=0?'+':'')+d))}
  return `<div class="hist">${bits.join(' · ')} · ${T('workout.total_such').replace('{n}',prior.length+1)}</div>`;
}

function zonesFmt(secs){if(secs==null||secs<0)return '—';const m=Math.floor(secs/60),s=secs%60;return m+':'+(s<10?'0':'')+s}
function teGauge(label,val){
  if(val==null)return '';
  const pct=Math.min(Math.round(val/5*100),100);
  return `<div style="margin-top:9px"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px"><span>${label}</span><span style="font-size:16px;font-weight:600">${Math.round(val*10)/10}</span></div>
   <div style="position:relative;display:flex;gap:2px;height:8px">
     <div style="flex:1;background:var(--mut);opacity:.45;border-radius:4px 0 0 4px"></div><div style="flex:1;background:var(--mut);opacity:.7"></div><div style="flex:1;background:#378ADD"></div><div style="flex:1;background:#4aaa99"></div><div style="flex:1;background:var(--amber)"></div><div style="flex:.5;background:var(--red);border-radius:0 4px 4px 0"></div>
     <div style="position:absolute;left:${pct}%;top:-3px;width:14px;height:14px;border-radius:50%;background:#378ADD;border:2px solid var(--card);transform:translateX(-50%)"></div>
   </div></div>`;
}
function hrLineSvg(series,hrMax){
  if(!series||series.length<2)return '';
  const hm=hrMax||184,x0=30,x1=336,y0=18,y1=128;
  const maxT=series[series.length-1][0]||1;
  const lo=50,hi=Math.max(hm,...series.map(p=>p[1]))+5;
  const X=t=>x0+(t/maxT)*(x1-x0),Y=hr=>y1-((hr-lo)/(hi-lo))*(y1-y0);
  const zc=['var(--mut)','#378ADD','#4aaa99','var(--amber)','var(--red)'];
  const zn=hr=>hr<.6*hm?0:hr<.7*hm?1:hr<.8*hm?2:hr<.9*hm?3:4;
  let segs='';
  for(let i=0;i<series.length-1;i++){const a=series[i],b=series[i+1];
    segs+=`<line x1="${X(a[0]).toFixed(1)}" y1="${Y(a[1]).toFixed(1)}" x2="${X(b[0]).toFixed(1)}" y2="${Y(b[1]).toFixed(1)}" stroke="${zc[zn(a[1])]}" stroke-width="1.8"/>`}
  const y120=Y(120).toFixed(1),mn=Math.round(maxT/60),tlab=mn>=60?Math.floor(mn/60)+':'+String(mn%60).padStart(2,'0'):mn+' '+T('common.min');
  return `<svg viewBox="0 0 360 150" style="width:100%"><line x1="${x0}" y1="${y120}" x2="${x1}" y2="${y120}" stroke="var(--tx)" stroke-width="1" opacity=".35"/><text x="${x1}" y="${(+y120-3).toFixed(1)}" font-size="9" fill="var(--mut)" text-anchor="end">120</text>${segs}<text x="${x0}" y="146" font-size="9" fill="var(--mut)">0:00</text><text x="${x1}" y="146" font-size="9" fill="var(--mut)" text-anchor="end">${tlab}</text></svg>`;
}
const MUSCLE_SLUGS={deltoids:'shoulders',trapezius:'traps',chest:'chest',biceps:'biceps',triceps:'triceps',forearm:'forearms',abs:'abs',obliques:'obliques','upper-back':'upper_back','lower-back':'lower_back',gluteal:'glutes',quadriceps:'quads',hamstring:'hamstrings',adductors:'adductors',calves:'calves'};
const MUSCLE_SEC='#f5b83d';
function muscleBodySvg(parts,view,m){
  const prim=new Set(m.primary||[]),sec=new Set(m.secondary||[]),inten=m.intensity||{};
  const shapes=parts.map(pt=>{
    const g=MUSCLE_SLUGS[pt.s];
    let fill='var(--bd)',op=1;
    if(g&&(prim.has(g)||sec.has(g))){fill=prim.has(g)?'var(--red)':MUSCLE_SEC;op=(0.35+0.65*(inten[g]||0)).toFixed(2)}
    return pt.p.map(d=>`<path d="${d}" fill="${fill}" opacity="${op}"/>`).join('');
  }).join('');
  return `<svg viewBox="${view}" style="height:195px">${shapes}</svg>`;
}
function muscleMapHtml(m){
  if(!m||!window.BODY)return '';
  return `<div style="display:flex;justify-content:center;gap:22px">${muscleBodySvg(BODY.front,BODY.viewFront,m)}${muscleBodySvg(BODY.back,BODY.viewBack,m)}</div>
  <div class="leg" style="justify-content:center;margin:8px 0 0">
    <span><span class="sw" style="background:var(--red)"></span>${T('muscles.legend_primary')}</span>
    <span><span class="sw" style="background:${MUSCLE_SEC}"></span>${T('muscles.legend_secondary')}</span>
    <span><span class="sw" style="background:var(--bd)"></span>${T('muscles.legend_idle')}</span></div>`;
}
function renderWorkoutDetail(rep){
  const c=rep.condition;
  const heroC=c?V[c.verdict.level]:['var(--card)','var(--mut)'];
  let html=`<div class="back" id="back">${T('workout.back')}</div><h1>${rep.day}</h1>`;
  if(c){
    html+=`<div class="hero" style="background:${heroC[0]};color:${heroC[1]}">
      <div class="t">${T('workout.approach')} · readiness ${c.readiness==null?'—':c.readiness}${c.hrv_delta!=null?` · HRV ${delta(c.hrv_delta)}`:''}${c.sleep_delta!=null?` · ${T('metric.sleep.name')} ${delta(c.sleep_delta)}${T('workout.sleep_h')}`:''}</div>
      <div class="h">${c.verdict.title}</div>
      <div class="r">${c.verdict.reason}</div></div>`;
  }
  rep.sessions.forEach(s=>{
    const stats=[s.duration_min?`${fmt(s.duration_min)} ${T('common.min')}`:null,s.avg_hr?T('workout.stat_hr').replace('{avg}',s.avg_hr).replace('{max}',s.max_hr||'—'):null,s.calories?T('workout.stat_cal').replace('{v}',s.calories):null,T('workout.stat_trimp').replace('{v}',rep.trimp)].filter(Boolean).join(' · ');
    const chip=[s.scaling,s.load_kg?`${s.load_kg} ${T('summary.kg')}`:null,s.rpe?`RPE ${s.rpe}`:null].filter(Boolean).join(' · ');
    const multi=s.score&&s.score.includes('\n');
    const resBlock=multi
      ? (chip?`<div class="reschip">${chip}</div>`:'')+fmtScore(s.score)
      : (()=>{const one=[chip,s.score].filter(Boolean).join(' · ');return one?`<div class="reschip">${one}</div>`:`<div class="hist">${T('workout.result_missing')}</div>`})();
    const ex=s.extra||{};
    let block='';
    if(s.distance_km!=null||s.avg_pace_s_per_km!=null||s.avg_power_w!=null||s.elevation_gain_m!=null){
      const paceFmt=p=>{const m=Math.floor(p/60),sec=Math.round(p%60);return m+':'+(sec<10?'0':'')+sec};
      const et=[];
      if(s.distance_km!=null)et.push({v:`${s.distance_km} ${T('workout.km')}`,l:T('workout.distance')});
      if(s.avg_pace_s_per_km!=null)et.push({v:`${paceFmt(s.avg_pace_s_per_km)} ${T('workout.per_km')}`,l:T('workout.pace')});
      if(s.avg_power_w!=null)et.push({v:`${s.avg_power_w} ${T('workout.watt')}`,l:T('workout.power')});
      if(s.elevation_gain_m!=null)et.push({v:`${s.elevation_gain_m} ${T('workout.m')}`,l:T('workout.elevation')});
      block+=`<div class="det-sec"><div class="det-hd">${T('workout.endurance_title')}</div>
        <div class="det-tiles">${et.map(t=>`<div class="det-tile"><div class="det-tile-v">${t.v}</div><div class="det-tile-l">${t.l}</div></div>`).join('')}</div></div>`;
    }
    if(ex.primary_benefit||ex.te_aerobic!=null||ex.te_anaerobic!=null){
      const teAer=ex.te_aerobic!=null?ex.te_aerobic:null;
      const teAna=ex.te_anaerobic!=null?ex.te_anaerobic:null;
      const load=ex.exercise_load!=null?T('workout.te_load').replace('{v}',ex.exercise_load):'';
      block+=`<div class="det-sec"><div class="det-hd">${T('workout.te_title')}</div>
        <div class="det-te">
          ${ex.primary_benefit?`<div class="te-title">${ex.primary_benefit}</div><div class="wsub" style="margin:1px 0 8px">${T('workout.te_primary_benefit')}${load}</div>`:''}
          ${teGauge(T('workout.te_aerobic'),teAer)}${teGauge(T('workout.te_anaerobic'),teAna)}
        </div></div>`;
    }
    if(s.hr_series&&s.hr_series.length>1){
      block+=`<div class="det-sec"><div class="det-hd">${T('workout.hr_title')}</div>
        <div style="background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:8px 6px 4px">${hrLineSvg(s.hr_series,rep.hr_max||s.max_hr||184)}
        <div style="display:flex;gap:9px;justify-content:center;font-size:10.5px;opacity:.75;margin-top:2px">${['Z1','Z2','Z3','Z4','Z5'].map((z,i)=>`<span><span style="display:inline-block;width:10px;height:3px;background:${['var(--mut)','#378ADD','#4aaa99','var(--amber)','var(--red)'][i]};vertical-align:middle"></span> ${z}</span>`).join('')}</div></div></div>`;
    }
    if(s.zones&&s.zones.length===5){
      const zc=['var(--mut)','#4aaa99','#b8b84a','var(--amber)','var(--red)'];
      const zl=['Z1','Z2','Z3','Z4','Z5'];
      const total=s.zones.reduce((a,b)=>a+b,0)||1;
      block+=`<div class="det-sec"><div class="det-hd">${T('workout.zones_title')}</div>
        <div style="display:flex;flex-direction:column;gap:5px">${s.zones.map((v,i)=>{const pct=Math.round(v/total*100);return `<div style="display:flex;align-items:center;gap:8px"><span style="width:22px;font-size:12px;opacity:.8">${zl[i]}</span><div style="flex:1;background:var(--bd);border-radius:4px;height:11px"><div style="width:${pct}%;height:100%;background:${zc[i]};border-radius:4px;min-width:${v?2:0}px"></div></div><span style="width:68px;text-align:right;font-size:12px;opacity:.8">${zonesFmt(v)} · ${pct}%</span></div>`}).join('')}
        </div></div>`;
    }
    const calTiles=[];
    if(ex.active_cal!=null)calTiles.push({v:ex.active_cal,l:T('workout.tile_active_cal')});
    if(ex.resting_cal!=null)calTiles.push({v:ex.resting_cal,l:T('workout.tile_resting_cal')});
    if(ex.active_cal!=null&&ex.resting_cal!=null)calTiles.push({v:ex.active_cal+ex.resting_cal,l:T('workout.tile_total_cal')});
    if(ex.sweat_loss_ml!=null)calTiles.push({v:ex.sweat_loss_ml,l:T('workout.tile_sweat')});
    if(ex.intensity_min!=null){const im=ex.intensity_min;const val=Array.isArray(im)?`${im[0]||0}${T('workout.intensity_mod')}${im[1]||0}${T('workout.intensity_int')}`:(im&&typeof im==='object'?`${im.moderate||0} + ${im.vigorous||0}`:im);calTiles.push({v:val,l:T('workout.tile_intensity')})}
    if(ex.recovery_h!=null)calTiles.push({v:ex.recovery_h+T('workout.tile_recovery_h'),l:T('workout.tile_recovery'),hi:true});
    if(calTiles.length){
      block+=`<div class="det-sec"><div class="det-hd">${T('workout.energy_title')}</div>
        <div class="det-tiles">${calTiles.map(t=>`<div class="det-tile${t.hi?' det-tile-hi':''}""><div class="det-tile-v">${t.v}</div><div class="det-tile-l">${t.l}</div></div>`).join('')}</div></div>`;
    }
    if(ex.respiration_avg!=null||ex.respiration_max!=null){
      block+=`<div class="det-sec"><div class="det-hd">${T('workout.resp_title')}</div>
        <div style="font-size:13px;display:flex;gap:14px">${ex.respiration_avg!=null?`<span>${T('workout.resp_avg')} <b>${ex.respiration_avg}</b></span>`:''}${ex.respiration_max!=null?`<span>${T('workout.resp_max')} <b>${ex.respiration_max}</b></span>`:''}</div></div>`;
    }
    if(s.narrative&&s.narrative.length){
      const kindColor={risk:'var(--red)',advice:'#6f9bd9',verdict:'var(--green)',section:'#6f9bd9',alert:'var(--red)',warn:'var(--amber)',info:'#6f9bd9',ok:'var(--green)'};
      block+=`<div class="det-sec"><div class="det-hd">${T('workout.narrative_title')}</div>
        ${s.narrative.map(n=>{const col=kindColor[n.kind]||'var(--mut)';return `<div class="narr-card" style="border-left-color:${col};margin-bottom:7px"><div class="narr-title" style="color:${col}">${n.title}</div><div class="narr-body">${n.body}</div></div>`}).join('')}</div>`;
    }
    html+=`<div class="card">
      <div class="wt">${s.wod_name||s.sport}</div>
      <div class="wsub" style="margin:4px 0 9px">${stats}</div>
      ${resBlock}
      ${block}
      ${s.wod_name?histLine(s,rep.history[s.wod_name]):''}
    </div>`;
  });
  if(rep.muscles&&window.BODY){
    html+=`<div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin:0 0 8px">${T('workout.muscles_title')}</div>
    <div class="card" style="margin-bottom:8px">${muscleMapHtml(rep.muscles)}</div>`;
  }
  html+=`<div id="claudehost_workout"></div>`;
  html+=`<div id="llmhost_workout"></div>`;
  app.innerHTML=html;
  loadClaude(rep.day,!!rep.pro,'workout');
  loadLlm('workout',rep.day,!!rep.pro);
  document.getElementById('back').onclick=()=>{ if(LAST_LIST)renderWorkoutsList(LAST_LIST); else go('workouts'); };
}

function renderCompetitions(data){
  if(data.starts===0){
    app.innerHTML=tabbar('competitions')+`<h1>${T('comp.title')}</h1><div class="sub">${T('comp.none')}</div>`;
    return;
  }
  const rows=data.totals||[];
  const radars=data.radars||[];
  const bw=data.best_worst||{};
  const nar=data.narrative||[];
  const kindColor={risk:'var(--red)',advice:'#6f9bd9',verdict:'var(--green)',section:'#6f9bd9',alert:'var(--red)',warn:'var(--amber)',info:'#6f9bd9',ok:'var(--green)'};

  const radarHtml=radars.length?`<h2>${T('comp.compare_title')}</h2>${_radarOverlaySvg(radars)}`:'';

  const bwBest=(bw.best||[]).map(s=>`<div style="display:flex;justify-content:space-between;padding:3px 0"><span>${s.name}</span><span style="color:#7bbf6a">${s.result&&s.result.place!=null?s.result.place:'—'}/${s.field}</span></div>`).join('');
  const bwWorst=(bw.worst||[]).map(s=>`<div style="display:flex;justify-content:space-between;padding:3px 0"><span>${s.name}</span><span style="color:#d76a5f">${s.result&&s.result.place!=null?s.result.place:'—'}/${s.field}</span></div>`).join('');
  const bwHtml=(bwBest||bwWorst)?`<h2>${T('comp.career_wods')}</h2>
    ${bwBest?`<div style="background:#15211d;border-radius:12px;padding:11px 13px;margin-bottom:8px"><div style="color:#7bbf6a;font-size:11px;font-weight:700;margin-bottom:6px">${T('comp.best')}</div>${bwBest}</div>`:''}
    ${bwWorst?`<div style="background:#221715;border-radius:12px;padding:11px 13px"><div style="color:#d76a5f;font-size:11px;font-weight:700;margin-bottom:6px">${T('comp.worst')}</div>${bwWorst}</div>`:''}
  `:'';

  const narHtml=nar.length?`<h2>${T('comp.conclusions')}</h2>${nar.map(b=>{const col=kindColor[b.kind]||'#6f9bd9';return `<div class="narr-card" style="border-left-color:${col};margin-bottom:8px"><div class="narr-title" style="color:${col}">${b.title}</div><div class="narr-body">${b.body}</div></div>`}).join('')}`:'';

  app.innerHTML=tabbar('competitions')+`
  <h1>${T('comp.title')}</h1>
  <div class="grid">
    <div class="mc"><div class="l">${T('comp.starts')}</div><div class="v">${data.starts}</div></div>
    <div class="mc"><div class="l">${T('comp.best_place')}</div><div class="v">${data.best_place==null?'—':data.best_place}</div></div>
  </div>
  <h2>${T('comp.place_by_start')}</h2>
  <div style="position:relative;height:220px"><canvas id="chc"></canvas></div>
  ${radarHtml}
  ${bwHtml}
  ${narHtml}
  <h2>${T('comp.starts_title')}</h2>
  ${rows.map(r=>`<div class="wrow" style="cursor:pointer" onclick="openCompetition(${r.id})">
    <div class="wmain">
      <div class="wt">${r.name}</div>
      <div class="wsub">${r.date} · ${T('comp.place_of_field').replace('{place}',r.final_place).replace('{field}',r.field)}</div>
    </div>
    <div class="wchev">›</div>
  </div>`).join('')}
  <div id="llmhost_competitions"></div>`;

  loadLlm('competitions','total',!!data.pro);

  new Chart(document.getElementById('chc'),{
    type:'line',
    data:{
      labels:rows.map(r=>r.date),
      datasets:[{
        data:rows.map(r=>r.final_place),
        borderColor:'#1D9E75',
        backgroundColor:'rgba(29,158,117,.15)',
        tension:.3,
        pointRadius:5,
        pointBackgroundColor:'#1D9E75'
      }]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        y:{reverse:true,min:1,ticks:{stepSize:1,font:{size:10}}},
        x:{ticks:{font:{size:11}}}
      }
    }
  });
}

const AXES_KEYS=["Движок","Сила","Гимнастика","Над головой","Спринт","Хват/тяга"];
const AXES_T_KEYS=["axis.engine","axis.strength","axis.gymnastics","axis.overhead","axis.sprint","axis.grip_pull"];
function axisLabel(i){ return T(AXES_T_KEYS[i]); }
function _radarOverlaySvg(radars){
  const axes=AXES_KEYS;
  const cx=110,cy=110,R=80,n=axes.length;
  const ang=i=>(-90+i*(360/n))*Math.PI/180;
  const pt=(i,r)=>[cx+r*Math.cos(ang(i)),cy+r*Math.sin(ang(i))];
  const poly=pts=>pts.map(p=>p.join(',')).join(' ');
  const gridPts=axes.map((_,i)=>pt(i,R));
  const gridInner=axes.map((_,i)=>pt(i,R*0.5));
  const labelPts=axes.map((_,i)=>pt(i,R+18));
  const labelAnchor=i=>{const x=labelPts[i][0];return x<cx-4?'end':x>cx+4?'start':'middle'};
  const palette=[
    {stroke:'#1D9E75',fill:'rgba(29,158,117,.18)',dash:'',width:'2.2'},
    {stroke:'#EF9F27',fill:'rgba(239,159,39,.12)',dash:'4 3',width:'1.8'},
    {stroke:'#378ADD',fill:'rgba(55,138,221,.12)',dash:'2 3',width:'1.8'},
  ];
  const polygons=radars.map((r,ri)=>{
    const c=palette[ri]||palette[palette.length-1];
    const dataPts=axes.map((a,i)=>pt(i,(r.grades[a]||0)/9*R));
    const dashAttr=c.dash?`stroke-dasharray="${c.dash}"`:'';
    return `<polygon points="${poly(dataPts)}" fill="${c.fill}" stroke="${c.stroke}" stroke-width="${c.width}" ${dashAttr}/>`;
  }).join('');
  const legend=radars.map((r,ri)=>{
    const c=palette[ri]||palette[palette.length-1];
    const lineStyle=c.dash?`border-top:2px dashed ${c.stroke}`:`border-top:2.2px solid ${c.stroke}`;
    const label=r.name+(r.date?` · ${r.date.slice(5)}`:'');
    return `<div style="display:flex;align-items:center;gap:6px"><span style="width:16px;height:0;${lineStyle}"></span><span style="font-size:11px;opacity:.8">${label}</span></div>`;
  }).join('');
  return `<div style="background:#15181f;border-radius:12px;padding:14px 8px 10px">
    <svg viewBox="-40 0 300 220" style="width:100%;max-width:300px;display:block;margin:0 auto">
      <polygon points="${poly(gridPts)}" fill="none" stroke="#262b35" stroke-width="1"/>
      <polygon points="${poly(gridInner)}" fill="none" stroke="#262b35" stroke-width="1"/>
      ${axes.map((_,i)=>`<line x1="${cx}" y1="${cy}" x2="${gridPts[i][0]}" y2="${gridPts[i][1]}" stroke="#262b35" stroke-width="1"/>`).join('')}
      ${polygons}
      ${axes.map((a,i)=>`<text x="${labelPts[i][0]}" y="${labelPts[i][1]+4}" font-size="9.5" fill="#9aa3b2" text-anchor="${labelAnchor(i)}">${axisLabel(i)}</text>`).join('')}
    </svg>
    <div style="display:flex;flex-wrap:wrap;gap:10px 16px;justify-content:center;margin-top:8px">${legend}</div>
  </div>`;
}

function _radarSvg(radar){
  const axes=AXES_KEYS;
  const cx=110,cy=110,R=80,n=axes.length;
  const ang=i=>(-90+i*(360/n))*Math.PI/180;
  const pt=(i,r)=>[cx+r*Math.cos(ang(i)),cy+r*Math.sin(ang(i))];
  const poly=pts=>pts.map(p=>p.join(',')).join(' ');
  const gridPts=axes.map((_,i)=>pt(i,R));
  const dataPts=axes.map((a,i)=>pt(i,(radar[a]||0)/9*R));
  const labelPts=axes.map((_,i)=>pt(i,R+18));
  const labelAnchor=i=>{const x=labelPts[i][0];return x<cx-4?'end':x>cx+4?'start':'middle'};
  return `<svg viewBox="-40 0 300 220" style="width:100%;max-width:280px;display:block;margin:0 auto">
    <polygon points="${poly(gridPts)}" fill="none" stroke="#262b35" stroke-width="1"/>
    ${axes.map((_,i)=>`<line x1="${cx}" y1="${cy}" x2="${gridPts[i][0]}" y2="${gridPts[i][1]}" stroke="#262b35" stroke-width="1"/>`).join('')}
    <polygon points="${poly(dataPts)}" fill="rgba(74,170,153,.24)" stroke="#4aaa99" stroke-width="2.2"/>
    ${axes.map((a,i)=>`<text x="${labelPts[i][0]}" y="${labelPts[i][1]+4}" font-size="9.5" fill="#9aa3b2" text-anchor="${labelAnchor(i)}">${axisLabel(i)}</text>`).join('')}
  </svg>`;
}

function renderCompetition(rep){
  const dyn=rep.dynamics||[];
  const tbl=rep.table||[];
  const nar=rep.narrative||[];
  const sc=rep.scenario||{};
  const pctCol=p=>p>=66?'var(--green)':p>=40?'var(--amber)':'var(--red)';
  let html=`<div class="back" id="cback">${T('compd.back')}</div>
  <h1>${rep.name}</h1>
  <div class="sub">${rep.city} · ${rep.date} · ${T('compd.division').replace('{v}',rep.division)}</div>
  <div class="grid" style="margin-top:10px">
    <div class="mc"><div class="l">${T('compd.place')}</div><div class="v">${rep.final_place==null?'—':rep.final_place}<span style="font-size:13px;opacity:.5">/${rep.field}</span></div></div>
    <div class="mc"><div class="l">${T('compd.points')}</div><div class="v">${rep.total_points==null?'—':rep.total_points}</div></div>
  </div>
  <h2>${T('compd.dynamics')}</h2>
  <div style="position:relative;height:200px"><canvas id="chdyn"></canvas></div>
  <h2>${T('compd.profile')}</h2>
  <div class="card">${_radarSvg(rep.radar||{})}</div>
  <h2>${T('compd.stages')}</h2>
  <div style="font-size:13px">
    <div style="display:flex;padding:7px 8px;background:var(--card);border-radius:8px 8px 0 0;opacity:.55;font-size:11px"><span style="flex:2">${T('compd.wod_col')}</span><span style="width:38px;text-align:center">${T('compd.place_col')}</span><span style="width:48px;text-align:right">${T('compd.pct_col')}</span></div>
    ${tbl.map((s,i)=>`<div style="display:flex;padding:8px;border-left:3px solid ${pctCol(s.percentile)};${i%2?'background:rgba(255,255,255,.02)':''}${i===tbl.length-1?';border-radius:0 0 8px 8px':''}">
      <span style="flex:2">${s.name}</span>
      <span style="width:38px;text-align:center">${s.place==null?'—':s.place}</span>
      <span style="width:48px;text-align:right;color:${pctCol(s.percentile)}">${s.percentile}%</span>
    </div>`).join('')}
  </div>
  <h2>${T('compd.narrative')}</h2>
  ${nar.map(b=>`<div class="card" style="margin-bottom:8px"><div style="font-weight:700;margin-bottom:5px">${b.title}</div><div style="font-size:13px">${b.body}</div></div>`).join('')}
  ${sc.gain>0?`<h2>${T('compd.cost_title')}</h2>
  <div class="card" style="border-left:3px solid #6f9bd9">${T('compd.cost_text').replace('{gain}',sc.gain).replace('{place}',sc.target_place)}</div>`:''}`;

  app.innerHTML=html;
  document.getElementById('cback').onclick=()=>go('competitions');

  if(dyn.length){
    new Chart(document.getElementById('chdyn'),{
      type:'line',
      data:{
        labels:dyn.map(d=>`${T('compd.round_prefix')}${d.idx}`),
        datasets:[{
          data:dyn.map(d=>d.place),
          borderColor:'#1D9E75',
          backgroundColor:'rgba(29,158,117,.15)',
          tension:.3,
          pointRadius:5,
          pointBackgroundColor:'#1D9E75'
        }]
      },
      options:{
        responsive:true,
        maintainAspectRatio:false,
        plugins:{legend:{display:false}},
        scales:{
          y:{reverse:true,min:1,ticks:{stepSize:1,font:{size:10}}},
          x:{ticks:{font:{size:11}}}
        }
      }
    });
  }
}

async function openCompetition(id){
  history.replaceState(null,'',`?view=competition&id=${id}`);
  app.innerHTML=`<div class="loading">${T('common.loading')}</div>`;
  try{ renderCompetition(await api('/api/competition/'+id)); }
  catch(e){ app.innerHTML=`<div class="loading">${T('common.error_generic').replace('{msg}',e.message)}</div>`; }
}

function tierBar(idx){
  let s='';
  for(let i=0;i<5;i++) s+=`<span class="seg${(idx!=null&&i<=idx)?' on':''}"></span>`;
  return `<div class="tierbar">${s}</div>`;
}
function discCard(d){
  if(!d.has_data){
    return `<div class="disc" onclick="Telegram.WebApp.close&&Telegram.WebApp.close()">
      <div class="nm"><b>${d.name}</b> <span class="mut">${T('goals.no_data')}</span></div>
      <span class="pill none">${T('goals.record_cta')}</span></div>`;
  }
  const val = d.unit==='kg' ? T('goals.kg_1rm').replace('{v}',Math.round(d.value))
            : d.unit==='time' ? zonesFmt(d.value) : T('goals.rounds').replace('{v}',d.value);
  return `<div class="disc">
    <div class="nm"><b>${d.name}</b> <span class="mut">· ${val}</span>${tierBar(d.idx)}</div>
    <div style="text-align:right">${d.level!=null?`<span class="pill">${d.level}</span>`:''}
      ${d.distance_text?`<div class="mut" style="margin-top:3px">${d.distance_text}</div>`:''}</div>
  </div>`;
}
function goalCard(g){
  const p=g.progress||{};
  const pct=p.pct!=null?p.pct:(p.done?100:0);
  const right=p.done?T('goals.done'):(p.text||'');
  return `<div class="goal"><div class="gtop"><span>${g.title}</span><span class="mut">${right}</span></div>
    <div class="bar"><i style="width:${Math.min(pct,100)}%"></i></div></div>`;
}
function enterPm(bot){
  const url='https://t.me/'+(bot||'example_bot')+'?start=pm';
  if(window.Telegram&&Telegram.WebApp&&Telegram.WebApp.openTelegramLink) Telegram.WebApp.openTelegramLink(url);
  else location.href=url;
}

function renderGoals(d){
  const ov=d.overall||{};
  const head=ov.level
    ?`<div class="ovr"><div class="ring" style="--p:${Math.round((ov.progress||0)*100)}"><div>${ov.level}</div></div>
        <div><div><b>${ov.level}</b> ${T('goals.level_suffix')}</div>
        <div class="bar" style="margin:5px 0 4px"><i style="width:${Math.round((ov.progress||0)*100)}%"></i></div>
        <div class="mut">${T('goals.assessed').replace('{a}',ov.assessed).replace('{t}',ov.total)}</div></div></div>`
    :`<div class="ovr"><div class="mut">${T('goals.assessed_prompt').replace('{a}',ov.assessed).replace('{t}',ov.total)}</div></div>`;
  const goals=(d.goals&&d.goals.length)
    ?d.goals.map(goalCard).join('')
    :`<div class="mut" style="padding:4px 2px">${T('goals.none')}</div>`;
  const lifts=(d.lifts||[]).map(discCard).join('');
  const bms=(d.benchmarks||[]).map(discCard).join('');
  app.innerHTML=tabbar('goals')+`<h1>${T('goals.title')}</h1>
    ${head}
    <div class="sec">${T('goals.my_goals')}</div>${goals}
    <div class="add" onclick="Telegram.WebApp.close&&Telegram.WebApp.close()">${T('goals.add_cta')}</div>
    <div class="add" onclick="enterPm('${d.bot_username||'example_bot'}')">${T('goals.enter_pm')}</div>
    <div class="sec">${T('goals.lifts')}</div>${lifts}
    <div class="sec">${T('goals.benchmarks')}</div>${bms}
    <div class="foot">${T('goals.source_note')}</div>`;
}

function renderLeaderboard(data){
  if(data.no_gym){ app.innerHTML=tabbar('leaderboard')+`<h1>${T('lb.title')}</h1><div class="sub">${T('lb.no_gym')}</div>`; return; }
  const cur=new URLSearchParams(location.search).get('metric')||'overall';
  const opts=`<option value="overall"${cur==='overall'?' selected':''}>${T('lb.overall')}</option>`+
    (data.disciplines||[]).map(d=>`<option value="${d.id}"${cur===d.id?' selected':''}>${d.name}</option>`).join('');
  const rows=(data.rows||[]).map(r=>`
    <div class="lbrow${r.is_me?' me':''}"><span class="pl">${r.place}</span>
      <span class="nk">${r.nick||('#'+r.tg_id)}</span>
      <span class="vl">${r.value}${r.tier?` · ${r.tier}`:''}</span></div>`).join('')
    || `<div class="sub">${T('lb.no_data')}</div>`;
  app.innerHTML=tabbar('leaderboard')+`
    <h1>${T('lb.title')}</h1>
    <div class="lbsel"><select id="lbMetric">${opts}</select></div>
    <div class="lblist">${rows}</div>`;
  document.getElementById('lbMetric').onchange=e=>{
    history.replaceState(null,'',`?view=leaderboard&metric=${e.target.value}`);
    load();
  };
}

function renderNutritionDays(d){
  const days=d.days||[];
  const w=d.weight_kg;
  const rows=days.length?days.map(r=>{
    const ppk=w&&r.protein_g?Math.round(r.protein_g/w*100)/100:null;
    return `<div class="wrow" onclick="history.replaceState(null,'','?view=nutrition_day&day=${r.day}');load()">
      <div class="wdot" style="background:${ppk!=null&&ppk>=1.6?'var(--green)':'var(--amber)'}"></div>
      <div class="wmain">
        <div class="wt">${r.day} · ${Math.round(r.kcal||0)} ${T('nut.kcal')}</div>
        <div class="wsub">${T('nut.bju')}: ${Math.round(r.protein_g||0)} / ${Math.round(r.fat_g||0)} / ${Math.round(r.carb_g||0)} ${T('nut.g')} · ${r.meals} ${T('nut.meals_n')}</div>
      </div><span style="font-size:16px;margin-right:2px">${r.verdict?qEmoji('q.day.'+r.verdict):''}</span><div class="wchev">›</div>
    </div>`}).join(''):`<div class="card" style="color:var(--mut);font-size:13px">${T('nut.no_meals')}</div>`;
  app.innerHTML=tabbar('nutrition')+`
    <h1>${T('nut.title')}</h1>
    <div class="sub">${T('nut.days_sub')}</div>
    ${rows}
    <div class="foot">${T('nut.hint')}</div>`;
}

function renderNutritionDay(d){
  const t=d.totals||{};
  const meals=d.meals||[];
  const ppk=d.protein_per_kg;
  const macroTile=(label,v,unit)=>`<div class="det-tile"><div class="det-tile-v">${v}</div><div class="det-tile-l">${label}${unit?', '+unit:''}</div></div>`;
  const mealRows=meals.length?meals.map(m=>{
    const foods=(m.foods||[]).map(f=>`${f.name} ~${f.grams!=null?Math.round(f.grams):'—'}г`).join(', ');
    const qBadge=m.quality?`<span style="margin-right:6px">${qEmoji('q.meal.'+m.quality)}</span>`:'';
    const qNote=(m.quality===3||m.quality===4)
      ?`<div style="font-size:11.5px;color:var(--mut);margin-top:3px">${qLabel('q.meal.'+m.quality)} — ${m.quality_note||''}</div>`:'';
    return `<div class="card" style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;font-size:13px"><b>${(m.ts||'').slice(11,16)||'—'}</b><b>${qBadge}${Math.round(m.kcal||0)} ${T('nut.kcal')}</b></div>
      <div style="font-size:12.5px;opacity:.85;margin-top:3px">${foods}</div>
      <div style="font-size:11.5px;color:var(--mut);margin-top:3px">${T('nut.bju')}: ${Math.round(m.protein_g||0)} / ${Math.round(m.fat_g||0)} / ${Math.round(m.carb_g||0)} ${T('nut.g')}</div>
      ${qNote}
    </div>`}).join(''):`<div class="card" style="color:var(--mut);font-size:13px">${T('nut.no_meals')}</div>`;
  const MICRO_T={fiber_g:30,sugar_g:50,sodium_mg:2300,iron_mg:8,calcium_mg:1000,magnesium_mg:400,potassium_mg:3500};
  const MICRO_LIMIT=new Set(['sugar_g','sodium_mg']);
  const microVal=k=>(MICRO_LIMIT.has(k)?'≤':'')+Math.round(t[k]||0)+'/'+MICRO_T[k];
  const microTile=([k,l,u])=>macroTile(l,microVal(k),u);
  const microTop=[['fiber_g',T('nut.m_fiber'),T('nut.g')],['sodium_mg',T('nut.m_sodium'),T('nut.mg')],
    ['calcium_mg',T('nut.m_calcium'),T('nut.mg')],['potassium_mg',T('nut.m_potassium'),T('nut.mg')]];
  const microMore=[['sugar_g',T('nut.m_sugar'),T('nut.g')],['iron_mg',T('nut.m_iron'),T('nut.mg')],
    ['magnesium_mg',T('nut.m_magnesium'),T('nut.mg')]];
  const microHtml=`<div class="det-tiles" style="grid-template-columns:repeat(2,1fr)">${microTop.map(microTile).join('')}</div>
    <details style="margin-top:8px"><summary style="font-size:12px;color:var(--mut);cursor:pointer">${T('nut.micro_more')}</summary>
    <div class="det-tiles" style="grid-template-columns:repeat(3,1fr);margin-top:8px">${microMore.map(microTile).join('')}</div></details>`;
  const adviceHtml=(d.advice&&d.advice.length)?`
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin:14px 0 8px">${T('nut.advice_hd')}</div>
    <div class="card">${d.advice.map(a=>`<div style="font-size:13px;margin:3px 0">• ${a}</div>`).join('')}</div>`:'';
  let ringHtml='';
  if(d.targets){
    const budget=d.targets.kcal+(d.burned||0), eaten=Math.round(t.kcal||0);
    const remain=budget-eaten, deg=Math.min(360, budget>0?eaten/budget*360:0);
    const remTxt=remain>=0?remain:`<span style="color:var(--red)">${T('nut.over').replace('{v}',-remain)}</span>`;
    ringHtml=`<div class="card" style="margin-bottom:8px"><div style="display:flex;align-items:center;justify-content:space-between">
      <div style="text-align:center;width:76px"><div style="font-size:11px;color:var(--mut)">${T('nut.eaten')}</div><div style="font-size:18px;font-weight:700">${eaten}</div></div>
      <div style="position:relative;width:118px;height:118px;border-radius:50%;background:conic-gradient(var(--tg-theme-button-color,#1D9E75) 0 ${deg}deg, rgba(128,128,128,.18) ${deg}deg 360deg);display:flex;align-items:center;justify-content:center">
        <div style="width:94px;height:94px;border-radius:50%;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center">
          <div style="font-size:10px;color:var(--mut)">${T('nut.remaining')}</div>
          <div style="font-size:22px;font-weight:800">${remTxt}</div>
          <div style="font-size:9px;color:var(--mut)">${T('nut.norm').replace('{v}',d.targets.kcal)}</div>
        </div></div>
      <div style="text-align:center;width:76px"><div style="font-size:11px;color:var(--mut)">${T('nut.burned')}</div><div style="font-size:18px;font-weight:700;color:var(--green)">+${d.burned||0}</div></div>
    </div></div>`;
  }
  const mbar=(label,val,tgt,color)=>{
    const pct=tgt?Math.min(100,Math.round(val/tgt*100)):0;
    return `<div style="flex:1;background:rgba(128,128,128,.08);border-radius:10px;padding:8px">
      <div style="font-size:11px;color:var(--mut)">${label}</div>
      <div style="font-weight:700">${Math.round(val)}${tgt?'/'+tgt:''} ${T('nut.g')}</div>
      ${tgt?`<div style="height:4px;background:rgba(128,128,128,.25);border-radius:2px;margin-top:4px"><div style="width:${pct}%;height:4px;background:${color};border-radius:2px"></div></div>`:''}
    </div>`;
  };
  const macroHtml=d.targets?
    `<div style="display:flex;gap:8px;margin-top:9px">
      ${mbar(T('nut.protein'),t.protein_g||0,d.targets.protein_g,'#e5484d')}
      ${mbar(T('nut.fat'),t.fat_g||0,d.targets.fat_g,'#b088f9')}
      ${mbar(T('nut.carb'),t.carb_g||0,d.targets.carb_g,'#4c8dff')}
    </div>`:
    `<div class="det-tiles" style="margin-top:9px">
      ${macroTile(T('nut.protein'),Math.round(t.protein_g||0),T('nut.g'))}
      ${macroTile(T('nut.fat'),Math.round(t.fat_g||0),T('nut.g'))}
      ${macroTile(T('nut.carb'),Math.round(t.carb_g||0),T('nut.g'))}
    </div>`;
  const waterSweat=d.water_target_l>2.2?`<span style="color:var(--mut);margin-left:6px">${T('nut.water_sweat').replace('{v}',(d.water_target_l-2.2).toFixed(1))}</span>`:'';
  const dayVerdictHtml=d.day_verdict?`<div class="card" style="display:flex;justify-content:space-between;font-weight:700"><span>${d.day||''}</span><span>${T('q.day.'+d.day_verdict)}</span></div>`:'';
  app.innerHTML=tabbar('nutrition')+`
    <span class="back" onclick="go('nutrition')">← ${T('nut.title')}</span>
    <h1>${d.day||''}</h1>
    ${ringHtml}
    <div class="card" style="margin-bottom:8px">
      <div style="display:flex;justify-content:space-between;align-items:baseline">
        <div><span style="font-size:26px;font-weight:700">${Math.round(t.kcal||0)}</span><span style="font-size:12px;opacity:.6;margin-left:4px">${T('nut.kcal')}</span></div>
        <div style="font-size:13px;color:var(--mut)">💧 ${d.water_l!=null?d.water_l:0}${d.water_target_l!=null?' / '+d.water_target_l:''} ${T('nut.l')}${waterSweat}</div>
      </div>
      ${macroHtml}
      ${ppk!=null?`<div style="font-size:12px;color:${ppk>=1.6?'var(--green)':'var(--amber)'};margin-top:7px">${T('nut.protein_per_kg').replace('{v}',ppk)}</div>`:''}
    </div>
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin:14px 0 8px">${T('nut.meals_hd')}</div>
    ${mealRows}
    ${dayVerdictHtml}
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:.5px;opacity:.55;margin:14px 0 8px">${T('nut.micro_hd')}</div>
    <div class="card">${microHtml}<div style="font-size:11px;color:var(--mut);margin-top:7px">${T('nut.micro_note')}</div></div>
    ${adviceHtml}
    <div id="llmhost_nutr_day"></div>
    <div class="foot">${T('nut.hint')}</div>`;
  loadLlm('nutr_day', d.day, !!d.pro);
}

async function setLang(l){
  try{ await fetch('/api/lang',{method:'POST',headers:{'Content-Type':'application/json','X-Init-Data':INIT},body:JSON.stringify({lang:l})}); }catch(e){}
  window.LANG = l;
  load();
}

function updateLangSwitcher(){
  document.querySelectorAll('.langsw a').forEach(el=>{
    el.classList.toggle('on', el.dataset.lang===window.LANG);
  });
}

async function load(){
  const params=new URLSearchParams(location.search);
  const view=params.get('view')||'summary';
  app.innerHTML=`<div class="loading">${T('common.loading')}</div>`;
  try{
    if(view==='workouts') renderWorkoutsList(await api('/api/workouts'));
    else if(view==='competitions') renderCompetitions(await api('/api/competitions'));
    else if(view==='competition'){ const id=params.get('id'); if(id) renderCompetition(await api('/api/competition/'+id)); else go('competitions'); }
    else if(view==='goals') renderGoals(await api('/api/goals'));
    else if(view==='leaderboard') renderLeaderboard(await api('/api/leaderboard?metric='+(params.get('metric')||'overall')));
    else if(view==='nutrition') renderNutritionDays(await api('/api/nutrition/days'));
    else if(view==='nutrition_day') renderNutritionDay(await api('/api/nutrition?day='+(params.get('day')||'')));
    else {
      const data=await api('/api/summary');
      window.LANG = data.lang || 'ru';
      document.documentElement.lang = window.LANG;
      renderSummary(data);
    }
  }catch(e){
    app.innerHTML=`<div class="loading">${T('common.error_access').replace('{msg}',e.message)}</div>`;
  }
  updateLangSwitcher();
}
load();
