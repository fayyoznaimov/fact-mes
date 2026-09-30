import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { SalaryBridge } from './bridge';
import { mastersText, noteText, operatorOptions, rateUnitLabel, shiftLabel } from './model';
import type { SalaryLoomRow, SalaryOperatorRow, SalaryResponse } from './model';
import type { SalaryController, SalaryState } from './controller';

type Props = {
  topBar: HTMLElement; tiles: HTMLElement; note: HTMLElement;
  tableBody: HTMLElement; tableFoot: HTMLElement;
  loomsBody: HTMLElement; loomsFoot: HTMLElement;
  state: SalaryState; bridge: SalaryBridge; controller: SalaryController;
};

export function Salary({topBar, tiles, note, tableBody, tableFoot, loomsBody, loomsFoot, state, bridge, controller}: Props) {
  const data = state.data;
  return <>
    {createPortal(<TopBar state={state} bridge={bridge} controller={controller}/>, topBar)}
    {data && createPortal(<Tiles data={data} bridge={bridge}/>, tiles)}
    {data && createPortal(noteText(data, bridge.nf), note)}
    {data && createPortal(<LoomRows data={data} bridge={bridge} controller={controller}/>, loomsBody)}
    {data && createPortal(<LoomFoot data={data} bridge={bridge}/>, loomsFoot)}
    {data && createPortal(<OperatorRows data={data} bridge={bridge}/>, tableBody)}
    {data && createPortal(<OperatorFoot data={data} bridge={bridge}/>, tableFoot)}
  </>;
}

function TopBar({state, bridge, controller}: {state: SalaryState; bridge: SalaryBridge; controller: SalaryController}) {
  return <>
    <div className="f"><label htmlFor="sal-shift">{tr('Смена')}</label>
      <select id="sal-shift" value={state.shiftIndex} onChange={e => {
        controller.setShiftIndex(+e.target.value); void controller.load();
      }}>
        {state.shifts.map((s, i) => <option key={i} value={i}>{shiftLabel(bridge.fday, s)}</option>)}
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="sal-go" onClick={() => {void controller.load();}}>{tr('Посчитать')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="sal-copy" onClick={() => {void controller.copy();}}>{tr('Повторить расстановку прошлой смены')}</button></div>
  </>;
}

function Tiles({data: d, bridge}: {data: SalaryResponse; bridge: SalaryBridge}) {
  const nf = bridge.nf;
  const items: {label: string; value: React.ReactNode}[] = [
    {label: 'Начислено', value: <>{nf(d.totals.salary)}<small> сум</small></>},
    {label: 'Не распределено', value: <>{nf(d.totals.unassigned_salary)}<small> сум</small></>},
    {label: 'Выработка', value: <>{nf(d.totals.kpicks)}<small> тыс. пиков</small></>},
    {label: 'Операторов', value: d.operators.length},
    {label: 'Станков закреплено', value: <>{d.totals.assigned}<small> / {d.totals.looms}</small></>},
    {label: 'Ставка', value: <>{nf(d.rate)}<small> сум {rateUnitLabel(d.rate_unit)}</small></>},
    {label: 'Мастерицы', value: mastersText(d.masters)},
  ];
  return <>{items.map(it => <div className="tile" key={it.label}>
    <div className="l">{tr(it.label)}</div><div className="v">{it.value}</div></div>)}</>;
}

function LoomRows({data: d, bridge, controller}: {data: SalaryResponse; bridge: SalaryBridge; controller: SalaryController}) {
  const nf = bridge.nf;
  if (!d.looms.length) return null;
  const opts = operatorOptions(bridge.operators());
  return <>{d.looms.map(l => <LoomRow key={l.loom} row={l} nf={nf} opts={opts} controller={controller}/>)}</>;
}

function LoomRow({row: l, nf, opts, controller}: {
  row: SalaryLoomRow; nf: (x: unknown, d?: number) => string;
  opts: {value: string; label: string}[]; controller: SalaryController;
}) {
  return <tr>
    <td><b>{l.loom}</b></td><td>{l.style}</td>
    <td className="n">{nf(l.kpicks, 1)}</td>
    <td className="n"><strong>{nf(l.salary)}</strong></td>
    <td className={'n' + (l.effic != null && l.effic < 60 ? ' bad' : '')}>{l.effic != null ? nf(l.effic, 1) : ''}</td>
    <td className="n">{nf(l.weft_ct)}</td><td className="n">{nf(l.warp_ct)}</td>
    <td className={'n' + (l.wait_min > 60 ? ' bad' : '')}>{nf(l.wait_min)}</td>
    <td><select data-assign={l.loom} value={l.operator_id != null ? String(l.operator_id) : ''}
      onChange={e => {void controller.assign(l.loom, e.target.value ? Number(e.target.value) : null);}}>
      {opts.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select></td>
  </tr>;
}

function LoomFoot({data: d, bridge}: {data: SalaryResponse; bridge: SalaryBridge}) {
  const nf = bridge.nf;
  if (!d.looms.length) return null;
  return <tr><td colSpan={2}>{tr('Итого')}</td>
    <td className="n">{nf(d.totals.kpicks, 1)}</td>
    <td className="n">{nf(d.totals.salary_all)}</td><td colSpan={5}/></tr>;
}

function OperatorRows({data: d, bridge}: {data: SalaryResponse; bridge: SalaryBridge}) {
  const nf = bridge.nf;
  if (!d.operators.length) {
    return <tr><td colSpan={10} className="note">{tr('На эту смену никто не назначен. Откройте вкладку «Смена».')}</td></tr>;
  }
  return <>{d.operators.map(o => <OperatorRow key={o.operator_id} row={o} nf={nf}/>)}</>;
}

function OperatorRow({row: o, nf}: {row: SalaryOperatorRow; nf: (x: unknown, d?: number) => string}) {
  return <tr>
    <td className="n">{o.code}</td><td>{o.name}</td><td>{o.looms.join(', ')}</td>
    <td className="n">{o.loom_count}</td><td className="n">{nf(o.kpicks, 1)}</td>
    <td className="n"><strong>{nf(o.salary)}</strong></td>
    <td className={'n' + (o.effic < 60 ? ' bad' : '')}>{nf(o.effic, 1)}</td>
    <td className="n">{nf(o.weft_cmpx, 1)}</td><td className="n">{nf(o.warp_cmpx, 1)}</td>
    <td className={'n' + (o.wait_min > 60 ? ' bad' : '')}>{nf(o.wait_min)}</td>
  </tr>;
}

function OperatorFoot({data: d, bridge}: {data: SalaryResponse; bridge: SalaryBridge}) {
  const nf = bridge.nf;
  if (!d.operators.length) return null;
  return <tr><td colSpan={4}>{tr('Итого')}</td>
    <td className="n">{nf(d.totals.kpicks, 1)}</td><td className="n">{nf(d.totals.salary)}</td>
    <td colSpan={4}/></tr>;
}
