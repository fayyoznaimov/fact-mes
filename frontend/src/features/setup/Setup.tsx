import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import type { SetupBridge } from './bridge';
import { tr } from './bridge';
import { SG_NUMS, YARN_KINDS, dash2dot, rowsDirty, yarnBad, yarnCanon, yarnKey } from './model';
import type { SetupController, SetupState } from './controller';

type Props = {
  topBar: HTMLElement;
  noteDay: HTMLElement;
  table: HTMLTableElement;
  fillBtn: HTMLButtonElement; rowBtn: HTMLButtonElement; sameBtn: HTMLButtonElement;
  yarnBar: HTMLElement; yarnTableBody: HTMLElement;
  state: SetupState;
  bridge: SetupBridge;
  controller: SetupController;
};

export function Setup({topBar, noteDay, table, fillBtn, rowBtn, sameBtn, yarnBar, yarnTableBody, state, bridge, controller}: Props) {
  const edit = bridge.can('setup_edit');
  const dirtyRef = useRef(false);
  dirtyRef.current = controller.isDirty();
  useEffect(() => {
    const onUnload = (e: BeforeUnloadEvent) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', onUnload);
    return () => window.removeEventListener('beforeunload', onUnload);
  }, []);
  useEffect(() => {
    fillBtn.onclick = () => controller.fillFocusToPicked();
    rowBtn.onclick = () => controller.copyRowToPicked();
    sameBtn.onclick = () => controller.markSameCloth();
    return () => { fillBtn.onclick = null; rowBtn.onclick = null; sameBtn.onclick = null; };
  }, [controller, fillBtn, rowBtn, sameBtn]);
  useEffect(() => {
    fillBtn.disabled = !edit; rowBtn.disabled = !edit; sameBtn.disabled = !edit;
  }, [edit, fillBtn, rowBtn, sameBtn]);

  const showNoteDay = !!state.reportDay && state.reportDay !== dash2dot(state.day);
  return <>
    {createPortal(<TopBar state={state} controller={controller} edit={edit}/>, topBar)}
    {createPortal(showNoteDay ? `${tr('Справочные значения — из отчёта за')} ${bridge.fday(state.reportDay)}.` : '', noteDay)}
    {createPortal(<SgTable state={state} bridge={bridge} controller={controller} edit={edit} table={table}/>, table)}
    {createPortal(<YarnBar controller={controller}/>, yarnBar)}
    {createPortal(<YarnRows state={state} bridge={bridge} controller={controller} edit={edit}/>, yarnTableBody)}
  </>;
}

