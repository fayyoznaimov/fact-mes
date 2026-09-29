import { Fragment } from 'react';
import { nf, type Scalar } from './model';
import { dateLabel, PeriodTable, PeriodTiles, Tiles, type PeriodData, type PeriodTotals } from './period';

export type Change={loom?:string;field?:string;label?:string;title?:string;before?:Scalar;after?:Scalar;
  before_source?:string;after_source?:string;delta?:number|null;changed?:boolean;since?:string;since_by?:string;context?:Record<string,Scalar>};
export type CheckedDocument={type:'setup'|'report';title:string;type_title:string;checksum:string;errors:string[];warnings:string[];
  may_post?:boolean;changes:Change[];summary:PeriodTotals & {changed_looms?:number;changed_fields?:number};result:Partial<PeriodData>};
const number=(value:Scalar)=>typeof value==='number'?value.toLocaleString(document.documentElement.lang==='en'?'en-GB':'ru-RU',{maximumFractionDigits:Math.abs(value)<10?4:1}):value;
const blank=(v:Scalar)=>v==null||v==='';
function Value({value,source}:{value:Scalar;source?:string}){return <>{blank(value)?<span className="dx-none">пусто</span>:number(value)}{source?<span className="dx-src">{source}</span>:null}</>;}
export function DiffTable({rows,before='Было',after='Стало'}:{rows:Change[];before?:string;after?:string}){
  if(!rows.length)return <p className="note">Реквизиты не менялись.</p>;
  return <div className="tbl-wrap"><table className="dx-diff"><thead><tr><th>Реквизит</th><th>{before}</th><th>{after}</th><th className="n">Разница</th></tr></thead><tbody>{rows.map((r,i)=>{
    const kind=r.changed===false?'same':blank(r.before)&&!blank(r.after)?'add':blank(r.after)&&!blank(r.before)?'del':'chg';
    return <tr key={i} className={'dx-'+kind}><th scope="row">{r.label||r.title||r.field}</th>
      <td className="dx-was">{kind==='add'?<span className="dx-none">не было</span>:<Value value={r.before} source={r.before_source}/>}</td>
      <td className="dx-now">{kind==='del'?<span className="dx-none">удалено</span>:<Value value={r.after} source={r.after_source}/>}</td>
      <td className="n">{r.delta!=null&&r.delta!==0&&!isNaN(r.delta)?<span className="dx-delta">{r.delta>0?'+':'−'}{number(Math.abs(Math.round(r.delta*1000)/1000))}</span>:null}</td></tr>;
  })}</tbody></table></div>;
}
export function DocumentBody({checked:c,note}:{checked:CheckedDocument;note?:string}){
  const errors=c.errors.length,warnings=c.warnings.length;
  const groups=new Map<string,Change[]>();c.changes.forEach(r=>{const key=r.loom||'';groups.set(key,[...(groups.get(key)||[]),r]);});
  return <>{note?<p className="bad">{note}</p>:null}
    <div className={'doc-verdict '+(errors?'err':warnings?'warn':'ok')}>{errors?`Провести нельзя: ошибок ${errors}`:warnings?`Можно провести — прочитайте предупреждения (${warnings})`:'Проверено: можно проводить'}<small>{c.type_title}</small></div>
    {c.type==='report'?<PeriodTiles totals={c.summary}/>:<Tiles values={[
      ['Станков',c.summary.looms],['С изменениями',c.summary.changed_looms],['Реквизитов меняется',c.summary.changed_fields],
    ]}/>}
    {errors?<><h4>Ошибки — исправьте и проверьте снова</h4><ul className="doc-list err">{c.errors.map((e,i)=><li key={i}>{e}</li>)}</ul></>:null}
    {warnings?<><h4>Предупреждения</h4><ul className="doc-list warn">{c.warnings.map((e,i)=><li key={i}>{e}</li>)}</ul></>:null}
    {!errors?<>
      {c.type==='setup'||c.changes.length?<h4>{c.type==='setup'?'Что изменится':'Отличия от заменяемого отчёта'}</h4>:null}
      {[...groups].map(([loom,rows])=><div className="dx-obj" key={loom}><h4>Станок {loom}{c.type==='setup'?<small>{rows[0].since?`сейчас действует заправка с ${dateLabel(rows[0].since)}, ввёл ${rows[0].since_by||'—'}`:'ручной заправки ещё не было'}</small>:null}</h4>
        {c.type==='setup'&&rows[0].context&&Object.keys(rows[0].context).length?<p className="dx-ctx">{Object.entries(rows[0].context).map(([k,v])=><span key={k}>{k} <b>{v}</b></span>)}</p>:null}
        <DiffTable rows={c.type==='setup'?rows:rows.map(r=>({...r,label:r.title,delta:typeof r.before==='number'&&typeof r.after==='number'?r.after-r.before:null}))} before={c.type==='setup'?'Сейчас':'Было'} after={c.type==='setup'?'Станет':'Стало'}/>
      </div>)}
      {c.type==='report'&&c.result.rows&&c.result.totals?<Fragment><h4>Отчёт</h4><PeriodTable data={{rows:c.result.rows,totals:c.result.totals}}/></Fragment>:null}
    </>:null}
    {c.may_post===false?<p className="note">Просмотр: провести этот документ может пользователь с соответствующим правом.</p>:null}
  </>;
}
