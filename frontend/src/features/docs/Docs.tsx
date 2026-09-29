import { Fragment, useState } from 'react';
import { createPortal } from 'react-dom';
import { nf } from '../report/model';
import { PeriodTable, type PeriodRow, type PeriodTotals } from '../report/period';
import type { DocsBridge } from './bridge';
import { tr } from './bridge';
import type { ChipKind, DiffField, DocFull, DocTab, LogOperation, PayrollResult } from './model';
import {
  docStatusText, docTiles, dxChanges, dxCtx, dxDay, dxGroup, dxObjects, dxSummary, dxTime,
  moneyDiffFields, payrollLines, payrollUnassigned, titledDiffFields,
} from './model';
import type { DocsController, DocsState } from './controller';
import { DiffTable } from './DiffTable';

type Props = {
  kindsBar: HTMLElement; filterBar: HTMLElement; newBar: HTMLElement;
  items: HTMLElement; form: HTMLElement;
  state: DocsState; bridge: DocsBridge; controller: DocsController;
};

export function Docs({kindsBar, filterBar, newBar, items, form, state, bridge, controller}: Props) {
  return <>
    {createPortal(<ChipsBar state={state} controller={controller}/>, kindsBar)}
    {createPortal(<FilterBar state={state} controller={controller}/>, filterBar)}
    {createPortal(<NewBar controller={controller} bridge={bridge}/>, newBar)}
    {createPortal(<ItemsList state={state} controller={controller}/>, items)}
    {createPortal(<DetailArticle state={state} bridge={bridge} controller={controller}/>, form)}
  </>;
}

const CHIPS: [ChipKind, string][] = [['', 'Все документы'], ['setup', 'Заправка'], ['payroll', 'Ведомости'],
  ['report', 'Отчёты'], ['rate', 'Ставка'], ['log', 'Журнал изменений']];

function ChipsBar({state, controller}: {state: DocsState; controller: DocsController}) {
  return <>{CHIPS.map(([k, label]) => <button key={k || 'all'} className="chip" aria-pressed={state.kind === k}
    onClick={() => controller.setKind(k)}>{tr(label)}</button>)}</>;
}

function FilterBar({state, controller}: {state: DocsState; controller: DocsController}) {
  return <>
    <div className="f"><label htmlFor="dx-from">{tr('С')}</label>
      <input id="dx-from" type="date" value={state.from} onChange={e => controller.setFrom(e.target.value)}/></div>
    <div className="f"><label htmlFor="dx-to">{tr('По')}</label>
      <input id="dx-to" type="date" value={state.to} onChange={e => controller.setTo(e.target.value)}/></div>
    <div className={'f wide' + (state.kind === 'log' ? '' : ' hidden')} id="dx-entity-wrap">
      <label htmlFor="dx-entity">{tr('Что менялось')}</label>
      <select id="dx-entity" value={state.entity} onChange={e => controller.setEntity(e.target.value)}>
        <option value="">{tr('всё, что мне доступно')}</option>
        {state.entities.map(e => <option key={e.id} value={e.id}>{e.title}</option>)}
      </select></div>
    <div className="f wide"><label htmlFor="dx-q">{tr('Поиск')}</label>
      <input id="dx-q" type="search" placeholder="номер, станок, сотрудник, автор" autoComplete="off"
        value={state.q} onChange={e => controller.setQ(e.target.value)}/></div>
  </>;
}

function NewBar({controller, bridge}: {controller: DocsController; bridge: DocsBridge}) {
  return <>
    <button className="act" onClick={() => {void controller.newDoc('payroll');}}>{tr('Новая ведомость…')}</button>
    <button className="act" onClick={() => {void controller.newDoc('report');}}>{tr('Утвердить отчёт…')}</button>
    <button className="act" onClick={bridge.goToRateSettings}>{tr('Новая ставка…')}</button>
  </>;
}

function DocStatus({status}: {status: string}) {
  return <span className={'doc-status ' + status}>{tr(docStatusText(status))}</span>;
}

