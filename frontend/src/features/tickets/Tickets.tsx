import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { TicketsBridge } from './bridge';
import { buildTiles, dur, shortTime, visibleRows } from './model';
import type { Filter, LiveResponse, Sort, SortKey, Ticket } from './model';
import type { TicketsController, TicketsState } from './controller';

type Props = {
  topBar: HTMLElement; needPar: HTMLElement; tiles: HTMLElement;
  thead: HTMLElement; tableBody: HTMLElement; dialog: HTMLDialogElement;
  dialogTitle: HTMLElement; dialogInfo: HTMLElement; dialogList: HTMLElement;
  state: TicketsState; bridge: TicketsBridge; controller: TicketsController;
};

export function Tickets({topBar, needPar, tiles, thead, tableBody, dialog, dialogTitle, dialogInfo, dialogList,
  state, bridge, controller}: Props) {
  const rows = visibleRows(state.tickets, state.shift, state.looms, state.filter, state.sort);
  return <>
    {createPortal(<TopBar state={state} controller={controller}/>, topBar)}
    {state.loaded && createPortal(<NeedTickets live={state.live} controller={controller}/>, needPar)}
    {state.loaded && createPortal(<Tiles rows={rows} live={state.live}/>, tiles)}
    {createPortal(<Thead sort={state.sort} controller={controller}/>, thead)}
    {state.loaded && createPortal(<TableRows rows={rows} show={state.show} canEdit={state.canEdit} bridge={bridge} controller={controller}/>, tableBody)}
    <CategoryDialog dialog={dialog} pick={state.pick} controller={controller}/>
    {createPortal(state.pick ? `${tr('Причина простоя')} · ${state.pick.loom} · № ${state.pick.id}` : '', dialogTitle)}
    {createPortal(state.pick ? <>{shortTime(bridge.ftime, state.pick.started_at)}, {tr('простой')} {dur(state.pick.duration_sec)}.
      {' '}{tr('Станок сообщает')}: {state.pick.cause_ru || '—'}.</> : '', dialogInfo)}
    {createPortal(<CategoryList pick={state.pick} categories={state.categories} controller={controller}/>, dialogList)}
  </>;
}

function TopBar({state, controller}: {state: TicketsState; controller: TicketsController}) {
  return <>
    <div className="f"><label>{tr('Монитор в цехе')}</label>
      <a className="act primary" href="/wall" target="_blank" rel="noreferrer" style={{textDecoration: 'none'}}>{tr('Открыть доску')}</a></div>
    <div className="f"><label htmlFor="tk-from">{tr('С')}</label>
      <input id="tk-from" type="date" value={state.from} onChange={e => controller.setFrom(e.target.value)}/></div>
    <div className="f"><label htmlFor="tk-to">{tr('По')}</label>
      <input id="tk-to" type="date" value={state.to} onChange={e => controller.setTo(e.target.value)}/></div>
    <div className="f"><label htmlFor="tk-shift">{tr('Смена')}</label>
      <select id="tk-shift" value={state.shift} onChange={e => controller.setShift(e.target.value)}>
        <option value="">{tr('все')}</option><option>A</option><option>B</option><option>C</option>
      </select></div>
    <div className="f"><label htmlFor="tk-looms">{tr('Станки')}</label>
      <input id="tk-looms" size={10} placeholder="D, J1-J14" autoComplete="off"
        value={state.looms} onChange={e => controller.setLooms(e.target.value)}/></div>
    <div className="f"><label htmlFor="tk-filter">{tr('Показывать')}</label>
      <select id="tk-filter" value={state.filter} onChange={e => controller.setFilter(e.target.value as Filter)}>
        <option value="all">{tr('все')}</option><option value="open">{tr('открытые')}</option>
        <option value="noreason">{tr('без причины')}</option>
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="tk-reload" onClick={() => {void controller.load();}}>{tr('Обновить')}</button></div>
  </>;
}

function NeedTickets({live, controller}: {live: LiveResponse | null; controller: TicketsController}) {
  const need = (live?.looms || []).filter(l => l.needs_ticket);
  if (!need.length) return <>{tr('Станков, которые стоят без объяснения, сейчас нет.')}</>;
  return <>{tr('Стоят без объяснения и ждут тикета')}: {need.map(l => <button key={l.loom} type="button" className="chip"
    onClick={() => {void controller.newTicket(l.loom);}}>
    {l.loom} · {l.cause_ru} · {dur(l.state_sec)}</button>)}</>;
}

