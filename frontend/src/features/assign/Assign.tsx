import { Fragment, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { AssignBridge } from './bridge';
import {
  buildSummary, dash2dot, dot2dash, editableOperators, foremenOptions, hueOf, isLocked, mapLayout,
  mastersOptions, opLabel, ownMasterOf, toRows,
} from './model';
import type { DocSummary, ShiftDoc } from './model';
import type { AssignController, AssignState, Edits } from './controller';

type Props = {
  topBar: HTMLElement; status: HTMLElement; pickerBar: HTMLElement; mapEl: HTMLElement;
  allCheckbox: HTMLElement; tableBody: HTMLElement; sidePanel: HTMLElement; weeklyBody: HTMLElement;
  state: AssignState; bridge: AssignBridge; controller: AssignController;
};

export function Assign({topBar, status, pickerBar, mapEl, allCheckbox, tableBody, sidePanel, weeklyBody, state, bridge, controller}: Props) {
  const data = state.data;
  const locked = isLocked(data?.doc ?? null);
  const editable = bridge.can('assign') && !locked;
  const ownMaster = ownMasterOf(bridge.me());
  return <>
    {createPortal(<TopBar state={state} bridge={bridge} controller={controller} locked={locked} editable={editable}/>, topBar)}
    {data && createPortal(<StatusLine data={data} bridge={bridge} locked={locked}/>, status)}
    {data && createPortal(<Picker state={state} bridge={bridge} controller={controller} editable={editable}/>, pickerBar)}
    {data && createPortal(<MapView data={data} edits={state.edits} checked={state.checked} bridge={bridge} controller={controller} editable={editable}/>, mapEl)}
    {data && createPortal(<AllCheckbox data={data} checked={state.checked} controller={controller} editable={editable}/>, allCheckbox)}
    {data && createPortal(<TableRows data={data} edits={state.edits} checked={state.checked} bridge={bridge} controller={controller} editable={editable}/>, tableBody)}
    {data && createPortal(<SidePanel data={data} edits={state.edits} bridge={bridge} controller={controller} editable={editable} ownMaster={ownMaster}/>, sidePanel)}
    {createPortal(<WeeklyDocs weekly={state.weekly} day={dash2dot(state.day)} shift={state.shift} bridge={bridge} controller={controller}/>, weeklyBody)}
  </>;
}

function TopBar({state, bridge, controller, locked, editable}: {
  state: AssignState; bridge: AssignBridge; controller: AssignController; locked: boolean; editable: boolean;
}) {
  return <>
    <div className="f"><label htmlFor="as-day">{tr('День')}</label>
      <input id="as-day" type="date" value={state.day} onChange={e => controller.setDay(e.target.value)}/></div>
    <div className="f"><label>{tr('Смена')}</label>
      <div className="chips" id="as-shifts">
        {[['A', 'A · 07–15'], ['B', 'B · 15–23'], ['C', 'C · 23–07']].map(([sh, label]) =>
          <button key={sh} type="button" className="chip" aria-pressed={state.shift === sh}
            onClick={() => controller.setShift(sh)}>{label}</button>)}
      </div></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="as-save" disabled={!editable} onClick={() => {void controller.save();}}>{tr('Сохранить')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="as-confirm" disabled={!bridge.can('assign')} onClick={() => {void controller.confirm();}}>
        {locked ? tr('Открыть для правки') : tr('Утвердить')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="as-print" onClick={() => controller.print()}>{tr('Печать')}</button></div>
    <button className="act" id="as-history" onClick={() => bridge.openHistory(dash2dot(state.day), state.shift)}>
      {tr('История расстановки')}</button>
  </>;
}

function StatusLine({data, bridge, locked}: {data: ShiftDoc; bridge: AssignBridge; locked: boolean}) {
  const doc = data.doc;
  const when = (t: string | null | undefined) => t ? bridge.ftime(t) : '';
  return <>
    <b>{tr('Расстановка смены')} {data.shift} {tr('за')} {bridge.fday(data.day)}</b> · {data.hours} · {
      locked ? <><span className="ok">{tr('утверждена')}</span> {doc?.confirmed_by || ''} {when(doc?.confirmed_at)}</> : tr('черновик')
    }{doc?.source ? <> · {tr('заполнена')}: {doc.source}</> : null}
    {doc?.updated_by ? <> · {tr('правил')} {doc.updated_by} {when(doc.updated_at)}</> : null}
  </>;
}

function Picker({state, bridge, controller, editable}: {
  state: AssignState; bridge: AssignBridge; controller: AssignController; editable: boolean;
}) {
  const pickerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) controller.closeSuggestions();
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, [controller]);
  const suggestions = state.suggestOpen ? controller.suggestionList() : [];
  const picked = state.bulkId ? bridge.operators().find(o => String(o.id) === state.bulkId) : null;
  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { controller.closeSuggestions(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      controller.moveSuggestion(e.key === 'ArrowDown' ? 1 : -1);
    } else if (e.key === 'Enter' && state.suggestOpen) {
      e.preventDefault();
      const list = controller.suggestionList();
      const op = list[Math.max(0, state.suggestIndex)];
      if (op) controller.pickOperator(op);
    }
  };
  return <>
    <div className="f" id="as-picker" style={{position: 'relative', minWidth: 280}} ref={pickerRef}>
      <label htmlFor="as-search">{tr('Оператор для отмеченных станков')}</label>
      <input id="as-search" type="search" role="combobox" aria-autocomplete="list"
        aria-expanded={state.suggestOpen} aria-controls="as-suggestions"
        {...(state.suggestIndex >= 0 ? {'aria-activedescendant': `as-option-${state.suggestIndex}`} : {})}
        placeholder={tr('Введите код или имя')} autoComplete="off"
        value={state.search} onChange={e => controller.setSearch(e.target.value)}
        onFocus={() => controller.openSuggestions()} onKeyDown={onKeyDown}/>
      <div id="as-suggestions" role="listbox" className={state.suggestOpen ? '' : 'hidden'}
        style={{position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 30, background: 'white',
          border: '1px solid #cbd5e1', borderRadius: 8, boxShadow: '0 6px 20px #0002', maxHeight: 260, overflow: 'auto'}}>
        {suggestions.length ? suggestions.map((o, i) =>
          <button type="button" role="option" key={o.id} id={`as-option-${i}`} aria-selected={i === state.suggestIndex}
            style={{display: 'block', width: '100%', textAlign: 'left', padding: 10, border: 0, borderRadius: 0,
              background: i === state.suggestIndex ? '#dbeafe' : 'white', color: '#182333'}}
            onClick={() => controller.pickOperator(o)}><b>{o.code}</b> — {o.name}</button>)
          : <div style={{padding: 10}}>{tr('Оператор не найден')}</div>}
      </div>
      <span id="as-picked" className="note" aria-live="polite">{picked ? `${picked.code} — ${picked.name}` : ''}</span>
    </div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="as-apply" disabled={!editable} onClick={() => controller.applyBulk()}>{tr('Назначить')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="as-prev" disabled={!editable} onClick={() => {void controller.fill('prev');}}>{tr('Как в прошлую такую смену')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="as-fact" disabled={!editable} onClick={() => {void controller.fill('fact');}}>{tr('Из FACT')}</button></div>
  </>;
}

function MapView({data, edits, checked, bridge, controller, editable}: {
  data: ShiftDoc; edits: Edits; checked: Set<string>; bridge: AssignBridge; controller: AssignController; editable: boolean;
}) {
  const looms = data.assignments.map(a => a.loom);
  const layout = mapLayout(data.layout, looms);
  if (!layout.cells.length) return null;
  const ops = bridge.operators();
  return <>{layout.cells.map(({loom, row, col}) => {
    const opId = edits.assignments[loom];
    const o = opId != null ? ops.find(x => x.id === opId) : null;
    const who = o ? `${o.code} · ${o.name.split(' ')[0]}` : tr('нет оператора');
    return <button key={loom} type="button" className={o ? '' : 'free'}
      style={{gridRow: layout.rows.indexOf(row) + 1, gridColumn: layout.colTrack[col], '--h': o ? hueOf(o.id) : 0} as React.CSSProperties}
      aria-pressed={checked.has(loom)} disabled={!editable}
      title={`${loom}: ${o ? o.name : tr('нет оператора')}`}
      onClick={() => controller.toggleChecked(loom)}><b>{loom}</b><span>{who}</span></button>;
  })}</>;
}

function AllCheckbox({data, checked, controller, editable}: {data: ShiftDoc; checked: Set<string>; controller: AssignController; editable: boolean}) {
  const looms = data.assignments.map(a => a.loom);
  const all = looms.length > 0 && looms.every(l => checked.has(l));
  return <input type="checkbox" id="as-all" aria-label={tr('Отметить все станки')}
    checked={all} onChange={e => controller.toggleAllChecked(e.target.checked, editable)}/>;
}

function TableRows({data, edits, checked, bridge, controller, editable}: {
  data: ShiftDoc; edits: Edits; checked: Set<string>; bridge: AssignBridge; controller: AssignController; editable: boolean;
}) {
  if (!data.assignments.length) return <tr><td colSpan={3} className="note">{tr('Станков нет.')}</td></tr>;
  const opts = editableOperators(bridge.operators(), data.assignments);
  return <>{data.assignments.map(a => <tr key={a.loom}>
    <td><input type="checkbox" aria-label={`${tr('Отметить')} ${a.loom}`} disabled={!editable}
      checked={checked.has(a.loom)} onChange={() => controller.toggleChecked(a.loom)}/></td>
    <td><strong>{a.loom}</strong></td>
    <td><select data-loom={a.loom} disabled={!editable} value={edits.assignments[a.loom] ?? ''}
      onChange={e => controller.setOperator(a.loom, e.target.value ? +e.target.value : null)}>
      <option value="">—</option>
      {opts.map(o => <option key={o.id} value={o.id}>{opLabel(o)}</option>)}
    </select></td>
  </tr>)}</>;
}

function SidePanel({data, edits, bridge, controller, editable, ownMaster}: {
  data: ShiftDoc; edits: Edits; bridge: AssignBridge; controller: AssignController; editable: boolean; ownMaster: number | null;
}) {
  const operators = bridge.operators();
  const foremen = foremenOptions(operators, edits.foremanId);
  const masters = mastersOptions(operators, data.masters);
  const summary = buildSummary(toRows(edits.assignments), operators);
  return <>
    <div className="f hidden">
      <label htmlFor="as-foreman">{tr('Мастер смены')}</label>
      <select id="as-foreman" disabled={!editable || !!ownMaster} value={edits.foremanId ?? ''}
        onChange={e => controller.setForeman(e.target.value ? +e.target.value : null)}>
        <option value="">{tr('— не указан —')}</option>
        {foremen.map(o => <option key={o.id} value={o.id}>{opLabel(o)}</option>)}
      </select>
      <span className="note" id="as-foreman-note">
        {foremen.length ? '' : tr('Мастеров в справочнике нет — добавьте на вкладке «Операторы» с ролью «мастер».')}</span>
    </div>
    <div className="f"><label>{tr('Мастерицы смены')}</label>
      <div className="chips" id="as-masters">
        {masters.length ? masters.map(m =>
          <button key={m.id} type="button" className="chip" aria-pressed={edits.masters.includes(m.id)}
            disabled={!editable || !!ownMaster} onClick={() => controller.toggleMaster(m.id)}>{opLabel(m)}</button>)
          : <span className="note">{tr('Мастериц в справочнике нет — добавьте на вкладке «Операторы».')}</span>}
      </div></div>
    <div className="f"><label htmlFor="as-note">{tr('Примечание')}</label>
      <input id="as-note" autoComplete="off" disabled={!editable} value={edits.note}
        onChange={e => controller.setNote(e.target.value)}/></div>
    <p className="note" id="as-summary">
      {tr('Станков')} {summary.total}, {tr('с оператором')} {summary.withOperator}
      {summary.freeLooms.length ? <>; {tr('без оператора')}: {summary.freeLooms.join(', ')}</> : null}<br/>
      {tr('Операторов')} {summary.byOperator.length}{summary.byOperator.length ? ': ' : ''}
      {summary.byOperator.map((o, i) => <Fragment key={o.id}>{i > 0 ? ', ' : ''}{o.name} — {o.count}</Fragment>)}
    </p>
    <p className="note">{tr('Документы на смены A, B и C заводятся сами каждое утро и заполняются')}{' '}
      {tr('расстановкой прошлой такой же смены. Мастер правит, сохраняет и утверждает;')}{' '}
      {tr('утверждённый документ меняется только после «Открыть для правки».')}</p>
  </>;
}

function WeeklyDocs({weekly, day, shift, bridge, controller}: {
  weekly: DocSummary[]; day: string; shift: string; bridge: AssignBridge; controller: AssignController;
}) {
  if (!weekly.length) return <tr><td colSpan={4} className="note">{tr('Документов пока нет.')}</td></tr>;
  const days = [...new Set(weekly.map(d => d.day))];
  return <>{days.map(dd => <tr key={dd}>
    <td>{bridge.fday(dd)}</td>
    {(['A', 'B', 'C'] as const).map(sh => {
      const x = weekly.find(y => y.day === dd && y.shift === sh);
      if (!x) return <td key={sh} className="note">—</td>;
      return <td key={sh}>
        <button type="button" className="chip" aria-pressed={dd === day && sh === shift}
          onClick={() => controller.openDoc(dot2dash(dd), sh)}>{x.status === 'confirmed' ? `✓ ${tr('утверждена')}` : tr('черновик')}</button>{' '}
        <small className="note">{x.foreman_name ? `${x.foreman_name} · ` : ''}{x.looms} {tr('ст.')}, {x.operators} {tr('опер.')}</small>
      </td>;
    })}
  </tr>)}</>;
}
