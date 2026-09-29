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
import { Ppt } from './features/plan/ppt/Ppt';
import { PptController, requestPptCheck } from './features/plan/ppt/controller';
import { Orders } from './features/plan/orders/Orders';
import { OrdersController, requestAddOrder, requestAssign, requestClose, requestImport1c, requestPlan, requestSavePpt } from './features/plan/orders/controller';
import { Gantt } from './features/plan/gantt/Gantt';
import { GanttController, TimelineController, requestGantt, requestLoomTimeline } from './features/plan/gantt/controller';
import { Loom } from './features/plan/loom/Loom';
import { LoomController, requestLoomCatalog, requestLoomGrid, requestSetCells, uploadLoomExcel } from './features/plan/loom/controller';
import type { UsersBridge } from './features/users/bridge';
import { Users } from './features/users/Users';
import { UsersController, requestUsers, requestOperators, postUser, postPassword } from './features/users/controller';
import { tr, type SetupBridge } from './features/setup/bridge';
import { Setup } from './features/setup/Setup';
import { SetupController, requestSetupGrid, postYarn, postYarnUpdate, uploadYarnsFile } from './features/setup/controller';
import type { DashBridge } from './features/dash/bridge';
import { Dash } from './features/dash/Dash';
import { DashController, requestDashboard, requestForecast, postLoomArticle } from './features/dash/controller';