function ItemsList({state, controller}: {state: DocsState; controller: DocsController}) {
  if (!state.loadedList) return <li className="dx-group">{tr('Загрузка…')}</li>;
  if (state.kind === 'log') {
    if (!state.ops.length) return <li className="dx-group">{tr('За этот период изменений нет.')}</li>;
    let day = '';
    return <>{state.ops.map((o, i) => {
      const d = dxDay(o.at), head = d !== day; day = d;
      const kinds = [...new Set(o.items.map(x => x.entity_text))];
      const current = state.sel?.type === 'op' && state.sel.index === i;
      return <Fragment key={i}>
        {head && <li className="dx-group">{d}</li>}
        <li><button className="dx-item" aria-current={current} onClick={() => controller.openOperation(i)}>
          <span className="dx-no">{o.actor}</span><span className="dx-when">{dxTime(o.at).slice(11)}</span>
          <span className="dx-title">{o.items[0].object}{o.items.length > 1 ? ` и ещё ${o.items.length - 1}` : ''}</span>
          <span className="dx-meta"><span>{kinds.join(', ')}</span><span>{dxObjects(o.items.length)}</span></span>
        </button></li>
      </Fragment>;
    })}</>;
  }
  if (!state.items.length) return <li className="dx-group">{tr('Документов нет. Измените период или вид.')}</li>;
  let day = '';
  return <>{state.items.map(d => {
    const dd = dxDay(d.created_at), head = dd !== day; day = dd;
    const current = state.sel?.type === 'doc' && state.sel.id === d.id;
    return <Fragment key={d.id}>
      {head && <li className="dx-group">{dd}</li>}
      <li><button className={'dx-item ' + d.status} aria-current={current} onClick={() => {void controller.openDoc(d.id);}}>
        <span className="dx-no">{d.number}</span><span className="dx-when">{dxTime(d.created_at).slice(11)}</span>
        <span className="dx-title">{d.title}</span>
        <span className="dx-meta"><DocStatus status={d.status}/><span>{d.created_by}</span><span>{dxSummary(d)}</span>
          {d.warnings_count ? <span>{tr('предупреждений')}: {d.warnings_count}</span> : null}</span>
      </button></li>
    </Fragment>;
  })}</>;
}

function DetailArticle({state, bridge, controller}: {state: DocsState; bridge: DocsBridge; controller: DocsController}) {
  if (!state.sel) return <p className="dx-blank">{tr('Выберите документ в журнале слева.')}</p>;
  if (state.sel.type === 'op') {
    const op = state.ops[state.sel.index];
    return op ? <OperationDetail op={op}/> : null;
  }
  if (state.loadingDoc || !state.doc) return <p className="dx-blank">{tr('Открываю документ…')}</p>;
  return <DocDetail state={state} bridge={bridge} controller={controller}/>;
}

function OperationDetail({op}: {op: LogOperation}) {
  return <>
    <div className="dx-head"><div><div className="dx-id"><span className="dx-pill">{dxObjects(op.items.length)}</span></div>
      <h3>{tr('Изменения')} {dxTime(op.at)}</h3></div></div>
    <dl className="dx-req">
      <div><dt>{tr('Кто')}</dt><dd>{op.actor}</dd></div>
      <div><dt>{tr('Когда')}</dt><dd>{dxTime(op.at)}</dd></div>
      <div><dt>{tr('Что менялось')}</dt><dd>{[...new Set(op.items.map(x => x.entity_text))].join(', ')}</dd></div>
    </dl>
    <div>{op.items.map((x, i) => <div className="dx-obj" key={i}>
      <h4>{x.object} <span className={'dx-pill ' + (x.action === 'DELETE' ? 'del' : x.action === 'UPDATE' || x.fields.some(f => f.before != null) ? 'chg' : 'add')}>{x.action_text}</span></h4>
      <DiffTable fields={x.fields}/>
    </div>)}</div>
  </>;
}

function DocTiles({type, summary}: {type: string; summary?: Record<string, unknown>}) {
  const tiles = docTiles(type, summary);
  if (!tiles.length) return null;
  return <div className="tiles" style={{marginTop: 10}}>{tiles.map(t => <div className="tile" key={t.label}>
    <span className="l">{t.label}</span><span className="v">{t.value}{t.unit ? <small> {t.unit}</small> : null}</span>
  </div>)}</div>;
}

