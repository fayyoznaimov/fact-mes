import { useLayoutEffect, useRef, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Cell } from './Cell';
import { average, G_MEND, G_SETUP, nextSort, nf, selectRows, SHIFT_GROUPS, sum, visibleColumns, type Snapshot, type View } from './model';

export type Actions = {setView:(view:View)=>void; load:(day:string)=>void; setup:(loom:string)=>void;
  full:(on:boolean)=>void; stick:()=>void; period:()=>void; approved:()=>void; excel:()=>void};
export type Targets={bar:Element;table:Element;tiles:Element;strip:Element};
const dayLabel=(day:string)=>day.split('.').reverse().join('.');
const keyAction=(e:KeyboardEvent,run:()=>void)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();run();}};

export function Report({state,days,range,actions,targets}:{state:Snapshot;days:string[];range:{from:string;to:string};actions:Actions;targets:Targets}) {
  const {rows,bad}=selectRows(state.rows,state),visible=visibleColumns(state.hidden);
  const groups:{g:string;n:number}[]=[];
  visible.forEach(({c})=>{const g=c.g||'',last=groups.at(-1);if(last?.g===g)last.n++;else groups.push({g,n:1});});
  const shiftCheck=useRef<HTMLInputElement>(null);
  const shiftOpen=SHIFT_GROUPS.filter(g=>!state.hidden.includes(g)).length;
  useLayoutEffect(()=>{if(shiftCheck.current)shiftCheck.current.indeterminate=shiftOpen>0&&shiftOpen<SHIFT_GROUPS.length;targets.table.setAttribute('aria-busy',String(!!state.loading));actions.stick();});
  const change=(v:Partial<View>)=>actions.setView({...state,...v});
  const toggle=(groups:string[],open?:boolean)=>{
    const hidden=new Set(state.hidden);groups.forEach(g=>{const show=open??hidden.has(g);if(show)hidden.delete(g);else hidden.add(g);});change({hidden:[...hidden]});
  };
  const hiddenFilters=Object.keys(state.filters).filter(i=>!visible.some(v=>v.i===+i)).length;
  const filtered=rows.length!==state.rows.length;
  const count=(filtered?`Показано ${rows.length} из ${state.rows.length} станков`:'')+(hiddenFilters?`${filtered?'; ':''}фильтр стоит и в свёрнутой группе`:'');
  const potential=sum(rows,'prod100_kg'),fact=sum(rows,'achieved_kg');
  const totals=[['100% Production',<>{nf(potential)}<small> кг</small></>],['Achieved',<>{nf(fact)}<small> кг</small></>],
    ['Efficiency',potential?<>{nf(100*fact/potential,1)}<small> %</small></>:'—'],['Средние об/мин',nf(average(rows,'rpm'))],
    ['Всего пиков',<>{nf(sum(rows,'picks')/1e6,2)}<small> млн</small></>],['Станков',filtered?<>{rows.length}<small> из {state.rows.length}</small></>:state.rows.length]];
  const day=state.day||days[0]||'';
  return <>
    {createPortal(<>
      <div className="f"><label htmlFor="rep-day">День</label><select id="rep-day" value={day} onChange={e=>actions.load(e.target.value)}>{days.map(d=><option key={d} value={d}>{dayLabel(d)}</option>)}</select></div>
      <div className="f"><label>&nbsp;</label><button className="act primary" id="rep-full" title="Только таблица, на весь экран. Выход — Esc" onClick={()=>actions.full(true)}>Развернуть отчёт</button></div>
      <div className="f"><label htmlFor="rp-from">За период с</label><input id="rp-from" type="date" defaultValue={range.from}/></div>
      <div className="f"><label htmlFor="rp-to">по</label><input id="rp-to" type="date" defaultValue={range.to}/></div>
      <div className="f"><label>&nbsp;</label><button className="act" id="rp-go" onClick={()=>actions.period()}>Отчёт за период</button></div>
      <div className="f"><label>&nbsp;</label><button className="act" id="rp-list" onClick={()=>actions.approved()}>Утверждённые отчёты</button></div>
      <div className="f"><label>&nbsp;</label><button className="act" id="rep-excel" disabled={!state.exportAllowed||state.loading||state.exportBusy} onClick={()=>actions.excel()}>{state.exportBusy?'Собираю…':'Скачать Excel'}</button></div>
      <div className="f"><label htmlFor="rep-flag">Показывать</label><select id="rep-flag" value={state.flag} onChange={e=>change({flag:e.target.value})}><option value="all">все станки</option><option value="red">только с красным</option><option value="warn">с жёлтым или красным</option></select></div>
      <div className="f"><label>&nbsp;</label><button className="act" id="rep-reset" onClick={()=>change({filters:{},sort:null,flag:'all'})}>Сбросить фильтры и сортировку</button></div>
      <div className="f"><label>Раскрыть колонки</label><div className="checks" style={{paddingTop:4}}>
        <label><input type="checkbox" id="rg-setup" checked={!state.hidden.includes(G_SETUP)} onChange={e=>toggle([G_SETUP],e.target.checked)}/> Заправка</label>
        <label><input type="checkbox" id="rg-mend" checked={!state.hidden.includes(G_MEND)} onChange={e=>toggle([G_MEND],e.target.checked)}/> Mending time</label>
        <label title="Свёрнутая смена показывает только итог"><input type="checkbox" id="rg-shift" ref={shiftCheck} checked={shiftOpen===SHIFT_GROUPS.length} onChange={e=>toggle(SHIFT_GROUPS,e.target.checked)}/> Смены A / B / C</label>
      </div></div>
      <div className="f"><label>&nbsp;</label><span className="note" id="rep-count" style={{padding:'7px 0'}}>{count}</span></div>
    </>,targets.bar)}
    {createPortal(totals.map(([label,content])=><div className="tile" key={String(label)}><div className="l">{label}</div><div className="v">{content}</div></div>),targets.tiles)}
    {createPortal(<><span><b>Производственный отчёт</b> · <span id="rep-strip-day">{dayLabel(day)}</span> <span id="rep-strip-info" className="note">{count}</span></span><button className="act" id="rep-strip-exit" onClick={()=>actions.full(false)}>Свернуть <span className="note">(Esc)</span></button></>,targets.strip)}
    {createPortal(<>
      <thead><tr className="grp">{groups.map(({g,n},i)=>g?<th key={g} colSpan={n} className="sep tg" data-g={g} tabIndex={0} aria-expanded={!state.hidden.includes(g)} title={`${state.hidden.includes(g)?'Раскрыть':'Свернуть'}: ${g}`} onClick={()=>toggle([g])} onKeyDown={e=>keyAction(e,()=>toggle([g]))}>
        <span className="car" aria-hidden="true">{state.hidden.includes(g)?'▸':'▾'}</span>{state.hidden.includes(g)&&!SHIFT_GROUPS.includes(g)?'':g}</th>:<th key={i} colSpan={n}/>)}</tr>
      <tr className="cols">{visible.map(({c,i})=>c.ph?<th key={c.g} className="sep ph" data-g={c.g} title={`Раскрыть: ${c.g}`} onClick={()=>toggle([c.g!])}>{c.g===G_SETUP?'Запр.':'Mend.'}</th>
        :<th key={c.k} className={(c.text?'':'n')+(c.sep?' sep':'')+' sortable'} data-i={i} tabIndex={0} title={`Сортировать: ${c.g?c.g+', ':''}${c.t}`} aria-sort={state.sort?.i===i?(state.sort.dir>0?'ascending':'descending'):'none'} onClick={()=>change({sort:nextSort(state.sort,i)})} onKeyDown={e=>keyAction(e,()=>change({sort:nextSort(state.sort,i)}))}>
          {c.t}<span className="ar">{state.sort?.i===i?(state.sort.dir>0?'▲':'▼'):''}</span></th>)}</tr>
      <tr className="flt">{visible.map(({c,i})=>c.ph?<th key={c.g} className="sep ph"/>:<th key={c.k} className={c.sep?'sep':undefined}><input className={'flt'+(bad.includes(i)?' bad-in':'')+(state.filters[i]?.trim()&&!bad.includes(i)?' on':'')} size={1} data-i={i} value={state.filters[i]||''}
        onChange={e=>{const filters:Record<string,string>={...state.filters,[i]:e.target.value};if(!e.target.value.trim())delete filters[i];change({filters});}} autoComplete="off" placeholder={c.text==='loom'?'D, J1-J14':''}
        title={c.text==='loom'?'D — ряд, J1-J14 — участок, D1,D5 — перечисление':c.text?'часть текста, например 12/1':'>60, <70, 50-80, =0'} aria-label={`Фильтр: ${c.g?c.g+', ':''}${c.t}`}/></th>)}</tr></thead>
      <tbody>{rows.length?rows.map((r,ri)=><tr key={r.loom||ri}>{visible.map(({c})=><Cell key={c.k||c.g} c={c} r={r} canEdit={state.setupEdit&&!state.loading} open={actions.setup}/>)}</tr>):<tr><td className="note" colSpan={visible.length}>Под фильтры не попал ни один станок</td></tr>}</tbody>
      <tfoot><tr>{visible.map(({c})=>{
        if(c.ph)return <td key={c.g} className="sep ph"/>;
        if(c.k==='sr')return <td key={c.k}>Итого</td>;
        if(c.k==='loom')return <td key={c.k}>{rows.length} станков</td>;
        return <td key={c.k} className={'n'+(c.sep?' sep':'')}>{c.f==='sum'?nf(sum(rows,c.k),c.d||0):c.f==='avg'?nf(average(rows,c.k),c.d||0):''}</td>;
      })}</tr></tfoot>
    </>,targets.table)}
  </>;
}