declare global {
  interface Window {
    FactReportLegacy: Omit<Actions,'load'|'setView'|'setup'|'period'|'excel'> & {snapshot:()=>Snapshot;
      publish:(rows:Snapshot['rows'])=>void;expire:()=>void;error:(message:string)=>void;
      prepareSetup:()=>Promise<void>;notify:(message:string,error?:boolean)=>void;openDocument:(id:number)=>void};
    FactReactReport?: {update:()=>void;setDays:(days:string[])=>void;load:(autoSkip?:boolean)=>Promise<void>;
      confirm:(type:'setup'|'report',payload:unknown)=>Promise<{id:number;number:string;after?:{days?:string[];after_error?:string}}|null>};
    FactPlanLegacy?: PlanBridge;
    FactPlanReact?: {loadOnec:()=>void;loadPpt:()=>void;loadPlan:()=>Promise<void>;loadGanttOnce:()=>void;loadLoomPlan:()=>Promise<void>};
    FactUsersLegacy?: UsersBridge;
    FactUsersReact?: {load:()=>void;openDialog:(id:number|null)=>void};
    FactSetupLegacy?: SetupBridge;
    FactSetupReact?: {load:(force:boolean)=>void;yarnsChanged:()=>void};
    FactDashLegacy?: DashBridge;
    FactDashReact?: {setDays:(days:string[])=>void;load:()=>void};
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
    confirm:(type,payload)=>workflow.current!.confirm(type,payload),
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
  const formBar=element<HTMLElement>('#pl-order').closest('.bar') as HTMLElement;
  const pptFormBar=element<HTMLElement>('#ppt-key').closest('.bar') as HTMLElement;
  const productsList=element<HTMLElement>('#pl-products');
  document.body.appendChild(productsList); // даталист общий для трёх полей — не должен пропасть при очистке formBar.
  const tilesEl=element<HTMLElement>('#pl-tiles'),ordersBody=element<HTMLElement>('#pl-table tbody'),pptNote=element<HTMLElement>('#pl-ppt-note');
  const gtBar=element<HTMLElement>('#gt-days').closest('.bar') as HTMLElement;
  const gtWrap=element<HTMLElement>('#gt-wrap'),gtDialog=element<HTMLDialogElement>('#gt-dlg');
  const lpPeriodBar=element<HTMLElement>('#lp-from').closest('.bar') as HTMLElement;
  const lpEditBar=element<HTMLElement>('#lp-span').closest('.bar') as HTMLElement;
  const lpNote=element<HTMLElement>('#lp-note'),lpContext=element<HTMLElement>('.lp-context');
  const lpTable=element<HTMLElement>('#lp-table'),lpPalette=element<HTMLElement>('.lp-pal');
  const lpOrderList=element<HTMLElement>('#lp-order-list'),lpDialog=element<HTMLDialogElement>('#lp-dlg');
  const lpWrap=element<HTMLElement>('.lp-wrap'),lpScroll=element<HTMLElement>('#lp-scroll');
  const lpInitialFrom=element<HTMLInputElement>('#lp-from').value,lpInitialTo=element<HTMLInputElement>('#lp-to').value;
  [tbody,dialog,unmappedBody,mapBody,pptBody,formBar,pptFormBar,ordersBody,gtBar,gtWrap,gtDialog,
    lpPeriodBar,lpEditBar,lpContext,lpTable,lpPalette,lpOrderList,lpDialog].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactPlan='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(<>
    <Onec tbody={tbody} dialog={dialog} state={onec.state} bridge={legacy}
      loadDetail={id=>requestOnecDetail(id,legacy.expire)}/>
    <Codes unmappedBody={unmappedBody} mapBody={mapBody} state={codes.state} bridge={legacy}
      link={(cloth,product)=>{void codes.link(cloth,product);}} unlink={cloth=>{void codes.unlink(cloth);}}/>
    <Ppt productsBody={pptBody} daysSummary={pptDaysSummary} daysBody={pptDaysBody} daysDetails={pptDaysDetails}
      state={ppt.state} bridge={legacy}/>
    <Orders formBar={formBar} pptBar={pptFormBar} productsList={productsList} tilesEl={tilesEl} tableBody={ordersBody}
      pptNote={pptNote} state={orders.state} bridge={legacy}
      addOrder={(o,p,q,d)=>orders.addOrder(o,p,q,d)} importFrom1c={()=>{void orders.importFrom1c();}}
      toggleClosed={()=>orders.toggleClosed()} showAllOrders={()=>orders.showAllOrders()}
      assign={(id,loom)=>{void orders.assign(id,loom);}} toggleClose={(id,closed)=>{void orders.toggleClose(id,!!closed);}}
      savePpt={(k,p,pn)=>orders.savePpt(k,p,pn)}/>
    <Gantt barEl={gtBar} wrapEl={gtWrap} dialog={gtDialog} state={gantt.state} timeline={timeline.state} bridge={legacy}
      setDays={n=>gantt.setDays(n)} setGroup={g=>gantt.setGroup(g)} prev={()=>gantt.prev()} next={()=>gantt.next()} today={()=>gantt.today()}
      openTimeline={(loom,a,b)=>{void timeline.open(loom,a,b);}} stepTimeline={h=>timeline.step(h)} closeTimeline={()=>timeline.close()}/>
    <Loom periodBar={lpPeriodBar} editBar={lpEditBar} noteEl={lpNote} contextEl={lpContext} table={lpTable} palette={lpPalette}
      orderList={lpOrderList} dialog={lpDialog} wrapEl={lpWrap} scrollEl={lpScroll} state={loom.state} bridge={legacy} controller={loom}/>
  </>));
  const onec=new OnecController({request:signal=>requestOnecMessages(signal,legacy.expire),changed:render});
  const codes=new CodesController({changed:render,say:legacy.say,refreshPlan:legacy.refreshPlan,
    postClothMap:(cloth,product)=>requestClothMap(cloth,product,legacy.expire)});
  const ppt=new PptController({request:signal=>requestPptCheck(signal,legacy.expire),changed:render});
  const orders=new OrdersController({request:(closed,signal)=>requestPlan(closed,signal,legacy.expire),changed:render,
    onData:data=>codes.setData(data),say:legacy.say,
    postOrder:(o,p,q,d)=>requestAddOrder(o,p,q,d,legacy.expire),postImport1c:()=>requestImport1c(legacy.expire),
    postAssign:(id,loom)=>requestAssign(id,loom,legacy.expire),postClose:(id,closed)=>requestClose(id,closed,legacy.expire),
    postPpt:(k,p,pn)=>requestSavePpt(k,p,pn,legacy.expire)});
  const gantt=new GanttController({request:(from,to,signal)=>requestGantt(from,to,signal,legacy.expire),changed:render,say:legacy.say});
  const timeline=new TimelineController({request:(loom,from,to,signal)=>requestLoomTimeline(loom,from,to,signal,legacy.expire),changed:render,say:legacy.say});
  const loom=new LoomController(lpInitialFrom,lpInitialTo,{
    requestGrid:(from,to,signal)=>requestLoomGrid(from,to,signal,legacy.expire),
    requestCatalog:signal=>requestLoomCatalog(signal,legacy.expire),
    postCells:changes=>requestSetCells(changes,legacy.expire),
    uploadExcel:file=>uploadLoomExcel(file,legacy.expire),
    changed:render,say:legacy.say,canEdit:()=>legacy.can('plan_edit'),dmy:legacy.dmy,refreshPlan:legacy.refreshPlan,
  });
  window.FactPlanReact={loadOnec:()=>{void onec.load();},loadPpt:()=>{void ppt.load();},loadPlan:()=>orders.load(),
    loadGanttOnce:()=>gantt.loadOnce(),loadLoomPlan:()=>loom.load()};
  render();
  if(!element('#tab-plan').classList.contains('hidden')){void onec.load();void ppt.load();void orders.load();void loom.load();}
  return ()=>{onec.dispose();ppt.dispose();orders.dispose();gantt.dispose();timeline.dispose();loom.dispose();delete window.FactPlanReact;root.unmount();host.remove();};
}