function Tiles({rows, live}: {rows: Ticket[]; live: LiveResponse | null}) {
  const tiles = buildTiles(rows, live?.totals.stopped ?? null);
  return <>{tiles.map((it, i) => <div className="tile" key={i}>
    <div className="l">{it.label}</div>
    <div className="v">{it.value}{it.sub ? <small> · {it.sub}</small> : null}</div>
  </div>)}</>;
}

const SORT_COLUMNS: {k: SortKey; label: string; n?: boolean}[] = [
  {k: 'loom', label: 'Станок'}, {k: 'started_at', label: 'Начало'}, {k: 'shift', label: 'Смена'},
  {k: 'duration_sec', label: 'Простой', n: true}, {k: 'cause_ru', label: 'Сигнал станка'},
  {k: 'reason', label: 'Причина в отчёте'},
];

function Thead({sort, controller}: {sort: Sort; controller: TicketsController}) {
  const arrow = (k: SortKey) => sort.k === k ? (sort.dir > 0 ? ' ▲' : ' ▼') : '';
  return <tr>
    {SORT_COLUMNS.map(c => <th key={c.k} className={c.n ? 'n' : undefined} style={{cursor: 'pointer'}}
      onClick={() => controller.toggleSort(c.k)}>{tr(c.label)}{arrow(c.k)}</th>)}
    <th>{tr('Откуда')}</th>
    <th style={{cursor: 'pointer'}} onClick={() => controller.toggleSort('category_name')}>{tr('Категория')}{arrow('category_name')}</th>
    <th/>
  </tr>;
}

function TableRows({rows, show, canEdit, bridge, controller}: {
  rows: Ticket[]; show: number; canEdit: boolean; bridge: TicketsBridge; controller: TicketsController;
}) {
  if (!rows.length) return <tr><td className="note" colSpan={9}>{tr('За выбранный период тикетов нет.')}</td></tr>;
  const shown = rows.slice(0, show);
  return <>
    {shown.map(r => <Row key={r.id} r={r} canEdit={canEdit} bridge={bridge} controller={controller}/>)}
    {rows.length > shown.length ? <tr><td colSpan={9}>
      <button className="act" onClick={() => controller.showMore()}>
        {tr('Показать ещё')} {Math.min(100, rows.length - shown.length)} · {tr('осталось')} {rows.length - shown.length}
      </button></td></tr> : null}
  </>;
}

function Row({r, canEdit, bridge, controller}: {r: Ticket; canEdit: boolean; bridge: TicketsBridge; controller: TicketsController}) {
  return <tr>
    <td>{r.loom} <button className="act" data-ticket-audit={r.id} title={tr('История тикета')}>№ {r.id}</button></td>
    <td className="n">{shortTime(bridge.ftime, r.started_at)}</td>
    <td>{(r.shift || '').slice(-1)}</td>
    <td className="n">{dur(r.duration_sec)}</td>
    <td>{r.cause_ru || '—'}</td>
    <td>{r.reason}</td>
    <td>{r.reason_from}</td>
    <td>{canEdit
      ? <button className={'act' + (r.category_id ? '' : ' need')} onClick={() => controller.openCategoryDialog(r)}>
          {r.category_name || tr('— выбрать —')}</button>
      : (r.category_name || '—')}</td>
    <td>{r.open && canEdit ? <button className="act" onClick={() => {void controller.closeTicket(r.id);}}>{tr('Закрыть')}</button>
      : (r.open ? <span className="ok">{tr('открыт')}</span> : null)}</td>
  </tr>;
}

function CategoryDialog({dialog, pick, controller}: {dialog: HTMLDialogElement; pick: Ticket | null; controller: TicketsController}) {
  useEffect(() => {
    const onClose = () => controller.closeCategoryDialog();
    dialog.addEventListener('close', onClose);
    return () => dialog.removeEventListener('close', onClose);
  }, [dialog, controller]);
  useEffect(() => {
    if (pick && !dialog.open) dialog.showModal();
    if (!pick && dialog.open) dialog.close();
  }, [pick, dialog]);
  return null;
}

function CategoryList({pick, categories, controller}: {pick: Ticket | null; categories: TicketsState['categories']; controller: TicketsController}) {
  if (!pick) return null;
  return <>{categories.map(c => <button key={c.id} type="button" className={'act' + (c.id === pick.category_id ? ' primary' : '')}
    onClick={() => {void controller.pickCategory(c.id);}}>{c.name}</button>)}</>;
}
