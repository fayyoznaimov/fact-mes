import { Fragment, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { DashBridge } from './bridge';
import type { DashRow, DashTotals } from './model';
import { articleOptions, dur, filterRows, inText, noteText, splitForecast, warnSummary, yarnEntries } from './model';
import type { DashController, DashState } from './controller';

type Props = {
  topBar: HTMLElement; tiles: HTMLElement; note: HTMLElement; warnEl: HTMLDetailsElement;
  soon: HTMLElement; tbody: HTMLElement;
  state: DashState; bridge: DashBridge; controller: DashController;
};

export function Dash({topBar, tiles, note, warnEl, soon, tbody, state, bridge, controller}: Props) {
  const data = state.data;
  const warnCount = data?.mismatches.length || 0;
  useEffect(() => { warnEl.classList.toggle('hidden', !warnCount); }, [warnEl, warnCount]);

  return <>
    {createPortal(<TopBar state={state} controller={controller} bridge={bridge}/>, topBar)}
    {data && createPortal(<Tiles totals={data.totals}/>, tiles)}
    {data && createPortal(noteText(data.totals), note)}
    {data && createPortal(<>
      <summary>{warnSummary(data.mismatches)}</summary>
      <ul style={{margin: '6px 0 0', paddingLeft: 18}}>
        {data.mismatches.map((w, i) => <li key={i}><b>{w.loom}</b> — {w.text}</li>)}
      </ul>
    </>, warnEl)}
    {createPortal(<Soon forecast={state.forecast}/>, soon)}
    {data && createPortal(<Rows data={data} state={state} bridge={bridge} controller={controller}/>, tbody)}
  </>;
}

function TopBar({state, controller, bridge}: {state: DashState; controller: DashController; bridge: DashBridge}) {
  return <>
    <div className="f"><label htmlFor="dash-day">День</label>
      <select id="dash-day" value={state.day} onChange={e => controller.setDay(e.target.value)}>
        {state.days.map(d => <option key={d} value={d}>{bridge.fday(d)}</option>)}
      </select></div>
    <div className="f"><label htmlFor="dash-shift">Смена</label>
      <select id="dash-shift" value={state.shift} onChange={e => controller.setShift(e.target.value)}>
        <option value="">весь день</option><option value="A">A</option><option value="B">B</option><option value="C">C</option>
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="dash-go" onClick={() => {void controller.load();}}>Показать</button></div>
    <div className="f"><label>Для монитора</label>
      <a className="act" id="dash-cards" href={controller.cardsHref()} target="_blank" rel="noreferrer" style={{textDecoration: 'none'}}>Карточки станков</a></div>
    <div className="f"><label htmlFor="dash-only">Показывать</label>
      <select id="dash-only" value={state.only} onChange={e => controller.setOnly(e.target.value as DashState['only'])}>
        <option value="all">все станки</option><option value="stop">только стоящие</option><option value="ticket">только с тикетом</option>
      </select></div>
  </>;
}

function Tiles({totals: t}: {totals: DashTotals}) {
  const nf = (x: number, d = 0) => x.toLocaleString('ru-RU', {minimumFractionDigits: d, maximumFractionDigits: d});
  const items: {label: string; value: React.ReactNode}[] = [
    {label: 'Работает', value: <><span className="dot run"/>{t.running}</>},
    {label: 'Стоит', value: <><span className="dot stop"/>{t.stopped}</>},
    {label: 'С тикетом', value: t.with_ticket},
    {label: 'Тыс. пиков', value: nf(t.kpicks)},
    {label: 'Обрывы утка', value: nf(t.weft_ct)},
    {label: 'Обрывы основы', value: nf(t.warp_ct)},
    {label: 'Обрывы ворса', value: nf(t.top_ct)},
  ];
  return <>{items.map(it => <div className="tile" key={it.label}><div className="l">{it.label}</div><div className="v">{it.value}</div></div>)}</>;
}

function Soon({forecast}: {forecast: DashState['forecast']}) {
  if (!forecast) return null;
  const events = forecast.events || [];
  const stale = forecast.stale ? <p className="bad">Данные FACT от {forecast.snapshot_at} — связи нет, сроки могут сдвинуться.</p> : null;
  if (!events.length) return stale;
  const {soon, later} = splitForecast(events);
  const table = (list: typeof events) => <table className="soon-t"><tbody>{list.map((e, i) => (
    <tr key={i} className={e.in_min <= 30 ? 'near' : ''}>
      <td className="n">{e.at}{e.when ? <small className="note"> {e.when}</small> : null}</td>
      <td className="n">через {inText(e.in_min)}</td>
      <td><b>{e.loom}</b></td><td>{e.what}</td>
    </tr>
  ))}</tbody></table>;
  return <>
    <h3 className="sect">Ближайшие 12 часов: съём ткани и сход навоя</h3>
    {stale}
    {soon.length ? table(soon) : <p className="note">В ближайшие два часа — ничего.</p>}
    {later.length ? <details><summary>Позже — ещё {later.length}</summary>{table(later)}</details> : null}
  </>;
}

function Rows({data, state, bridge, controller}: {data: NonNullable<DashState['data']>; state: DashState; bridge: DashBridge; controller: DashController}) {
  const rows = filterRows(data.rows, state.only);
  const nf = bridge.nf;
  const brk = (ct: number, fix?: number) => <>{nf(ct)}{fix ? <small className="note"> ({fix} мин)</small> : null}</>;
  return <>{rows.map(r => {
    const open = state.open.has(r.loom);
    const product = r.article_from === 'план'
      ? <><b>{r.order_no}</b> {r.design || ''}{r.client ? <small className="note"> · {r.client}</small> : null}</>
      : r.design ? r.design : <span className="note">не задано</span>;
    return <Fragment key={r.loom}>
      <tr className={r.state === 'stop' ? 'is-stop' : ''}>
        <td><button type="button" className="more" aria-expanded={open} aria-label={`Заправка станка ${r.loom}`}
          onClick={() => controller.toggleOpen(r.loom)}>{open ? '▾' : '▸'}</button></td>
        <td><b>{r.loom}</b>{(r.mismatch || []).length
          ? <span className="bad" title={(r.mismatch || []).join('\n')} aria-label="расхождение с планом"> ⚠</span>
          : (r.notes || []).length ? <span className="note" title={(r.notes || []).join('\n')} aria-label="примечание к заправке"> ⓘ</span> : null}</td>
        <td className="st">{r.state === 'run' ? 'работает' : r.state === 'stop'
          ? <><span className="dot stop"/>стоит {dur((r.state_min || 0) * 60)}<br/><small>{r.reason || r.cause_ru || ''}</small></> : '—'}
          {r.ticket ? <> <span className="badge">тикет: {r.ticket.reason}</span></> : null}</td>
        <td className="n">{r.rpm_now ? nf(r.rpm_now) : ''}</td>
        <td className="sep">{product}</td>
        <td className="n sep">{nf(r.kpicks, 1)}</td>
        <td className="n">{nf(r.towels)}</td>
        <td className="n">{r.effic != null ? nf(r.effic, 1) : ''}</td>
        <td className="sep">{r.operator ? <>{r.operator.name} <small className="note">{r.operator.code}</small></> : '—'}</td>
        <td className="n sep">{nf(r.weft_ct)} · {nf(r.warp_ct)} · {nf(r.top_ct)}
          {r.manual_ct ? <><br/><small className="note">ручн. {nf(r.manual_ct)}</small></> : null}</td>
      </tr>
      <tr className={'detail' + (open ? '' : ' hidden')}><td/><td colSpan={9}>
        <dl className="dash-setup">
          <div><dt>Изделие</dt><dd><ArticleCell row={r} articles={data.articles} controller={controller}/></dd></div>
          <div><dt>Размер</dt><dd>{r.size || '—'}</dd></div>
          <div><dt>Плотность</dt><dd>{r.gsm ? `${r.gsm} г/м²` : '—'}</dd></div>
          <div><dt>Код ткани на станке</dt><dd>{r.cloth || '—'}</dd></div>
          <div><dt>Метры</dt><dd>{nf(r.meters || 0, 1)}</dd></div>
          <div><dt>Ряды × панели</dt><dd>{(r.panels || 0) > 1 ? `${nf(r.pieces || 0)} × ${r.panels}` : nf(r.pieces || 0)}</dd></div>
          <div><dt>Об/мин за смену</dt><dd>{r.rpm_shift ? nf(r.rpm_shift) : '—'}</dd></div>
          <div><dt>Устранение, мин</dt><dd>уток {brk(r.weft_fix_min || 0)} · основа {brk(r.warp_fix_min || 0)} · ворс {brk(r.top_fix_min || 0)}</dd></div>
          <div className="wide"><dt>Пряжа</dt><dd>{(() => {
            const entries = yarnEntries(r, data.yarn_titles);
            return entries.length ? entries.map((y, i) => <span key={i}>{i > 0 ? ' · ' : ''}{y.label}: {y.text}</span>) : '—';
          })()}</dd></div>
          {[...(r.mismatch || []), ...(r.notes || [])].length ? <div className="wide"><dt>Сверка с планом</dt>
            <dd>{[...(r.mismatch || []), ...(r.notes || [])].map((t, i) => <Fragment key={i}>{i > 0 ? <br/> : null}{t}</Fragment>)}</dd></div> : null}
        </dl>
      </td></tr>
    </Fragment>;
  })}</>;
}

function ArticleCell({row: r, articles, controller}: {row: DashRow; articles: string[]; controller: DashController}) {
  if (r.article_from === 'план') {
    return <><div><b>{r.order_no}</b> {r.design || ''}{r.client ? <> · клиент {r.client}</> : null} <small>(план)</small></div>
      <div className="note" style={{margin: '2px 0 0'}}>{r.article}</div></>;
  }
  const opts = articleOptions(r, articles);
  return <>
    {r.order_no ? <div className="note" style={{margin: '0 0 2px'}}>по плану: <b>{r.order_no}</b> {r.plan_product || ''}</div> : null}
    <select className="art" value={r.article || ''} onChange={e => {void controller.setArticle(r.loom, e.target.value);}}>
      {opts.map(o => <option key={o.value} value={o.value}>{o.starred ? '★ ' : ''}{o.label}</option>)}
    </select>
    {r.design ? <div className="note" style={{margin: '2px 0 0'}}>{r.design}{r.article_from ? <small> ({r.article_from})</small> : null}</div> : null}
  </>;
}
