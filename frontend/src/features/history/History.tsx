import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { HistoryBridge } from './bridge';
import {
  MH_CAUSES, MH_SEGS, SIGNAL_LABELS, buildGridHtml, chartPolylines, chartRange, chartValues, flattenSignalValues,
  loomGroups, mhDuration, mhTime, pageEvents, pageRangeText, signalKeys, statusText,
} from './model';
import type { FlatSample, HistoryEvent, HistoryRow, HistoryTicket, MachineHistory, Period } from './model';
import type { HistoryController, HistoryState } from './controller';

type Props = {
  topBar: HTMLElement; legend: HTMLElement; status: HTMLElement; gridWrap: HTMLElement; detail: HTMLElement;
  state: HistoryState; bridge: HistoryBridge; controller: HistoryController;
};

export function History({topBar, legend, status, gridWrap, detail, state, controller}: Props) {
  return <>
    {createPortal(<TopBar state={state} controller={controller}/>, topBar)}
    {createPortal(<Legend/>, legend)}
    {createPortal(<StatusLine state={state}/>, status)}
    {createPortal(<Grid state={state} controller={controller} detailEl={detail}/>, gridWrap)}
    {createPortal(<Detail state={state} controller={controller} detailEl={detail}/>, detail)}
  </>;
}

function TopBar({state, controller}: {state: HistoryState; controller: HistoryController}) {
  const groups = loomGroups(state.catalog);
  return <>
    <div className="f"><label htmlFor="mh-day">{tr('Дата в цехе')}</label>
      <input type="date" id="mh-day" value={state.day} onChange={e => controller.setDay(e.target.value)}/></div>
    <div className="f"><label htmlFor="mh-period">{tr('Период')}</label>
      <select id="mh-period" value={state.period} onChange={e => controller.setPeriod(e.target.value as Period)}>
        <option value="day">{tr('Сутки · 00–24')}</option><option value="A">{tr('Смена A · 07–15')}</option>
        <option value="B">{tr('Смена B · 15–23')}</option><option value="C">{tr('Смена C · 23–07 (+1 день)')}</option>
      </select></div>
    <div className="f"><label htmlFor="mh-loom">{tr('Станки')}</label>
      <select id="mh-loom" value={state.loomSelect} onChange={e => controller.setLoomSelect(e.target.value)}>
        <option value="">{tr('Все станки')}</option>
        {groups.map(g => <option key={g} value={`row:${g}`}>{tr('Ряд')} {g}</option>)}
        {state.catalog.map(l => <option key={l} value={l}>{l}</option>)}
      </select></div>
    <div className="f"><label htmlFor="mh-zoom">{tr('Масштаб')}</label>
      <select id="mh-zoom" value={state.zoom} onChange={e => controller.setZoom(+e.target.value as 1 | 2 | 4)}>
        <option value="1">{tr('Обзор')}</option><option value="2">×2</option><option value="4">×4</option>
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="mh-go" disabled={state.loading} onClick={() => {void controller.load();}}>{tr('Показать')}</button></div>
  </>;
}

function Legend() {
  return <>
    {MH_CAUSES.map(([, c, t]) => <span key={t}><i className="mh-key" style={{background: c}}/>{tr(t)}</span>)}
    {(['estimated_run', 'observed_run', 'observed_stop'] as const).map(k =>
      <span key={k}><i className="mh-key" style={{background: MH_SEGS[k][0]}}/>{tr(MH_SEGS[k][1])}</span>)}
    <span><i className="mh-key" style={{background: 'repeating-linear-gradient(135deg,#77839155 0 2px,transparent 2px 6px)'}}/>{tr('Нет подтверждённого состояния')}</span>
    <span><i className="mh-key" style={{background: '#348ec1', height: 5}}/>{tr('Тикет · нижняя дорожка')}</span>
    <span><i className="mh-key" style={{border: '1px solid var(--rule)'}}/>{tr('Время ещё не наступило')}</span>
  </>;
}

function StatusLine({state}: {state: HistoryState}) {
  if (state.error) return <>{state.error}</>;
  if (state.loading) return <>{tr('Загружаю журнал Toyota…')}</>;
  if (state.data) return <>{statusText(state.data)}</>;
  return null;
}

function Grid({state, controller, detailEl}: {state: HistoryState; controller: HistoryController; detailEl: HTMLElement}) {
  const {data} = state;
  const onClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!data) return;
    const target = e.target as HTMLElement;
    const rowEl = target.closest('[data-row]') as HTMLElement | null;
    if (!rowEl) return;
    controller.selectRow(+rowEl.dataset.row!);
    const eventEl = target.closest('[data-event]') as HTMLElement | null;
    const ticketEl = target.closest('[data-ticket]') as HTMLElement | null;
    if (eventEl) controller.showEventDetail(+eventEl.dataset.event!);
    if (ticketEl) controller.showTicketDetail(+ticketEl.dataset.ticket!);
    detailEl.scrollIntoView({block: 'nearest'});
  };
  if (data && !data.rows.length) {
    return <div className="mh-grid" id="mh-grid">{tr('В локальной базе пока нет истории станков.')}</div>;
  }
  return <div className="mh-grid" id="mh-grid" style={{width: state.zoom * 100 + '%'}} onClick={onClick}
    dangerouslySetInnerHTML={{__html: data ? buildGridHtml(data) : ''}}/>;
}