function TopBar({state, controller, edit}: {state: SetupState; controller: SetupController; edit: boolean}) {
  const dirty = rowsDirty(state.cells, state.original, state.cols);
  return <>
    <div className="f"><label htmlFor="sg-day">{tr('Заправка с дня')}</label>
      <input id="sg-day" type="date" value={state.day} onChange={e => controller.setDay(e.target.value)}/></div>
    <div className="f"><label htmlFor="sg-time">{tr('Время начала заправки')}</label>
      <input id="sg-time" type="time" value={state.time} required onChange={e => controller.setTime(e.target.value)}/></div>
    <div className="f"><label htmlFor="sg-filter">{tr('Станки')}</label>
      <input id="sg-filter" size={10} placeholder="D, J1-J14" autoComplete="off"
        value={state.filter} onChange={e => controller.setFilter(e.target.value)}/></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="sg-save" disabled={!edit || state.saving} onClick={() => {void controller.save();}}>{tr('Проверить и провести…')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="sg-undo" disabled={!edit} onClick={() => {void controller.load(true);}}>{tr('Отменить правки')}</button></div>
    <div className="f"><label>{' '}</label>
      <span className="note" id="sg-state" style={{padding: '7px 0'}}>
        {dirty.length ? `${tr('Изменено станков')}: ${dirty.length}` : tr('Изменений нет')}</span></div>
  </>;
}

function SgTable({state, bridge, controller, edit, table}: {state: SetupState; bridge: SetupBridge; controller: SetupController; edit: boolean; table: HTMLTableElement}) {
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});
  const yarns = bridge.yarns();
  const visible = new Set(controller.visibleRows());

  useEffect(() => {
    const grp = table.querySelector('tr.grp') as HTMLElement | null;
    const gh = grp?.offsetHeight;
    if (gh) table.style.setProperty('--sg-h1', gh + 'px');
  });

  if (!state.rows.length) {
    return <><thead/><tbody><tr><td colSpan={state.cols.length + 3 || 1} className="note">
      {tr(state.loaded ? 'Нет отчёта ни за один день — станков не из чего взять.' : 'Загрузка…')}</td></tr></tbody></>;
  }

  const yarnCols = state.cols.filter(c => c.yarn);

  const go = (r: number, c: number, dr: number) => {
    let k = r + dr;
    while (k >= 0 && k < state.rows.length && !visible.has(k)) k += dr;
    const el = inputs.current[`${k}-${c}`];
    if (el) { el.focus(); el.select(); }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>, r: number, c: number) => {
    const col = state.cols[c];
    if (e.key === 'Enter') {
      e.preventDefault();
      if (col.yarn) controller.commitCell(r, c);
      go(r, c, e.shiftKey ? -1 : 1);
    } else if (!col.yarn && e.key === 'ArrowDown') { e.preventDefault(); go(r, c, 1); }
    else if (!col.yarn && e.key === 'ArrowUp') { e.preventDefault(); go(r, c, -1); }
    else if ((e.ctrlKey || e.metaKey) && e.code === 'KeyD' && edit) {
      e.preventDefault();
      let k = r - 1;
      while (k >= 0 && !visible.has(k)) k--;
      if (k >= 0) controller.setCellCanon(r, c, state.cells[k][col.k]);
    }
  };

  const onPaste = (e: ClipboardEvent<HTMLInputElement>, r: number, c: number) => {
    if (!edit) return;
    const text = e.clipboardData.getData('text');
    if (!/[\t\n]/.test(text)) return;
    e.preventDefault();
    controller.paste(r, c, text);
  };

  const cell = (r: number, c: number) => {
    const col = state.cols[c];
    const value = state.cells[r][col.k];
    const row = state.rows[r];
    const isRef = !row.manual[col.k];
    const dirty = value !== state.original[r][col.k];
    const bad = !!col.yarn && yarnBad(value, yarns);
    const cls = ['sg', isRef && 'ref', col.num && 'num', col.yarn && 'yw', dirty && 'chg', bad && 'bad'].filter(Boolean).join(' ');
    return <input key={col.k} className={cls} value={value}
      data-pick={col.yarn ? `yarn:${col.slot}` : col.lot ? `lot:${col.slot}` : undefined}
      readOnly={!edit} autoComplete="off" aria-label={`${row.loom}: ${col.t}`}
      title={bad ? 'Такой пряжи нет в справочнике — выберите из списка или добавьте её' : undefined}
      ref={el => {inputs.current[`${r}-${c}`] = el;}}
      onFocus={() => controller.setFocus(r, c)}
      onChange={e => controller.typeCell(r, c, e.target.value)}
      onBlur={() => controller.commitCell(r, c)}
      onKeyDown={e => onKeyDown(e, r, c)}
      onPaste={e => onPaste(e, r, c)}/>;
  };

  return <>
    <thead>
      <tr className="grp">
        <th colSpan={4}/>
        <th colSpan={SG_NUMS.length} className="sep">{tr('Параметры')}</th>
        {yarnCols.map(c => <th key={c.k} colSpan={2} className="sep">{c.t}</th>)}
      </tr>
      <tr className="cols">
        <th className="stk s0"><input type="checkbox" aria-label={tr('Отметить все станки')}
          onChange={e => controller.toggleAllVisible(e.target.checked)}/></th>
        <th className="stk s1">{tr('Станок')}</th><th className="stk s2">{tr('Дизайн')}</th><th>{tr('Код ткани')}</th>
        {state.cols.filter(c => !c.design).map(c => <th key={c.k} className={(c.num ? 'n' : '') + (c.sep ? ' sep' : '')}>
          {c.yarn ? tr('пряжа') : c.lot ? tr('лот') : c.t}</th>)}
      </tr>
    </thead>
    <tbody>
      {state.rows.map((row, r) => <tr key={row.loom} className={visible.has(r) ? '' : 'hidden'}>
        <td className="stk s0"><input type="checkbox" className="sg-pick" checked={state.picked.has(r)}
          onChange={() => controller.togglePick(r)} aria-label={`${tr('Отметить')} ${row.loom}`}/></td>
        <td className="stk s1"><strong>{row.loom}</strong></td>
        <td className="stk s2">{cell(r, 0)}</td>
        <td className="note">{row.cloth || ''}</td>
        {state.cols.map((c, ci) => ci === 0 ? null : <td key={c.k} className={c.sep ? 'sep' : ''}>{cell(r, ci)}</td>)}
      </tr>)}
    </tbody>
  </>;
}

