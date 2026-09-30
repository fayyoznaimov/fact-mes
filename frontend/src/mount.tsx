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
import type { DocsBridge } from './features/docs/bridge';
import { Docs } from './features/docs/Docs';
import { DocsController, requestDocuments, requestDocKinds, requestChangeLog, requestDoc, requestVerify, postCancel } from './features/docs/controller';
import type { SalaryBridge } from './features/salary/bridge';
import { Salary } from './features/salary/Salary';
import { SalaryController, requestSalary, postAssignOne, postAssignCopy } from './features/salary/controller';
import type { AssignBridge } from './features/assign/bridge';
import { Assign } from './features/assign/Assign';
import { AssignController, requestShiftDoc, requestWeeklyDocs, postShiftDoc, postShiftDocConfirm, postShiftDocFill } from './features/assign/controller';
import type { PeopleBridge } from './features/people/bridge';
import { People } from './features/people/People';
import { PeopleController, requestOperators as requestOperatorList, postOperator, postOperatorDelete, postOperatorsImport, postOperatorsImportFact } from './features/people/controller';
import type { ExplorerBridge } from './features/explorer/bridge';
import { Explorer } from './features/explorer/Explorer';
import { ExplorerController, requestExplorer } from './features/explorer/controller';
import type { WalkBridge } from './features/walk/bridge';
import { Walk } from './features/walk/Walk';
import { WalkController, requestWalk } from './features/walk/controller';
import type { ManualBridge } from './features/manual/bridge';
import { Manual } from './features/manual/Manual';
import { ManualController, requestManual } from './features/manual/controller';
import type { TicketsBridge } from './features/tickets/bridge';
import { Tickets } from './features/tickets/Tickets';
import { TicketsController, requestTickets, requestLive, postTicketNew, postTicketClose, postTicketClassify } from './features/tickets/controller';
import type { HistoryBridge } from './features/history/bridge';
import { History } from './features/history/History';
import { HistoryController, requestHistory, requestSignals } from './features/history/controller';
import type { SettingsBridge } from './features/settings/bridge';
import { Rate } from './features/settings/rate/Rate';
import { RateController, requestRates } from './features/settings/rate/controller';
import { Reasons } from './features/settings/reasons/Reasons';
import { ReasonsController, requestReasons } from './features/settings/reasons/controller';
import { Andon } from './features/settings/andon/Andon';
import { AndonController, postAndonSettings } from './features/settings/andon/controller';
import type { AndonValues } from './features/settings/andon/model';
import { Keys } from './features/settings/keys/Keys';
import { KeysController, requestKeys, postKey, postKeyRevoke } from './features/settings/keys/controller';

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
    FactDocsLegacy?: DocsBridge;
    FactDocsReact?: {load:()=>void;open:(id:number)=>void;showList:(kind:'payroll'|'report')=>void};
    FactSalaryLegacy?: SalaryBridge;
    FactSalaryReact?: {setShifts:(shifts:{day:string;shift:string}[])=>void;load:()=>void;copy:()=>void};
    FactAssignLegacy?: AssignBridge;
    FactAssignReact?: {load:()=>void};
    FactPeopleLegacy?: PeopleBridge;
    FactPeopleReact?: {load:()=>void};
    FactExplorerLegacy?: ExplorerBridge;
    FactExplorerReact?: {setDays:(days:string[])=>void;load:()=>void};
    FactWalkLegacy?: WalkBridge;
    FactWalkReact?: {setShifts:(shifts:{day:string;shift:string}[])=>void;load:()=>void};
    FactManualLegacy?: ManualBridge;
    FactManualReact?: {setDays:(days:string[])=>void;load:()=>void};
    FactTicketsLegacy?: TicketsBridge;
    FactTicketsReact?: {load:()=>void};
    FactHistoryLegacy?: HistoryBridge;
    FactHistoryReact?: {load:()=>void;clear:()=>void};
    FactSettingsLegacy?: SettingsBridge;
    FactRateReact?: {load:()=>void};
    FactReasonsReact?: {load:()=>void};
    FactAndonReact?: {setValues:(values:AndonValues)=>void};
    FactKeysReact?: {load:()=>void};
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