function Detail({state, controller, detailEl}: {state: HistoryState; controller: HistoryController; detailEl: HTMLElement}) {
  const row = controller.currentRow();
  const mh = state.data;
  const visible = !!(row && mh);
  useEffect(() => { detailEl.classList.toggle('hidden', !visible); }, [detailEl, visible]);
  if (!row || !mh) return null;
  const t = row.totals;
  return <>
    <h3>{row.loom} · {mh.day}</h3>
    <div>{tr('Остановы по журналу')}: <b>{mhDuration(t.stop)}</b> · {tr('Работа (расчёт)')}: {mhDuration(t.estimated_run)} · {tr('Неизвестно')}: {mhDuration(t.unknown)}</div>
    <p className="note">{tr('По соседним снимкам FACT: работа')} {mhDuration(t.observed_run || 0)}, {tr('останов')} {mhDuration(t.observed_stop || 0)}. {tr('Пробелы в данных не означают простой.')}</p>
    <h4>{tr('Сигналы станка')}</h4>
    <Signals state={state.signals} controller={controller}/>
    {row.overlap_sec > 0 ? <p className="note">{tr('В журнале есть пересечения. В сумме простой учитывается один раз; исходные события сохранены.')}</p> : null}
    {row.invalid_records ? <p className="note">{tr('Есть некорректные строки журнала')}: {row.invalid_records}. {tr('Они исключены из расчёта.')}</p> : null}
    <EventTicketDetail row={row} detail={state.detail}/>
    <h4>{tr('Остановки Toyota')} · {row.events.length}</h4>
    <EventsTable row={row} mh={mh} page={state.page} controller={controller}/>
    <div className="bar" style={{marginTop: 8}}>
      <button className="act" disabled={state.page === 0} onClick={() => controller.setPage(state.page - 1)}>← {tr('Предыдущие')}</button>
      <span>{pageRangeText(row.events.length, state.page)}</span>
      <button className="act" disabled={(state.page + 1) * 50 >= row.events.length} onClick={() => controller.setPage(state.page + 1)}>{tr('Следующие')} →</button>
    </div>
    <details><summary>{tr('Сверка со сменными итогами Toyota')}</summary>
      <div className="tbl-wrap"><table><thead><tr><th>{tr('Смена')}</th><th>{tr('Работа по итогу, мин')}</th>
        <th>{tr('Простой по итогу, мин')}</th><th>{tr('По журналу, мин')}</th><th>{tr('Расчёт работы')}</th></tr></thead>
        <tbody>{row.shift_checks.map((s, i) => <tr key={i}><td>{s.shift}</td><td>{s.run_min ?? '—'}</td><td>{s.stop_min ?? '—'}</td>
          <td>{(s.logged_stop_sec / 60).toFixed(1)}</td><td>{s.can_estimate ? tr('Согласуется') : tr('Недостаточно подтверждений')}</td></tr>)}</tbody>
      </table></div></details>
    <h4>{tr('Тикеты за период')} · {row.tickets.length}</h4>
    <p className="note">{tr('Время регистрации в MES. Причина относится к тикету; связь с конкретным событием Toyota не установлена.')}</p>
    <TicketsTable row={row} controller={controller}/>
  </>;
}

function EventTicketDetail({row, detail}: {row: HistoryRow; detail: HistoryState['detail']}) {
  if (!detail) return <div id="mh-event-detail" role="status">{tr('Выберите остановку в списке или на шкале.')}</div>;
  if (detail.kind === 'event') {
    const e = row.events[detail.index];
    if (!e) return <div id="mh-event-detail" role="status"/>;
    return <div id="mh-event-detail" role="status">
      <b>{e.reason}</b> · {mhTime(e.start, true)} — {mhTime(e.end, true)}<br/>
      {tr('Полная длительность')}: {mhDuration(e.duration_sec)} · {tr('Реакция')}: {e.response_sec == null ? tr('нет данных') : mhDuration(e.response_sec)}<br/>
      {tr('Код Toyota')}: {e.code ?? '—'} · {tr('Смена')}: {e.shift ?? '—'} · {tr('Стиль')}: <span data-i18n-skip>{e.style ?? '—'}</span><br/>
      <span className="note">{tr('Источник: журнал остановов Toyota.')}</span>
    </div>;
  }
  const t = row.tickets[detail.index];
  if (!t) return <div id="mh-event-detail" role="status"/>;
  return <div id="mh-event-detail" role="status">
    <b>{tr('Тикет')} № {t.id} · {t.reason}</b><br/>
    {mhTime(t.start, true)} — {t.open ? tr('не закрыт') : mhTime(t.end, true)}<br/>
    <span data-i18n-skip>{t.comment}</span><br/>
    <span className="note">{tr('Источник: журнал тикетов MES.')}</span>
  </div>;
}