export function mountUsers() {
  const legacy=window.FactUsersLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка пользователей');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента пользователей: '+selector);return el;
  };
  const bar=element<HTMLElement>('#u-new').closest('.bar') as HTMLElement;
  const tbody=element<HTMLElement>('#u-table tbody');
  const dialog=element<HTMLDialogElement>('#u-dlg'),pwDialog=element<HTMLDialogElement>('#u-pw-dlg');
  [bar,tbody,dialog,pwDialog].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactUsers='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Users bar={bar} tbody={tbody} dialog={dialog} pwDialog={pwDialog} state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new UsersController({
    request:signal=>requestUsers(signal,legacy.expire),
    requestOperators:()=>requestOperators(legacy.expire),
    postUser:body=>postUser(body,legacy.expire),
    postPassword:body=>postPassword(body,legacy.expire),
    changed:render,say:legacy.say,
  });
  window.FactUsersReact={
    load:()=>{void controller.load();},
    openDialog:id=>{void controller.openDialog(id!=null?controller.state.rows.find(x=>x.id===id)||null:null);},
  };
  render();
  if(!element('#tab-users').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactUsersReact;root.unmount();host.remove();};
}

export function mountSetup() {
  const legacy=window.FactSetupLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка заправки');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента заправки: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#sg-day').closest('.bar') as HTMLElement;
  const noteDay=element<HTMLElement>('#sg-note-day');
  const table=element<HTMLTableElement>('#sg-table');
  const fillBtn=element<HTMLButtonElement>('#sg-fill'),rowBtn=element<HTMLButtonElement>('#sg-row'),sameBtn=element<HTMLButtonElement>('#sg-same');
  const yarnBar=element<HTMLElement>('#yarn-new').closest('.bar') as HTMLElement;
  const yarnTableBody=element<HTMLElement>('#yarn-table tbody');
  [topBar,noteDay,table,yarnBar,yarnTableBody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactSetup='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Setup topBar={topBar} noteDay={noteDay} table={table} fillBtn={fillBtn} rowBtn={rowBtn} sameBtn={sameBtn}
      yarnBar={yarnBar} yarnTableBody={yarnTableBody} state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new SetupController({
    requestGrid:(day,signal)=>requestSetupGrid(day,legacy.expire,signal),
    postYarn:body=>postYarn(body,legacy.expire),
    postYarnUpdate:body=>postYarnUpdate(body,legacy.expire),
    uploadYarns:file=>uploadYarnsFile(file,legacy.expire),
    confirmSetup:payload=>window.FactReactReport!.confirm('setup',payload),
    changed:render,say:legacy.say,
    yarns:()=>legacy.yarns(),refreshYarns:()=>legacy.refreshYarns(),
    confirmDiscard:text=>window.confirm(tr(text)),
  });
  window.FactSetupReact={
    load:force=>{void controller.load(force);},
    yarnsChanged:()=>render(),
  };
  render();
  if(!element('#tab-setup').classList.contains('hidden'))void controller.load(true);
  return ()=>{controller.dispose();delete window.FactSetupReact;root.unmount();host.remove();};
}

export function mountDash() {
  const legacy=window.FactDashLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка дашборда');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента дашборда: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#dash-day').closest('.bar') as HTMLElement;
  const tiles=element<HTMLElement>('#dash-tiles'),note=element<HTMLElement>('#dash-note');
  const warnEl=element<HTMLDetailsElement>('#dash-warn'),soon=element<HTMLElement>('#dash-soon');
  const tbody=element<HTMLElement>('#dash-table tbody');
  [topBar,tiles,note,warnEl,soon,tbody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactDash='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Dash topBar={topBar} tiles={tiles} note={note} warnEl={warnEl} soon={soon} tbody={tbody}
      state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new DashController({
    requestDashboard:(day,shift,signal)=>requestDashboard(day,shift,legacy.expire,signal),
    requestForecast:signal=>requestForecast(legacy.expire,signal),
    postLoomArticle:(loom,productCode,day)=>postLoomArticle(loom,productCode,day,legacy.expire),
    changed:render,say:legacy.say,
  });
  window.FactDashReact={
    setDays:days=>controller.setDays(days),
    load:()=>{void controller.load();void controller.loadSoon();},
  };
  render();
  if(!element('#tab-dash').classList.contains('hidden')){void controller.load();void controller.loadSoon();}
  return ()=>{controller.dispose();delete window.FactDashReact;root.unmount();host.remove();};
}