export function mountDocs() {
  const legacy=window.FactDocsLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка документов');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента документов: '+selector);return el;
  };
  const kindsBar=element<HTMLElement>('#dx-kinds');
  const filterBar=element<HTMLElement>('#dx-from').closest('.dx-filter') as HTMLElement;
  const newBar=element<HTMLElement>('#dx-new');
  const items=element<HTMLElement>('#dx-items'),form=element<HTMLElement>('#dx-form');
  [kindsBar,filterBar,newBar,items,form].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactDocs='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Docs kindsBar={kindsBar} filterBar={filterBar} newBar={newBar} items={items} form={form}
      state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new DocsController({
    requestDocuments:(kind,from,to,signal)=>requestDocuments(kind,from,to,legacy.expire,signal),
    requestDocKinds:()=>requestDocKinds(legacy.expire),
    requestChangeLog:(from,to,q,entity,signal)=>requestChangeLog(from,to,q,entity,legacy.expire,signal),
    requestDoc:(id,signal)=>requestDoc(id,legacy.expire,signal),
    requestVerify:id=>requestVerify(id,legacy.expire),
    postCancel:(id,reason)=>postCancel(id,reason,legacy.expire),
    docConfirm:(type,payload)=>legacy.docConfirm(type,payload),
    changed:render,say:legacy.say,
  });
  window.FactDocsReact={
    load:()=>{void controller.load();},
    open:id=>{void controller.openDoc(id);},
    showList:kind=>{controller.setKind(kind);},
  };
  render();
  if(!element('#tab-docs').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactDocsReact;root.unmount();host.remove();};
}

export function mountSalary() {
  const legacy=window.FactSalaryLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка зарплаты');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента зарплаты: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#sal-shift').closest('.bar') as HTMLElement;
  const tiles=element<HTMLElement>('#sal-tiles'),note=element<HTMLElement>('#sal-note');
  const tableBody=element<HTMLElement>('#sal-table tbody'),tableFoot=element<HTMLElement>('#sal-table tfoot');
  const loomsBody=element<HTMLElement>('#sal-looms tbody'),loomsFoot=element<HTMLElement>('#sal-looms tfoot');
  [topBar,tiles,note,tableBody,tableFoot,loomsBody,loomsFoot].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactSalary='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Salary topBar={topBar} tiles={tiles} note={note} tableBody={tableBody} tableFoot={tableFoot}
      loomsBody={loomsBody} loomsFoot={loomsFoot} state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new SalaryController({
    requestSalary:(day,shift,signal)=>requestSalary(day,shift,legacy.expire,signal),
    postAssignOne:(day,shift,loom,operatorId)=>postAssignOne(day,shift,loom,operatorId,legacy.expire),
    postAssignCopy:(day,shift)=>postAssignCopy(day,shift,legacy.expire),
    changed:render,say:legacy.say,
  });
  window.FactSalaryReact={
    setShifts:shifts=>controller.setShifts(shifts),
    load:()=>{void controller.load();},
    copy:()=>{void controller.copy();},
  };
  render();
  if(!element('#tab-salary').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactSalaryReact;root.unmount();host.remove();};
}

