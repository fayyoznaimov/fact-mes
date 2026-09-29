import { nf, value, type Row, type Column } from './model';

const slots=(...ys:string[])=>ys.flatMap(y=>[y+'_yarn',y+'_lot']);
const keys:Record<string,string[]>={pile:slots('pile'),ground:slots('ground'),weft:slots('weft1'),
  hem:slots('weft2','hemply','hempoly'),fancy:slots('weft3','fancyply','weft4')};
const manual=(r:Row,s:string)=>!!(r.setup && (keys[s] || [s]).some(k=>r.setup![k]!=null && r.setup![k]!==''));
const tip=(r:Row)=>`введено вручную: ${r.setup?.set_by || '—'}, действует с ${r.setup?.from_day}`;
export function Cell({c,r,canEdit,open}:{c:Column;r:Row;canEdit:boolean;open:(loom:string)=>void}) {
  const v=value(r,c.k),sep=c.sep?' sep':'';
  if(c.ph)return <td className="sep ph" />;
  if(c.k==='loom')return canEdit
    ? <td className="edit-loom" data-loom={r.loom} title="Ввести GSM, вес штуки, PPT, пряжу и лот" onClick={()=>open(r.loom)}><strong>{v}</strong> <span className="pen" aria-hidden="true">✎</span></td>
    : <td><strong>{v}</strong></td>;
  if(c.s){const man=manual(r,c.s);return <td className={(c.text?'tx':'n')+sep+(man?' man':'')} title={man?tip(r):undefined}>{c.text?v??'':nf(v,c.d || 0)}</td>;}
  if(c.k==='ppt'){
    const estimate=value(r,'ppt_est'),fact=value(r,'ppt_fact'),gap=value(r,'ppt_gap'),spread=value(r,'ppt_spread'),note=value(r,'ppt_note');
    const hot=gap!=null && Math.abs(Number(gap))>5;
    if(v==null || v==='')return <td className={'n note'+sep} title={'PPT не введён — введите его во вкладке «Заправка» (или щёлкните по номеру станка)'+(estimate?`. Оценка по счётчикам ткани FACT ≈ ${nf(estimate)} — только подсказка, в расчёт килограммов не входит`:'')}>
      не введено{estimate?<><br/><small>≈ {nf(estimate)} по FACT</small></>:null}</td>;
    if(manual(r,'ppt'))return <td className={'n man'+sep} title={tip(r)}>{nf(v)}</td>;
    const title=fact!=null?`по счётчикам станка ${nf(fact)}${gap!=null?` (${Number(gap)>0?'+':''}${nf(gap,1)} %)` : ''}${spread!=null?`, разброс по дням ${nf(spread,1)} %`:''}${note?` — ${note}`:''}`:'по счётчикам не посчитан';
    return <td className={'n'+sep+(hot?' c-yel':'')} title={title}>{nf(v)}{fact!=null&&hot?<><br/><small>факт {nf(fact)}</small></>:null}</td>;
  }
  return <td className={(c.text?'tx':'n')+sep+(c.p?c.p(v):'')}>{c.text?v??'':nf(v,c.d || 0)}</td>;
}