function VerifyOut({verify}: {verify: NonNullable<DocsState['verify']>}) {
  if (verify.loading) return <div id="dx-verify-out"><p className="note">{tr('Пересчитываю по текущим данным…')}</p></div>;
  if (verify.same) return <div id="dx-verify-out"><div className="doc-verdict ok">{tr('Совпадает с текущими данными')}</div></div>;
  return <div id="dx-verify-out">
    <div className="doc-verdict warn">{tr('Данные изменились после проведения. Исправляют новым документом взамен этого.')}</div>
    {verify.rows ? <DiffTable fields={moneyDiffFields(verify.rows)} before="Было, сум" after="Стало, сум"/> : null}
    {verify.looms ? verify.looms.map(l => <div className="dx-obj" key={l.loom}><h4>{tr('Станок')} {l.loom}</h4>
      <DiffTable fields={l.rows.map(r => ({label: r.label, before: r.before, after: r.after, changed: true, delta: r.delta}))} before="В документе" after="Сейчас"/>
    </div>) : null}
  </div>;
}

function HistoryTable({rows, replacedBy, onOpen}: {rows: [string, string, string][]; replacedBy: {id: number; number: string}[]; onOpen: (id: number) => void}) {
  return <div className="tbl-wrap"><table><thead><tr><th>{tr('Когда')}</th><th>{tr('Кто')}</th><th>{tr('Что сделано')}</th></tr></thead>
    <tbody>
      {rows.map((r, i) => <tr key={i}><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td></tr>)}
      {replacedBy.length ? <tr><td/><td/><td>{tr('Заменён документом')} {replacedBy.map((x, i) => <span key={x.id}>
        {i > 0 ? ', ' : ''}<button className="dx-link" onClick={() => onOpen(x.id)}>{x.number}</button></span>)}</td></tr> : null}
    </tbody></table></div>;
}

function PayrollTable({result}: {result: PayrollResult}) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const ops = result.operators || [], shifts = result.shifts || [];
  const toggle = (id: number) => setOpen(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const totalKpicks = ops.reduce((a, o) => a + o.kpicks, 0), totalSalary = ops.reduce((a, o) => a + o.salary, 0);
  const unassigned = payrollUnassigned(shifts);
  return <>
    <div className="tbl-wrap"><table>
      <thead><tr><th>{tr('Код')}</th><th>{tr('Сотрудник')}</th><th className="n">{tr('Смен')}</th><th className="n">{tr('Тыс. пиков')}</th><th className="n">{tr('Сумма, сум')}</th></tr></thead>
      <tbody>{ops.length ? ops.map(o => <Fragment key={o.operator_id}>
        <tr><td>{o.code}</td><td><button className="dx-link" aria-expanded={open.has(o.operator_id)} onClick={() => toggle(o.operator_id)}>{o.name}</button></td>
          <td className="n">{o.shifts}</td><td className="n">{nf(o.kpicks, 1)}</td><td className="n"><b>{nf(o.salary)}</b></td></tr>
        <tr className={'dx-sub' + (open.has(o.operator_id) ? '' : ' hidden')}><td/><td colSpan={4}>
          <div className="tbl-wrap"><table><thead><tr><th>{tr('День')}</th><th>{tr('Смена')}</th><th>{tr('Станки')}</th><th>{tr('Тыс. пиков')}</th><th>{tr('Ставка')}</th><th>{tr('Сумма, сум')}</th></tr></thead>
            <tbody>{payrollLines(shifts, o.operator_id).map((l, i) => <tr key={i}><td>{dxDay(l.day)}</td><td>{l.shift}</td><td>{(l.looms || []).join(', ')}</td>
              <td>{nf(l.kpicks, 1)}</td><td>{nf(l.rate, 2)} {l.unit === 'kpick' ? tr('за 1000 пиков') : tr('за пик')}</td><td>{nf(l.salary)}</td></tr>)}</tbody>
          </table></div>
        </td></tr>
      </Fragment>) : <tr><td colSpan={5}>{tr('Нет начислений.')}</td></tr>}</tbody>
      <tfoot><tr><td colSpan={2}>{tr('Итого')}</td><td/><td className="n">{nf(totalKpicks, 1)}</td><td className="n"><b>{nf(totalSalary)}</b></td></tr></tfoot>
    </table></div>
    {unassigned.length ? <>
      <h4>{tr('Не распределено: выработка станков без оператора')}</h4>
      <div className="tbl-wrap"><table><thead><tr><th>{tr('День')}</th><th>{tr('Смена')}</th><th>{tr('Сумма, сум')}</th></tr></thead>
        <tbody>{unassigned.map((s, i) => <tr key={i}><td>{dxDay(s.day)}</td><td>{s.shift}</td><td>{nf(s.unassigned_salary)}</td></tr>)}</tbody>
      </table></div></> : null}
  </>;
}