export function mountAssign() {
  const legacy=window.FactAssignLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка расстановки');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента расстановки: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#as-day').closest('.bar') as HTMLElement;
  const status=element<HTMLElement>('#as-status');
  const pickerBar=element<HTMLElement>('#as-picker').closest('.bar') as HTMLElement;
  const mapEl=element<HTMLElement>('#as-map');
  const allCheckbox=element<HTMLElement>('#as-all').parentElement as HTMLElement;
  const tableBody=element<HTMLElement>('#as-table tbody');
  const sidePanel=element<HTMLElement>('#as-note').closest('.bar') as HTMLElement;
  const weeklyBody=element<HTMLElement>('#as-docs tbody');
  [topBar,status,pickerBar,mapEl,allCheckbox,tableBody,sidePanel,weeklyBody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactAssign='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Assign topBar={topBar} status={status} pickerBar={pickerBar} mapEl={mapEl} allCheckbox={allCheckbox}
      tableBody={tableBody} sidePanel={sidePanel} weeklyBody={weeklyBody}
      state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new AssignController({
    requestDoc:(day,shift,signal)=>requestShiftDoc(day,shift,legacy.expire,signal),
    requestWeekly:(from,to,signal)=>requestWeeklyDocs(from,to,legacy.expire,signal),
    postSave:payload=>postShiftDoc(payload,legacy.expire),
    postConfirm:(day,shift,confirmed)=>postShiftDocConfirm(day,shift,confirmed,legacy.expire),
    postFill:(day,shift,how)=>postShiftDocFill(day,shift,how,legacy.expire),
    operators:()=>legacy.operators(),
    me:()=>legacy.me(),
    confirmTranslated:text=>legacy.confirmTranslated(text),
    fday:legacy.fday, ftime:legacy.ftime,
    openPrintWindow:html=>legacy.openPrintWindow(html),
    changed:render, say:legacy.say,
  });
  window.FactAssignReact={load:()=>{void controller.load();}};
  render();
  if(!element('#tab-assign').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactAssignReact;root.unmount();host.remove();};
}

export function mountPeople() {
  const legacy=window.FactPeopleLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка операторов');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента операторов: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#op-code').closest('.bar') as HTMLElement;
  const pasteBar=element<HTMLElement>('#op-paste').closest('.bar') as HTMLElement;
  const tableBody=element<HTMLElement>('#op-table tbody');
  [topBar,pasteBar,tableBody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactPeople='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <People topBar={topBar} pasteBar={pasteBar} tableBody={tableBody} state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new PeopleController({
    operators:()=>legacy.operators(),
    requestOperators:()=>requestOperatorList(legacy.expire),
    postOperator:body=>postOperator(body,legacy.expire),
    postDelete:id=>postOperatorDelete(id,legacy.expire),
    postImport:text=>postOperatorsImport(text,legacy.expire),
    postImportFact:()=>postOperatorsImportFact(legacy.expire),
    confirmTranslated:text=>legacy.confirmTranslated(text),
    setOperators:ops=>legacy.setOperators(ops),
    changed:render, say:legacy.say,
  });
  window.FactPeopleReact={load:()=>controller.load()};
  render();
  return ()=>{delete window.FactPeopleReact;root.unmount();host.remove();};
}

export function mountExplorer() {
  const legacy=window.FactExplorerLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка простоев');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента простоев: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#ex-from').closest('.bar') as HTMLElement;
  const tiles=element<HTMLElement>('#ex-tiles'),stack=element<HTMLElement>('#ex-stack'),legendEl=element<HTMLElement>('#ex-legend');
  const tableBody=element<HTMLElement>('#ex-table tbody');
  [topBar,tiles,stack,legendEl,tableBody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactExplorer='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Explorer topBar={topBar} tiles={tiles} stack={stack} legend={legendEl} tableBody={tableBody}
      state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new ExplorerController({
    requestExplorer:(from,to,shifts,group,signal)=>requestExplorer(from,to,shifts,group,legacy.expire,signal),
    changed:render, say:legacy.say,
  });
  window.FactExplorerReact={setDays:days=>controller.setDays(days),load:()=>{void controller.load();}};
  render();
  if(!element('#tab-explorer').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactExplorerReact;root.unmount();host.remove();};
}

