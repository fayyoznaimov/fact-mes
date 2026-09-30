import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { ExplorerBridge } from './bridge';
import { causeColor, causeShare, sortedCauses } from './model';
import type { ExplorerResponse, Group } from './model';
import type { ExplorerController, ExplorerState } from './controller';

type Props = {
  topBar: HTMLElement; tiles: HTMLElement; stack: HTMLElement; legend: HTMLElement; tableBody: HTMLElement;
  state: ExplorerState; bridge: ExplorerBridge; controller: ExplorerController;
};

export function Explorer({topBar, tiles, stack, legend, tableBody, state, bridge, controller}: Props) {
  const data = state.data;
  return <>
    {createPortal(<TopBar state={state} bridge={bridge} controller={controller}/>, topBar)}
    {data && createPortal(<Tiles data={data} bridge={bridge}/>, tiles)}
    {data && createPortal(<Stack data={data}/>, stack)}
    {data && createPortal(<Legend data={data} bridge={bridge}/>, legend)}
    {data && createPortal(<TableRows data={data} bridge={bridge}/>, tableBody)}
  </>;
}

function TopBar({state, bridge, controller}: {state: ExplorerState; bridge: ExplorerBridge; controller: ExplorerController}) {
  return <>
    <div className="f"><label htmlFor="ex-from">{tr('С')}</label>
      <select id="ex-from" value={state.from} onChange={e => controller.setFrom(e.target.value)}>
        {state.days.map(d => <option key={d} value={d}>{bridge.fday(d)}</option>)}
      </select></div>
    <div className="f"><label htmlFor="ex-to">{tr('По')}</label>
      <select id="ex-to" value={state.to} onChange={e => controller.setTo(e.target.value)}>
        {state.days.map(d => <option key={d} value={d}>{bridge.fday(d)}</option>)}
      </select></div>
    <div className="f"><label>{tr('Смены')}</label>
      <div className="chips" id="ex-shifts">
        {['A', 'B', 'C'].map(sh => <button key={sh} type="button" className="chip" aria-pressed={state.shifts.has(sh)}
          onClick={() => controller.toggleShift(sh)}>{sh}</button>)}
      </div></div>
    <div className="f"><label>{tr('Группа')}</label>
      <div className="chips" id="ex-group">
        {([['all', 'все'], ['D', 'махровые D'], ['J', 'жаккард J']] as [Group, string][]).map(([g, label]) =>
          <button key={g} type="button" className="chip" aria-pressed={state.group === g}
            onClick={() => controller.setGroup(g)}>{tr(label)}</button>)}
      </div></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="ex-go" onClick={() => {void controller.load();}}>{tr('Показать')}</button></div>
  </>;
}

function Tiles({data: d, bridge}: {data: ExplorerResponse; bridge: ExplorerBridge}) {
  const nf = bridge.nf;
  const items: {label: string; value: React.ReactNode}[] = [
    {label: 'КПД', value: <>{nf(d.totals.eff, 1)}<small> %</small></>},
    {label: 'Отработано', value: <>{nf(d.totals.run_h)}<small> ч</small></>},
    {label: 'Простой', value: <>{nf(d.totals.stop_h)}<small> ч</small></>},
    {label: 'Выработка', value: <>{nf(d.totals.mpicks, 2)}<small> млн пиков</small></>},
    {label: 'Ручные остановы', value: <>{nf(d.causes['Ручные остановы'] || 0)}<small> ч</small></>},
    {label: 'Смен без работы', value: <>{nf(d.totals.idle_shifts || 0)}<small> из {nf(d.totals.rows)}</small></>},
  ];
  return <>{items.map(it => <div className="tile" key={it.label}>
    <div className="l">{tr(it.label)}</div><div className="v">{it.value}</div></div>)}</>;
}

function Stack({data: d}: {data: ExplorerResponse}) {
  const shares = causeShare(sortedCauses(d.causes));
  return <>{shares.map(s => <div key={s.name} title={`${s.name}: ${s.hours} ч`}
    style={{width: `${s.pct}%`, background: causeColor(s.name)}}/>)}</>;
}

function Legend({data: d, bridge}: {data: ExplorerResponse; bridge: ExplorerBridge}) {
  const shares = causeShare(sortedCauses(d.causes));
  return <>{shares.map(s => <span key={s.name} className="chip" style={{cursor: 'default'}}>
    <b style={{display: 'inline-block', width: 9, height: 9, marginRight: 6, background: causeColor(s.name)}}/>
    {s.name} — {bridge.nf(s.hours)} {tr('ч')}</span>)}</>;
}

function TableRows({data: d, bridge}: {data: ExplorerResponse; bridge: ExplorerBridge}) {
  const nf = bridge.nf;
  return <>{d.by_loom.map(l => <tr key={l.loom}>
    <td><strong>{l.loom}</strong></td><td className={'n' + (l.eff < 60 ? ' bad' : '')}>{nf(l.eff, 1)}</td>
    <td className="n">{nf(l.kpicks)}</td><td className="n">{nf(l.weft_ct)}</td><td className="n">{nf(l.weft_cmpx, 1)}</td>
    <td className="n">{nf(l.warp_ct)}</td><td className="n">{nf(l.top_ct)}</td>
    <td className="n">{nf(l.manual_ct)}</td><td className="n">{nf(l.manual_h, 1)}</td>
    <td className="n">{nf(l.wait_h, 1)}</td><td className="n">{nf(l.warp_out_h, 1)}</td>
    <td className="n">{nf(l.other_h, 1)}</td><td className="n">{nf(l.power_h, 1)}</td>
    <td className="n">{l.shifts}{l.idle_shifts
      ? <span className="note" title="смены, где станок не работал (≤ 5 мин)"> · {l.idle_shifts} {tr('без работы')}</span>
      : null}</td>
  </tr>)}</>;
}
