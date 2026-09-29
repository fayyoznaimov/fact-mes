import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ApiError, requestJson } from './http';
import { DocumentBody, type CheckedDocument } from './DocumentBody';
import { dateLabel, PeriodTable, PeriodTiles, type PeriodData } from './period';

type Posted={id:number;number:string;after?:{days?:string[];after_error?:string}};
export type WorkflowHandle={period:(from:string,to:string)=>void;confirm:(type:'setup'|'report',payload:unknown)=>Promise<Posted|null>;excel:(day:string)=>void};
type Props={expire:()=>void;notify:(message:string,error?:boolean)=>void;openDocument:(id:number)=>void;exportBusy:(busy:boolean)=>void;download?:(url:string)=>void};
const message=(e:unknown)=>e instanceof Error?e.message:String(e);
export const ReportWorkflow=forwardRef<WorkflowHandle,Props>(function ReportWorkflow({expire,notify,openDocument,exportBusy,download=url=>{location.href=url;}},ref){
  const periodDialog=useRef<HTMLDialogElement>(null),docDialog=useRef<HTMLDialogElement>(null);
  const [period,setPeriod]=useState<{from:string;to:string;data?:PeriodData;error?:string}|null>(null);
  const [doc,setDoc]=useState<{type:'setup'|'report';payload:unknown;checked?:CheckedDocument;error?:string;note?:string}|null>(null);
  const [ack,setAck]=useState(false),[comment,setComment]=useState(''),[posting,setPosting]=useState(false);
  const resolver=useRef<((v:Posted|null)=>void)|null>(null),periodRequest=useRef<AbortController|null>(null),docRequest=useRef<AbortController|null>(null);
  const postLock=useRef(false),exportLock=useRef(false),alive=useRef(true);
  useEffect(()=>()=>{alive.current=false;periodRequest.current?.abort();docRequest.current?.abort();resolver.current?.(null);},[]);
  useEffect(()=>{if(period&&!periodDialog.current?.open)periodDialog.current?.showModal();},[period]);
  useEffect(()=>{if(doc&&!docDialog.current?.open)docDialog.current?.showModal();},[doc]);
  const closeDoc=(result:Posted|null=null)=>{docRequest.current?.abort();resolver.current?.(result);resolver.current=null;docDialog.current?.close();setDoc(null);};
  const confirm=(type:'setup'|'report',payload:unknown)=>{
    if(resolver.current)return Promise.resolve(null);
    const request=new AbortController();docRequest.current=request;setAck(false);setComment('');
    const captured=structuredClone(payload);setDoc({type,payload:captured});
    const result=new Promise<Posted|null>(resolve=>{resolver.current=resolve;});
    void requestJson<CheckedDocument>('/api/documents/preview',expire,{type,payload:captured},request.signal).then(checked=>{
      if(!request.signal.aborted&&alive.current)setDoc({type,payload:captured,checked});
    }).catch(e=>{if(!request.signal.aborted&&alive.current)setDoc({type,payload:captured,error:message(e)});});
    return result;
  };
  useImperativeHandle(ref,()=>({
    confirm,
    period:(from,to)=>{
      if(!from||!to){notify('Укажите период отчёта',true);return;}
      periodRequest.current?.abort();const request=new AbortController();periodRequest.current=request;
      setPeriod({from,to});
      void requestJson<PeriodData>('/api/report_period?'+new URLSearchParams({from,to}),expire,undefined,request.signal).then(data=>{
        if(!request.signal.aborted&&alive.current)setPeriod({from,to,data});
      }).catch(e=>{if(!request.signal.aborted&&alive.current)setPeriod({from,to,error:message(e)});});
    },
    excel:day=>{
      if(exportLock.current)return;exportLock.current=true;exportBusy(true);
      void requestJson<{ok:boolean;log?:string}>('/api/export_excel',expire,{day}).then(result=>{
        if(!result.ok)throw new Error(result.log||'не собралось');
        if(alive.current){download('/api/excel?day='+encodeURIComponent(day));notify('Excel за '+dateLabel(day)+' готов');}
      }).catch(e=>{if(alive.current)notify('Excel не собрался: '+message(e),true);})
        .finally(()=>{exportLock.current=false;if(alive.current)exportBusy(false);});
    },
  }));
  const post=async()=>{
    const checked=doc?.checked;
    if(!doc||!checked||postLock.current||checked.errors.length||checked.may_post===false||(checked.warnings.length&&!ack))return;
    postLock.current=true;setPosting(true);
    try{
      const result=await requestJson<Posted>('/api/documents/post',expire,{type:doc.type,payload:doc.payload,checksum:checked.checksum,comment});
      if(!alive.current)return;closeDoc(result);
      const error=result.after?.after_error;
      notify(`Проведён документ ${result.number}`+(result.after?.days?`; отчёт пересчитан за ${result.after.days.length} дн.`:'')+(error?`; пересборка отчёта не удалась: ${error}`:''),!!error);
    }catch(e){
      if(!alive.current)return;
      if(e instanceof ApiError&&e.status===409&&e.data&&typeof e.data==='object'&&'preview' in e.data){
        setDoc({...doc,checked:e.data.preview as CheckedDocument,note:e.message});setAck(false);
      }else notify('Документ не проведён: '+message(e),true);
    }finally{postLock.current=false;if(alive.current)setPosting(false);}
  };
  const checked=doc?.checked,mayPost=checked?.may_post!==false;
  return createPortal(<>
    <dialog ref={periodDialog} id="react-period" style={{width:'min(1150px,95vw)',maxHeight:'90vh',overflow:'auto'}} onClose={()=>{periodRequest.current?.abort();setPeriod(null);}}>
      <form method="dialog" style={{float:'right'}}><button className="act">Закрыть</button></form>
      <h3>{period?.data?`Производственный отчёт ${dateLabel(period.from)} – ${dateLabel(period.to)}`:'Производственный отчёт за период'}</h3>
      <div>{period?.error?<p className="bad">{period.error}</p>:period?.data?<>
        <PeriodTiles totals={period.data.totals}/>
        {period.data.days_without_report.length?<p className="note">Дневной отчёт не собран: {period.data.days_without_report.join(', ')} — нет изделия и килограммов.</p>:null}
        <p className="note">КПД, пики и ряды — из смен Toyota; изделие, панели и килограммы — из дневного отчёта каждого дня.</p>
        <PeriodTable data={period.data}/>
        <div className="bar" style={{marginTop:10}}><button className="act primary" id="rp-approve" onClick={()=>{
          const {from,to}=period;periodDialog.current?.close();
          void confirm('report',{from,to}).then(result=>{if(result&&alive.current)openDocument(result.id);});
        }}>Утвердить отчёт…</button></div>
      </>:'Загрузка…'}</div>
    </dialog>
    <dialog ref={docDialog} id="react-doc" className="ls doc" onCancel={e=>{if(postLock.current)e.preventDefault();}} onClose={()=>{if(resolver.current)closeDoc();}}>
      <form method="dialog"><h3>{checked?.title||checked?.type_title||'Проверка документа'}</h3>
        <div>{doc?.error?<p className="bad">{doc.error}</p>:checked?<DocumentBody checked={checked} note={doc?.note}/>:<p className="note">Сервер проверяет документ…</p>}</div>
        <label className="f"><span>Комментарий к документу</span><input maxLength={300} autoComplete="off" value={comment} onChange={e=>setComment(e.target.value)}/></label>
        <label className={'ack'+(!checked?.warnings.length||checked.errors.length||!mayPost?' hidden':'')}><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/> <span>Предупреждения прочитаны — провести документ так</span></label>
        <div className="btns"><button className="act" value="cancel" formNoValidate disabled={posting}>Вернуться к правке</button><button className={'act primary'+(!mayPost?' hidden':'')} type="button" disabled={!checked||!mayPost||!!checked.errors.length||(!!checked.warnings.length&&!ack)||posting} onClick={()=>{void post();}}>Провести</button></div>
      </form>
    </dialog>
  </>,document.body);
});