function EventsTable({row, mh, page, controller}: {row: HistoryRow; mh: MachineHistory; page: number; controller: HistoryController}) {
  const shown = pageEvents(row.events, page);
  return <div className="tbl-wrap"><table><thead><tr><th>{tr('Начало')}</th><th>{tr('Окончание')}</th>
    <th>{tr('Причина')}</th><th>{tr('В выбранном периоде')}</th></tr></thead>
    <tbody>{shown.length ? shown.map((e, j) => <EventRow key={page * 50 + j} e={e} index={page * 50 + j} mh={mh} controller={controller}/>)
      : <tr><td colSpan={4}>{tr('Остановок за этот период в журнале нет.')}</td></tr>}</tbody>
  </table></div>;
}

function EventRow({e, index, mh, controller}: {e: HistoryEvent; index: number; mh: MachineHistory; controller: HistoryController}) {
  const inPeriod = Math.max(0, Math.min(e.end, mh.end, mh.generated_at) - Math.max(e.start, mh.start));
  return <tr>
    <td><button className="mh-event" onClick={() => controller.showEventDetail(index)}>{mhTime(e.start, true)}</button></td>
    <td>{mhTime(e.end, true)}</td><td>{e.reason}</td><td>{mhDuration(inPeriod)}</td>
  </tr>;
}

function TicketsTable({row, controller}: {row: HistoryRow; controller: HistoryController}) {
  return <div className="tbl-wrap"><table><thead><tr><th>{tr('Тикет')}</th><th>{tr('Начало')}</th>
    <th>{tr('Причина')}</th><th>{tr('Статус')}</th></tr></thead>
    <tbody>{row.tickets.length ? row.tickets.map((t, i) => <TicketRow key={i} t={t} index={i} controller={controller}/>)
      : <tr><td colSpan={4}>{tr('Тикетов за этот период нет.')}</td></tr>}</tbody>
  </table></div>;
}

function TicketRow({t, index, controller}: {t: HistoryTicket; index: number; controller: HistoryController}) {
  return <tr>
    <td><button className="mh-event" onClick={() => controller.showTicketDetail(index)}>№ {t.id}</button></td>
    <td>{mhTime(t.start, true)}</td><td>{t.reason}</td><td>{t.open ? tr('Не закрыт') : tr('Закрыт')}</td>
  </tr>;
}

function Signals({state, controller}: {state: HistoryState['signals']; controller: HistoryController}) {
  if (state.loading) return <div id="mh-signals">{tr('Загружаю сохранённые сигналы…')}</div>;
  if (state.error) return <div id="mh-signals">{state.error}</div>;
  if (!state.data) return <div id="mh-signals"/>;
  if (!state.data.samples.length) {
    return <div id="mh-signals">{tr('Архив за этот период пуст. Сигналы сохраняются после установки обновления; прошлые значения не выдумываются.')}</div>;
  }
  const samples: FlatSample[] = state.data.samples.map(s => ({at: s.at, flat: flattenSignalValues(s.values)}));
  const keys = signalKeys(samples);
  const key = state.selectedKey || keys[0] || '';
  const values = key ? chartValues(samples, key) : [];
  const range = chartRange(values);
  const lines = chartPolylines(values, state.data.start, state.data.end);
  return <div id="mh-signals">
    <p className="note">{state.data.note} {tr('Основное состояние — каждый снимок; подробные сигналы работающего станка могут обновляться раз в 5 минут. RPM из FACT — исходное значение, оно может оставаться ненулевым при останове.')}</p>
    <label>{tr('Сигнал')} <select id="mh-signal" value={key} onChange={e => controller.setSignalKey(e.target.value)}>
      {keys.map(k => <option key={k} value={k}>{SIGNAL_LABEL(k)}</option>)}
    </select></label>
    <div id="mh-signal-chart">
      {range ? <>
        <p>Min: {range.lo} · Max: {range.hi}</p>
        <svg viewBox="0 0 1000 170" role="img" aria-label={tr('История выбранного сигнала')} style={{width: '100%', height: 170, background: 'var(--surface-2)'}}>
          {lines.map((points, i) => <polyline key={i} points={points} fill="none" stroke="#147eaf" strokeWidth={2}/>)}
        </svg></> : null}
    </div>
    <div id="mh-signal-values">
      <p className="note">{tr('Последние 200 значений; время источника сигнала (UTC+5).')}</p>
      <div className="tbl-wrap"><table><thead><tr><th>{tr('Время')}</th><th>{tr('Значение')}</th></tr></thead>
        <tbody>{values.slice(-200).reverse().map((s, i) => <tr key={i}><td>{mhTime(s.at, true)}</td><td>{String(s.v ?? tr('Нет данных'))}</td></tr>)}</tbody>
      </table></div>
    </div>
  </div>;
}

function SIGNAL_LABEL(k: string): string { return tr(SIGNAL_LABELS[k] || k); }