export function mountWalk() {
  const legacy=window.FactWalkLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка обхода цеха');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента обхода цеха: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#wk-shift').closest('.bar') as HTMLElement;
  const tableBody=element<HTMLElement>('#wk-table tbody');
  [topBar,tableBody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactWalk='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Walk topBar={topBar} tableBody={tableBody} state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new WalkController({
    requestWalk:(day,shift,signal)=>requestWalk(day,shift,legacy.expire,signal),
    changed:render, say:legacy.say,
  });
  window.FactWalkReact={setShifts:shifts=>controller.setShifts(shifts),load:()=>{void controller.load();}};
  render();
  if(!element('#tab-walk').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactWalkReact;root.unmount();host.remove();};
}

export function mountManual() {
  const legacy=window.FactManualLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка ручных остановов');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента ручных остановов: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#mn-from').closest('.bar') as HTMLElement;
  const reasonBtn=element<HTMLElement>('#mn-reason').parentElement as HTMLElement;
  const tiles=element<HTMLElement>('#mn-tiles');
  const thead=element<HTMLElement>('#mn-table thead'),tableBody=element<HTMLElement>('#mn-table tbody'),tableFoot=element<HTMLElement>('#mn-table tfoot');
  [topBar,reasonBtn,tiles,thead,tableBody,tableFoot].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactManual='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Manual topBar={topBar} reasonBtn={reasonBtn} tiles={tiles} thead={thead} tableBody={tableBody} tableFoot={tableFoot}
      state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new ManualController({
    requestManual:(from,to,group,signal)=>requestManual(from,to,group,legacy.expire,signal),
    changed:render, say:legacy.say,
  });
  window.FactManualReact={setDays:days=>controller.setDays(days),load:()=>{void controller.load();}};
  render();
  if(!element('#tab-manual').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactManualReact;root.unmount();host.remove();};
}

export function mountTickets() {
  const legacy=window.FactTicketsLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка тикетов');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента тикетов: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#tk-from').closest('.bar') as HTMLElement;
  const needPar=element<HTMLElement>('#tk-need');
  const tiles=element<HTMLElement>('#tk-tiles');
  const thead=element<HTMLElement>('#tk-table thead'),tableBody=element<HTMLElement>('#tk-table tbody');
  const dialog=element<HTMLDialogElement>('#tk-cat-dlg');
  const dialogTitle=element<HTMLElement>('#tk-cat-title'),dialogInfo=element<HTMLElement>('#tk-cat-info'),dialogList=element<HTMLElement>('#tk-cat-list');
  [topBar,needPar,tiles,thead,tableBody,dialogTitle,dialogInfo,dialogList].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactTickets='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <Tickets topBar={topBar} needPar={needPar} tiles={tiles} thead={thead} tableBody={tableBody}
      dialog={dialog} dialogTitle={dialogTitle} dialogInfo={dialogInfo} dialogList={dialogList}
      state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new TicketsController({
    requestTickets:(from,to,openOnly,signal)=>requestTickets(from,to,openOnly,legacy.expire,signal),
    requestLive:signal=>requestLive(legacy.expire,signal),
    postNew:loom=>postTicketNew(loom,legacy.expire),
    postClose:id=>postTicketClose(id,legacy.expire),
    postClassify:(id,categoryId,was)=>postTicketClassify(id,categoryId,was,legacy.expire),
    changed:render, say:legacy.say,
  });
  window.FactTicketsReact={load:()=>{void controller.load();}};
  render();
  if(!element('#tab-tickets').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactTicketsReact;root.unmount();host.remove();};
}

