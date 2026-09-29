import type { ReactNode } from 'react';
import { nf } from './model';

export type PeriodRow = {loom:string;days:number;shifts:number;designs:string[];gsm:(string|number)[];
  effic:number|null;picks:number;rows:number;towels:number|null;towels_known:boolean;kg:number|null;
  pile:number;weft:number;ground:number;other:number};
export type PeriodTotals = Omit<PeriodRow,'loom'|'designs'|'gsm'> & {looms:number};
export type PeriodData = {rows:PeriodRow[];totals:PeriodTotals;days_without_report:string[]};
export const PERIOD_HEADERS=['Станок','Дней','Смен','Дизайн','GSM','КПД, %','Тыс. пиков','Ряды','Полотенца','Кг','Ворс','Уток','Грунт','Прочие'];
export const dateLabel=(date:string)=>date.split('.').reverse().join('.');
export function Tiles({values}:{values:[string,ReactNode][]}){
  return <div className="tiles" style={{marginTop:10}}>{values.map(([name,value])=><div className="tile" key={name}><span className="l">{name}</span><span className="v">{value}</span></div>)}</div>;
}
export function PeriodTiles({totals:t}:{totals:PeriodTotals}){
  return <Tiles values={[
    ['Станков',t.looms],['Дней',t.days],['КПД',t.effic==null?'—':<>{nf(t.effic,1)}<small> %</small></>],
    ['Полотенца',nf(t.towels)],['Кг',nf(t.kg,1)],
  ]}/>;
}
export function PeriodTable({data:{rows,totals:t}}:{data:Pick<PeriodData,'rows'|'totals'>}){
  const lines:ReactNode[][]=rows.map(r=>[r.loom,r.days,r.shifts,r.designs.join(', ')||'—',r.gsm.join(', ')||'—',
    r.effic==null?'—':nf(r.effic,1),nf(r.picks/1000),nf(r.rows),r.towels_known?nf(r.towels):<>{nf(r.towels)} <span className="note">неполн.</span></>,nf(r.kg,1),r.pile,r.weft,r.ground,r.other]);
  lines.push([<b>Итого</b>,t.days,'','','',t.effic==null?'—':<b>{nf(t.effic,1)}</b>,<b>{nf(t.picks/1000)}</b>,<b>{nf(t.rows)}</b>,<b>{nf(t.towels)}</b>,<b>{nf(t.kg,1)}</b>,t.pile,t.weft,t.ground,t.other]);
  return <div className="tbl-wrap"><table><thead><tr>{PERIOD_HEADERS.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{lines.map((cells,i)=><tr key={i}>{cells.map((v,j)=><td key={j}>{v}</td>)}</tr>)}</tbody></table></div>;
}