function DocBody({doc: d, tab, state, controller}: {doc: DocFull; tab: DocTab; state: DocsState; controller: DocsController}) {
  if (tab === 'warnings') {
    return d.warnings.length
      ? <><p className="note">{tr('Эти предупреждения проводивший видел и подтвердил.')}</p>
        <ul className="doc-list warn">{d.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></>
      : <p className="note">{tr('Предупреждений при проведении не было.')}</p>;
  }
  if (tab === 'history') {
    const rows: [string, string, string][] = d.history.map(h => [dxTime(h.at), h.actor, h.text || h.action]);
    return <HistoryTable rows={rows} replacedBy={d.replaced_by} onOpen={id => {void controller.openDoc(id);}}/>;
  }
  if (d.type === 'setup') {
    const only = tab === 'changes' || state.only;
    return <>
      {tab === 'content' && <label className="dx-tools"><input type="checkbox" checked={state.only}
        onChange={e => controller.setOnly(e.target.checked)}/> {tr('Только изменённые реквизиты')}</label>}
      {(d.looms || []).map(l => {
        const ctx = dxCtx(l.context);
        return <div className="dx-obj" key={l.loom}>
          <h4>{tr('Станок')} {l.loom} <small>{tr('версия')} {l.version}{l.previous
            ? `, ${tr('предыдущая')} — ${dxTime(l.previous.created_at)}, ${tr('ввёл')} ${l.previous.author}` : `, ${tr('первая запись по станку')}`}</small></h4>
          {ctx.length ? <p className="dx-ctx">{ctx.map(([k, v]) => <span key={k}>{k} <b>{v}</b></span>)}</p> : null}
          <p className="dx-ctx"><span>{tr('Действует с')} <b>{dxTime(l.valid_from)}</b></span></p>
          <DiffTable fields={l.fields} only={only}/>
          {l.warning ? <p className="note">{l.warning}</p> : null}
        </div>;
      })}
    </>;
  }
  if (d.type === 'payroll') {
    return tab === 'content'
      ? <><p className="note">{tr('Нажмите на сотрудника, чтобы увидеть начисление по сменам.')}</p><PayrollTable result={(d.result || {}) as PayrollResult}/></>
      : (d.changes || []).length
        ? <><p className="note">{tr('Сравнение с заменённой ведомостью')} {d.supersedes ? d.supersedes.number : ''}.</p>
          <DiffTable fields={moneyDiffFields((d.changes || []) as unknown as {title: string; before: number | null; after: number | null}[])} before="Было, сум" after="Стало, сум"/></>
        : <p className="note">{tr('Первая ведомость за этот период: сравнивать не с чем. Изменения после проведения покажет «Сверить с текущими данными».')}</p>;
  }
  if (d.type === 'report') {
    const r = (d.result || {}) as {rows?: PeriodRow[]; totals?: PeriodTotals};
    if (tab === 'content') return r.rows && r.totals ? <PeriodTable data={{rows: r.rows, totals: r.totals}}/> : null;
    if (!(d.changes || []).length) return <p className="note">{tr('Первый утверждённый отчёт за этот период: сравнивать не с чем.')}</p>;
    return <>
      <h4>{tr('Отличия от заменяемого отчёта')}</h4>
      {dxGroup(d.changes as unknown as Record<string, unknown>[], 'loom').map(([loom, rows]) => <div className="dx-obj" key={String(loom)}>
        <h4>{tr('Станок')} {String(loom)}</h4><DiffTable fields={titledDiffFields(rows as DiffField[])}/>
      </div>)}
    </>;
  }
  if (d.type === 'rate') {
    return <DiffTable fields={titledDiffFields(d.changes || [])} before="Действовало" after="Стало действовать"/>;
  }
  return null;
}

function DocDetail({state, bridge, controller}: {state: DocsState; bridge: DocsBridge; controller: DocsController}) {
  const d = state.doc!;
  const k = state.kinds[d.type] || {id: d.type, title: d.type_title, can_post: false};
  const canCancel = d.status === 'posted' && d.type !== 'setup' && k.can_post;
  const canReplace = d.status === 'posted' && ['payroll', 'report'].includes(d.type) && k.can_post;
  const tabs: [DocTab, string, number | null][] = [['content', 'Содержание', null], ['changes', 'Изменения', dxChanges(d)],
    ['warnings', 'Предупреждения', d.warnings.length], ['history', 'История', d.history.length]];
  const tab = tabs.some(t => t[0] === state.tab) ? state.tab : 'content';
  const req: [string, string][] = [
    ['Вид', d.type_title], ['Проведён', `${d.created_by}, ${dxTime(d.created_at)}`],
    ...(d.period_from ? [['Период', d.period_to ? `${dxDay(d.period_from)} – ${dxDay(d.period_to)}` : `с ${dxDay(d.period_from)}`] as [string, string]] : []),
    ...(d.comment ? [['Комментарий', d.comment] as [string, string]] : []),
    ...(d.status === 'cancelled' ? [['Отменён', `${d.cancelled_by}, ${dxTime(d.cancelled_at)}: ${d.cancel_reason}`] as [string, string]] : []),
  ];
  const onCancel = async () => {
    const reason = window.prompt(tr('Причина отмены документа') + ' ' + d.number + ':');
    if (reason == null) return;
    await controller.cancel(reason);
  };
  return <>
    <div className="dx-head">
      <div><div className="dx-id"><span className="dx-no">{d.number}</span><DocStatus status={d.status}/></div><h3>{d.title}</h3></div>
      <div className="dx-actions">
        {['payroll', 'report'].includes(d.type) && <button className="act" onClick={() => {void controller.verify();}}>{tr('Сверить с текущими данными')}</button>}
        {canReplace && <button className="act" onClick={() => {void controller.replace();}}>{tr('Провести взамен…')}</button>}
        {canCancel && <button className="act" onClick={() => {void onCancel();}}>{tr('Отменить…')}</button>}
        <button className="act" onClick={() => window.print()}>{tr('Печать')}</button>
      </div>
    </div>
    <dl className="dx-req">
      {req.map(([t, v]) => <div key={t}><dt>{tr(t)}</dt><dd>{v}</dd></div>)}
      {d.supersedes ? <div><dt>{tr('Заменяет')}</dt><dd><button className="dx-link" onClick={() => {void controller.openDoc(d.supersedes!.id);}}>{d.supersedes.number}</button> {tr('от')} {dxTime(d.supersedes.created_at)}</dd></div> : null}
      {d.replaced_by.length ? <div><dt>{tr('Заменён документом')}</dt><dd>{d.replaced_by.map((x, i) => <span key={x.id}>
        {i > 0 ? ', ' : ''}<button className="dx-link" onClick={() => {void controller.openDoc(x.id);}}>{x.number}</button></span>)}</dd></div> : null}
    </dl>
    <DocTiles type={d.type} summary={d.summary}/>
    {state.verify ? <VerifyOut verify={state.verify}/> : null}
    <div className="dx-tabs" role="tablist">{tabs.map(([id, t, n]) => <button key={id} role="tab" aria-selected={tab === id}
      onClick={() => controller.setTab(id)}>{tr(t)}{n != null ? <span className="count">{n}</span> : null}</button>)}</div>
    <div role="tabpanel"><DocBody doc={d} tab={tab} state={state} controller={controller}/></div>
  </>;
}