export function mountHistory() {
  const legacy=window.FactHistoryLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка истории станков');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента истории станков: '+selector);return el;
  };
  const topBar=element<HTMLElement>('#mh-day').closest('.bar') as HTMLElement;
  const legendEl=element<HTMLElement>('#mh-legend'),status=element<HTMLElement>('#mh-status');
  const gridWrap=element<HTMLElement>('#mh-grid').parentElement as HTMLElement;
  const detail=element<HTMLElement>('#mh-detail');
  [topBar,legendEl,status,gridWrap,detail].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactHistory='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(
    <History topBar={topBar} legend={legendEl} status={status} gridWrap={gridWrap} detail={detail}
      state={controller.state} bridge={legacy} controller={controller}/>
  ));
  const controller=new HistoryController({
    requestHistory:(day,period,looms,signal)=>requestHistory(day,period,looms,legacy.expire,signal),
    requestSignals:(loom,day,period,signal)=>requestSignals(loom,day,period,legacy.expire,signal),
    changed:render, say:legacy.say,
  });
  window.FactHistoryReact={load:()=>{void controller.load();},clear:()=>controller.clear()};
  render();
  if(!element('#tab-history').classList.contains('hidden'))void controller.load();
  return ()=>{controller.dispose();delete window.FactHistoryReact;root.unmount();host.remove();};
}

export function mountSettings() {
  const legacy=window.FactSettingsLegacy;
  if(!legacy)throw new Error('Не загружена исходная оболочка настроек');
  const element=<T extends Element>(selector:string)=>{
    const el=document.querySelector<T>(selector);if(!el)throw new Error('Нет элемента настроек: '+selector);return el;
  };
  const rateBar=element<HTMLElement>('#set-from').closest('.bar') as HTMLElement;
  const rateBody=element<HTMLElement>('#set-rates tbody');
  const reasonsBar=element<HTMLElement>('#rs-add').closest('.bar') as HTMLElement;
  const reasonsBody=element<HTMLElement>('#rs-table tbody');
  const andonBar=element<HTMLElement>('#an-warn').closest('.bar') as HTMLElement;
  const keysBar=element<HTMLElement>('#key-name').closest('.bar') as HTMLElement;
  const keysReveal=element<HTMLElement>('#key-new');
  const keysBody=element<HTMLElement>('#key-table tbody');
  [rateBar,rateBody,reasonsBar,reasonsBody,andonBar,keysBar,keysReveal,keysBody].forEach(t=>t.replaceChildren());
  const host=document.createElement('div');host.hidden=true;host.dataset.reactSettings='';document.body.appendChild(host);
  const root=createRoot(host);
  const render=()=>flushSync(()=>root.render(<>
    <Rate topBar={rateBar} tableBody={rateBody} state={rate.state} bridge={legacy} controller={rate}/>
    <Reasons topBar={reasonsBar} tableBody={reasonsBody} state={reasons.state} bridge={legacy}/>
    <Andon topBar={andonBar} state={andon.state} controller={andon}/>
    <Keys topBar={keysBar} revealBox={keysReveal} tableBody={keysBody} state={keys.state} bridge={legacy} controller={keys}/>
  </>));
  const rate=new RateController({requestRates:()=>requestRates(legacy.expire),confirmRate:p=>legacy.confirmRate(p),changed:render,say:legacy.say});
  const reasons=new ReasonsController({requestReasons:()=>requestReasons(legacy.expire),setReasonsData:data=>legacy.setReasonsData(data),changed:render,say:legacy.say});
  const andon=new AndonController({postSettings:v=>postAndonSettings(v,legacy.expire),changed:render,say:legacy.say});
  const keys=new KeysController({
    can:legacy.can,
    requestKeys:()=>requestKeys(legacy.expire),
    postKey:(name,scopes)=>postKey(name,scopes,legacy.expire),
    postRevoke:id=>postKeyRevoke(id,legacy.expire),
    confirmTranslated:legacy.confirmTranslated,
    changed:render,say:legacy.say,
  });
  window.FactRateReact={load:()=>{void rate.load();}};
  window.FactReasonsReact={load:()=>{void reasons.load();}};
  window.FactAndonReact={setValues:values=>andon.setValues(values)};
  window.FactKeysReact={load:()=>{void keys.load();}};
  render();
  return ()=>{
    delete window.FactRateReact;delete window.FactReasonsReact;delete window.FactAndonReact;delete window.FactKeysReact;
    root.unmount();host.remove();
  };
}
