import { Fragment } from 'react';
import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { ManualBridge } from './bridge';
import { GROUP_KEY_NAME, hms, isHotCell, noneColClass, paintEff, rowKeyLabel, unexplainedMinutes } from './model';
import type { Cat, Column, Group, ManualResponse, ManualRow } from './model';
import type { ManualController, ManualState } from './controller';

type Props = {
  topBar: HTMLElement; reasonBtn: HTMLElement; tiles: HTMLElement;
  thead: HTMLElement; tableBody: HTMLElement; tableFoot: HTMLElement;
  state: ManualState; bridge: ManualBridge; controller: ManualController;
};

export function Manual({topBar, reasonBtn, tiles, thead, tableBody, tableFoot, state, bridge, controller}: Props) {
  const data = state.data;
  return <>
    {createPortal(<TopBar state={state} bridge={bridge} controller={controller}/>, topBar)}
    {createPortal(<button className="act primary" id="mn-reason" onClick={bridge.openTickets}>
      {tr('Указать причину ручного простоя / создать тикет')}</button>, reasonBtn)}
    {data && createPortal(<Tiles data={data} bridge={bridge}/>, tiles)}
    {data && createPortal(<Thead data={data}/>, thead)}
    {data && createPortal(<TableRows data={data} bridge={bridge}/>, tableBody)}
    {data && createPortal(<tr><RowCells row={data.totals} columns={data.columns} label={tr('Итого')} nf={bridge.nf}/></tr>, tableFoot)}
  </>;
}

function TopBar({state, bridge, controller}: {state: ManualState; bridge: ManualBridge; controller: ManualController}) {
  return <>
    <div className="f"><label htmlFor="mn-from">{tr('С')}</label>
      <select id="mn-from" value={state.from} onChange={e => controller.setFrom(e.target.value)}>
        {state.days.map(d => <option key={d} value={d}>{bridge.fday(d)}</option>)}
      </select></div>
    <div className="f"><label htmlFor="mn-to">{tr('По')}</label>
      <select id="mn-to" value={state.to} onChange={e => controller.setTo(e.target.value)}>
        {state.days.map(d => <option key={d} value={d}>{bridge.fday(d)}</option>)}
      </select></div>
    <div className="f"><label htmlFor="mn-group">{tr('Строка')}</label>
      <select id="mn-group" value={state.group} onChange={e => controller.setGroup(e.target.value as Group)}>
        <option value="day">{tr('день')}</option><option value="shift">{tr('смена')}</option><option value="loom">{tr('станок')}</option>
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="mn-go" onClick={() => {void controller.load();}}>{tr('Показать')}</button></div>
  </>;
}

function Tiles({data: d, bridge}: {data: ManualResponse; bridge: ManualBridge}) {
  const nf = bridge.nf;
  const t = d.totals;
  const un = unexplainedMinutes(t);
  const items: {label: string; value: React.ReactNode}[] = [
    {label: 'Shed Eff', value: <>{nf(t.shed_eff, 1)}<small> %</small></>},
    {label: 'Time Eff', value: <>{nf(t.time_eff, 1)}<small> %</small></>},
    {label: 'Prod Eff', value: <>{nf(t.prod_eff, 1)}<small> %</small></>},
    {label: 'Длинные остановы', value: <>{nf(t.stop_pct, 1)}<small> % · {nf(t.stop_min / 60)} ч</small></>},
    {label: 'Объяснено тикетами и станком', value: <>{t.explained_pct == null ? '—' : nf(t.explained_pct, 1)}<small> %</small></>},
    {label: 'Без причины', value: <><span className={un ? 'bad' : ''}>{nf(un / 60)}</span><small> ч</small></>},
  ];
  return <>{items.map(it => <div className="tile" key={it.label}>
    <div className="l">{tr(it.label)}</div><div className="v">{it.value}</div></div>)}</>;
}

function Thead({data: d}: {data: ManualResponse}) {
  const keyName = GROUP_KEY_NAME[d.group];
  return <>
    <tr className="grp"><th colSpan={6}/>
      {d.columns.map(c => <th key={c.id} colSpan={4} className={'sep' + noneColClass(c)}>{c.name}</th>)}
    </tr>
    <tr className="cols">
      <th>{tr(keyName)}</th><th className="n">{tr('Станков')}</th><th className="n">Shed Eff %</th>
      <th className="n">Time Eff %</th><th className="n">Prod Eff %</th><th className="n">Tot. Stop %</th>
      {d.columns.map(c => <Fragment key={c.id}>
        <th className={'n sep' + noneColClass(c)}>{tr('Раз')}</th>
        <th className={'n' + noneColClass(c)}>{tr('Мин')}</th>
        <th className={'n' + noneColClass(c)}>{tr('Среднее')}</th>
        <th className={'n' + noneColClass(c)}>%</th>
      </Fragment>)}
    </tr>
  </>;
}

function TableRows({data: d, bridge}: {data: ManualResponse; bridge: ManualBridge}) {
  if (!d.rows.length) {
    return <tr><td className="note" colSpan={6 + d.columns.length * 4}>{tr('За период нет данных')}</td></tr>;
  }
  return <>{d.rows.map(r => <tr key={r.key}>
    <RowCells row={r} columns={d.columns} label={rowKeyLabel(r, d.group, bridge.fday)} nf={bridge.nf}/>
  </tr>)}</>;
}

function RowCells({row: r, columns, label, nf}: {row: ManualRow; columns: Column[]; label: string; nf: (x: unknown, d?: number) => string}) {
  return <>
    <td>{label}</td><td className="n">{r.looms}</td>
    <td className="n">{nf(r.shed_eff, 1)}</td><td className={'n' + paintEff(r.time_eff)}>{nf(r.time_eff, 1)}</td>
    <td className="n">{nf(r.prod_eff, 1)}</td><td className="n">{nf(r.stop_pct, 1)}</td>
    {columns.map(c => <Cell key={c.id} c={c} v={r.cats[c.id]} nf={nf}/>)}
  </>;
}

function Cell({c, v, nf}: {c: Column; v: Cat | undefined; nf: (x: unknown, d?: number) => string}) {
  const cls = noneColClass(c);
  if (!v) return <><td className={'n sep' + cls}/><td className={'n' + cls}/><td className={'n' + cls}/><td className={'n' + cls}/></>;
  const hot = isHotCell(c, v) ? ' bad' : '';
  return <>
    <td className={'n sep' + cls}>{v.n == null ? '—' : nf(v.n)}</td>
    <td className={'n' + cls}>{nf(v.min)}</td>
    <td className={'n' + cls}>{hms(v.avg_sec)}</td>
    <td className={'n' + cls + hot}>{nf(v.pct, 1)}</td>
  </>;
}
