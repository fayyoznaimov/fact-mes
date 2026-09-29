import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Row, Scalar } from './model';

export const YARN_SLOTS = [['pile','Ворс (Pile)'],['ground','Грунт (Ground)'],['weft1','Уток (Weft)'],
  ['weft2','Кромка (E hem)'],['hemply','Кромка кручёная (E hem ply)'],['hempoly','Кромка полиэстер (E hem polyester)'],
  ['weft3','Бордюр (Fancy)'],['fancyply','Бордюр кручёная (Fancy ply)'],['weft4','Бордюр полиэстер (Fancy polyester)']];
export type SetupPayload = {from_day:string;effective_at:string;rows:{loom:string;values:Record<string,string>}[]};
type Props = {target:HTMLDialogElement;row:Row|null;rows:Row[];day:string;session:number;
  confirm:(payload:SetupPayload)=>Promise<unknown>;error:(message:string)=>void;close:()=>void;refresh:()=>void};
const dateLabel=(v:Scalar)=>String(v||'').split('.').reverse().join('.');
export function SetupDialog({target,row,rows,day,session,confirm,error,close,refresh}:Props){
  const [busy,setBusy]=useState(false);
  const time=useRef('07:00');
  const form=useRef<HTMLFormElement>(null);
  useEffect(()=>{
    const onClose=()=>close();target.addEventListener('close',onClose);
    return()=>target.removeEventListener('close',onClose);
  },[target,close]);
  useEffect(()=>{if(row && !target.open)target.showModal();},[row,target]);
  if(!row)return null;
  const setup=row.setup||{};
  const val=(key:string,ref:unknown)=>String(setup[key]!=null&&setup[key]!==''?setup[key]:ref==null||ref==='0'?'':ref);
  const yarnBy=(row.yarn_by||{}) as unknown as Record<string,{yarn?:string;lot?:string}>;
  const same=rows.filter(r=>r.cloth&&r.cloth===row.cloth&&r.loom!==row.loom).map(r=>r.loom);
  const save=async()=>{
    if(busy||!form.current)return;
    const data=new FormData(form.current),get=(key:string)=>String(data.get(key)||'');
    if(!get('time')){error('Укажите время начала заправки');return;}
    const values=Object.fromEntries(['design','gsm','weight_kg','ppt','panels',...YARN_SLOTS.flatMap(([slot])=>[slot+'_yarn',slot+'_lot'])].map(k=>[k,get(k)]));
    const looms=[row.loom,...(get('same')?same:[])];
    setBusy(true);
    try{
      const result=await confirm({from_day:get('from').replace(/-/g,'.'),effective_at:get('from')+'T'+get('time')+':00+05:00',rows:looms.map(loom=>({loom,values}))});
      if(result){target.close();refresh();}
    }catch(e){error('Заправка не сохранена: '+(e instanceof Error?e.message:String(e)));}
    finally{setBusy(false);}
  };
  return createPortal(<form method="dialog" ref={form} key={session}>
    <h3 id="ls-title">Заправка станка {row.loom}{row.cloth?' · '+row.cloth:''}</h3>
    <p className="note" id="ls-note">{row.setup?`Сейчас действует запись с ${dateLabel(setup.from_day)} (ввёл ${setup.set_by||'—'}).`:'Вручную по этому станку ещё не вводили — в полях значения из справочника, их можно поправить.'}</p>
    <div className="ls-grid">
      <label className="f"><span>С какого дня</span><input id="ls-from" name="from" type="date" defaultValue={day.replace(/\./g,'-')}/></label>
      <label className="f"><span>Дизайн</span><input id="ls-design" name="design" autoComplete="off" placeholder="D144" defaultValue={val('design',row.design)}/></label>
      <label className="f"><span>GSM</span><input id="ls-gsm" name="gsm" inputMode="decimal" autoComplete="off" defaultValue={val('gsm',row.gsm)}/></label>
      <label className="f"><span>Вес штуки, кг</span><input id="ls-weight_kg" name="weight_kg" inputMode="decimal" placeholder="0,635 или 635 г" autoComplete="off" defaultValue={val('weight_kg',row.weight_kg)}/></label>
      <label className="f"><span>PPT — прокидки на ряд</span><input id="ls-ppt" name="ppt" inputMode="numeric" autoComplete="off" defaultValue={val('ppt',row.ppt)}/></label>
      <label className="f"><span>Время начала заправки</span><input id="ls-time" name="time" type="time" defaultValue={time.current} onChange={e=>{time.current=e.target.value;}} required/></label>
      <label className="f"><span>Панелей</span><input id="ls-panels" name="panels" inputMode="numeric" autoComplete="off" defaultValue={val('panels',row.panels)}/></label>
    </div>
    <table className="ls-yarn"><thead><tr><th/><th>Пряжа</th><th>Лот</th></tr></thead><tbody id="ls-yarns">
      {YARN_SLOTS.map(([slot,label])=><tr key={slot}><th scope="row">{label}</th>
        {(['yarn','lot'] as const).map(kind=><td key={kind}><input name={slot+'_'+kind} data-f={slot+'_'+kind} data-pick={kind+':'+slot} defaultValue={val(slot+'_'+kind,yarnBy[slot]?.[kind])} autoComplete="off" aria-label={label+': '+(kind==='yarn'?'пряжа':'лот')}/></td>)}
      </tr>)}
    </tbody></table>
    <label className={'checks'+(same.length?'':' hidden')} id="ls-same-wrap"><input type="checkbox" id="ls-same" name="same"/> <span id="ls-same-text">то же для станков с этим кодом ткани: {same.join(', ')}</span></label>
    <p className="note">Запись действует с указанного дня, пока станок не перезаправят. Пустое поле — значение берётся из справочника артикулов и техкарты 1С.</p>
    <div className="btns"><button className="act" value="cancel" formNoValidate>Отмена</button><button className="act primary" id="ls-save" type="button" disabled={busy} onClick={()=>{void save();}}>Проверить и провести…</button></div>
  </form>,target);
}