function YarnBar({controller}: {controller: SetupController}) {
  const nameRef = useRef<HTMLInputElement>(null), kindRef = useRef<HTMLSelectElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const onAdd = () => {
    const name = nameRef.current?.value.trim() || '';
    void controller.addYarn(name, kindRef.current?.value || '');
    if (nameRef.current) nameRef.current.value = '';
  };
  const onFile = () => {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    void controller.importYarns(f);
    if (fileRef.current) fileRef.current.value = '';
  };
  return <>
    <div className="f"><label htmlFor="yarn-new">{tr('Пряжа')}</label>
      <input id="yarn-new" size={16} placeholder="16/1 SPUN" autoComplete="off" ref={nameRef}/></div>
    <div className="f"><label htmlFor="yarn-kind">{tr('Вид')}</label>
      <select id="yarn-kind" ref={kindRef}>
        {Object.entries(YARN_KINDS).map(([k, v]) => <option key={k} value={k}>{tr(v)}</option>)}
      </select></div>
    <div className="f"><label>{' '}</label><button className="act primary" id="yarn-add" onClick={onAdd}>{tr('Добавить')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="yarn-imp" onClick={() => fileRef.current?.click()}>{tr('Загрузить из 1С (.mxl)')}</button>
      <input type="file" id="yarn-file" accept=".mxl" className="hidden" ref={fileRef} onChange={onFile}/></div>
  </>;
}

function YarnRows({state, bridge, controller, edit}: {state: SetupState; bridge: SetupBridge; controller: SetupController; edit: boolean}) {
  const nameRefs = useRef<Record<number, HTMLInputElement | null>>({});
  const yarns = bridge.yarns();
  if (!yarns.length) return <tr><td colSpan={4} className="note">{tr('Справочник пуст — добавьте пряжу.')}</td></tr>;
  const uses: Record<string, number> = {};
  state.rows.forEach(r => state.cols.filter(c => c.yarn).forEach(c => {
    const v = r.values[c.k];
    if (v) uses[yarnKey(v)] = (uses[yarnKey(v)] || 0) + 1;
  }));
  return <>{yarns.map(y => <tr key={y.id} className={y.active ? '' : 'note'}>
    <td>{edit
      ? <input defaultValue={y.name} size={18} autoComplete="off" aria-label={tr('Название пряжи')}
        ref={el => {nameRefs.current[y.id] = el;}}
        onBlur={() => { const v = nameRefs.current[y.id]?.value.trim() || ''; if (v && yarnCanon(v) !== y.name) void controller.renameYarn(y.id, v); }}/>
      : y.name}</td>
    <td>{edit
      ? <select aria-label={tr('Вид пряжи')} defaultValue={y.kind} onChange={e => controller.setYarnKind(y.id, e.target.value)}>
        {Object.entries(YARN_KINDS).map(([k, v]) => <option key={k} value={k}>{tr(v)}</option>)}
      </select>
      : tr(YARN_KINDS[y.kind] || '')}</td>
    <td className="n">{uses[y.key] || ''}</td>
    <td>{edit
      ? <button className="act" onClick={() => controller.toggleYarnActive(y.id, y.name, y.active)}>{tr(y.active ? 'Скрыть' : 'Вернуть')}</button>
      : (y.active ? '' : tr('скрыта'))}</td>
  </tr>)}</>;
}
