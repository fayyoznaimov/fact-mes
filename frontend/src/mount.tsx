import { createRoot } from 'react-dom/client';
import { createRef } from 'react';
import { flushSync } from 'react-dom';
import { Report, type Actions, type Targets } from './features/report/Report';
import type { Snapshot } from './features/report/model';
import { ReportController, requestReport } from './features/report/controller';
import { SetupDialog } from './features/report/SetupDialog';
import { ReportWorkflow, type WorkflowHandle } from './features/report/ReportWorkflow';
import type { PlanBridge } from './features/plan/bridge';
import { Onec } from './features/plan/onec/Onec';
import { OnecController, requestOnecDetail, requestOnecMessages } from './features/plan/onec/controller';
import { Codes } from './features/plan/codes/Codes';
import { CodesController, requestClothMap } from './features/plan/codes/controller';
import type { PlanClothData } from './features/plan/codes/model';
import { Ppt } from './features/plan/ppt/Ppt';
import { PptController, requestPptCheck } from './features/plan/ppt/controller';

declare global {
  interface Window {
    FactReportLegacy: Omit<Actions,'load'|'setView'|'setup'|'period'|'excel'> & {snapshot:()=>Snapshot;
      publish:(rows:Snapshot['rows'])=>void;expire:()=>void;error:(message:string)=>void;
      prepareSetup:()=>Promise<void>;notify:(message:string,error?:boolean)=>void;openDocument:(id:number)=>void};
    FactReactReport?: {update:()=>void;setDays:(days:string[])=>void;load:(autoSkip?:boolean)=>Promise<void>};
    FactPlanLegacy?: PlanBridge;
    FactPlanReact?: {loadOnec:()=>void;onPlan:(data:PlanClothData)=>void;loadPpt:()=>void};
  }
}
export function mountReport() {
  const legacy=window.FactReportLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка отчёта');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента отчёта: '+selector);return el;
  };
  const targets:Targets={bar:element('#tab-report > .bar'),table:element('#rep-table'),tiles:element('#rep-tiles'),strip:element('#rep-strip')};
  const days=Array.from(element<HTMLSelectElement>('#rep-day').options).map(o=>o.value);
  const snapshot=legacy.snapshot();
  const range={from:element<HTMLInputElement>('#rp-from').value,to:element<HTMLInputElement>('#rp-to').value};
  const setupTarget=element<HTMLDialogElement>('#ls-dlg');
  setupTarget.replaceChildren();
  let setupRow:Snapshot['rows'][number]|null=null,setupSession=0;
  Object.values(targets).forEach(target=>target.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactReport='';document.body.appendChild(host);
  const root=createRoot(host);
  const workflow=createRef<WorkflowHandle>();
  let alive=true;
  const closeSetup=()=>{setupRow=null;render();};
  const refresh=()=>{void controller.load(false);};
  const render=()=>flushSync(()=>root.render(<>
    <Report state={controller.state} days={controller.days} range={range} actions={actions} targets={targets}/>
    <SetupDialog target={setupTarget} row={setupRow} rows={controller.state.rows} day={controller.state.day} session={setupSession}
      confirm={payload=>workflow.current!.confirm('setup',payload)} error={legacy.error} close={closeSetup} refresh={refresh}/>
    <ReportWorkflow ref={workflow} expire={legacy.expire} notify={legacy.notify} openDocument={legacy.openDocument}
      exportBusy={busy=>{controller.state={...controller.state,exportBusy:busy};render();}}/>
  </>));
  const controller=new ReportController(snapshot,days,{
    request:(day,signal)=>requestReport(day,signal,legacy.expire),changed:render,
    publish:legacy.publish,error:legacy.error,
    storage:{getItem:key=>localStorage.getItem(key),setItem:(key,v)=>localStorage.setItem(key,v)},
  });
  const actions:Actions={...legacy,setView:view=>controller.setView(view),load:day=>{void controller.load(false,day);},
    period:()=>workflow.current!.period(element<HTMLInputElement>('#rp-from').value.replace(/-/g,'.'),element<HTMLInputElement>('#rp-to').value.replace(/-/g,'.')),
    excel:()=>{if(controller.state.exportAllowed&&!controller.state.loading)workflow.current!.excel(controller.state.day);},setup:loom=>{
    if(!controller.state.setupEdit||controller.state.loading)return;
    const day=controller.state.day;
    void legacy.prepareSetup().then(()=>{
      if(!alive||controller.state.loading||controller.state.day!==day||!controller.state.setupEdit)return;
      setupRow=controller.state.rows.find(r=>r.loom===loom)||null;setupSession++;render();
    }).catch(e=>legacy.error('Заправка не открылась: '+String(e)));
  }};
  const update=()=>{
    const {setupEdit,exportAllowed}=legacy.snapshot();
    controller.state={...controller.state,setupEdit,exportAllowed};render();
  };
  window.FactReactReport={
    update,
    setDays:next=>{controller.setDays(next);update();},
    load:autoSkip=>controller.load(autoSkip),
  };
  render();
  const language=()=>window.FactReactReport?.update();
  window.addEventListener('mes-language-change',language);
  if(days.length && !element('#tab-report').classList.contains('hidden'))void controller.load(true);
  return ()=>{alive=false;controller.dispose();window.removeEventListener('mes-language-change',language);delete window.FactReactReport;root.unmount();host.remove();};
}

export function mountPlan() {
  const legacy=window.FactPlanLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка плана');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента плана: '+selector);return el;
  };
  const tbody=element<HTMLElement>('#oc-msgs tbody'),dialog=element<HTMLDialogElement>('#oc-dlg');
  const unmappedBody=element<HTMLElement>('#cm-unmapped tbody'),mapBody=element<HTMLElement>('#cm-map tbody');
  const pptBody=element<HTMLElement>('#ppt-prod tbody'),pptDaysSummary=element<HTMLElement>('#ppt-days-sum');
  const pptDaysBody=element<HTMLElement>('#ppt-days tbody'),pptDaysDetails=element<HTMLDetailsElement>('#ppt-days-box');
  [tbody,dialog,unmappedBody,mapBody,pptBody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactPlan='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(<>
    <Onec tbody={tbody} dialog={dialog} state={onec.state} bridge={legacy}
      loadDetail={id=>requestOnecDetail(id,legacy.expire)}/>
    <Codes unmappedBody={unmappedBody} mapBody={mapBody} state={codes.state} bridge={legacy}
      link={(cloth,product)=>{void codes.link(cloth,product);}} unlink={cloth=>{void codes.unlink(cloth);}}/>
    <Ppt productsBody={pptBody} daysSummary={pptDaysSummary} daysBody={pptDaysBody} daysDetails={pptDaysDetails}
      state={ppt.state} bridge={legacy}/>
  </>));
  const onec=new OnecController({request:signal=>requestOnecMessages(signal,legacy.expire),changed:render});
  const codes=new CodesController({changed:render,say:legacy.say,refreshPlan:legacy.refreshPlan,
    postClothMap:(cloth,product)=>requestClothMap(cloth,product,legacy.expire)});
  const ppt=new PptController({request:signal=>requestPptCheck(signal,legacy.expire),changed:render});
  window.FactPlanReact={loadOnec:()=>{void onec.load();},onPlan:data=>codes.setData(data),loadPpt:()=>{void ppt.load();}};
  render();
  if(!element('#tab-plan').classList.contains('hidden')){void onec.load();void ppt.load();}
  return ()=>{onec.dispose();ppt.dispose();delete window.FactPlanReact;root.unmount();host.remove();};
}
