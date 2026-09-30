import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { WalkBridge } from './bridge';
import { shiftLabel, styleText } from './model';
import type { WalkResponse, WalkRow } from './model';
import type { WalkController, WalkState } from './controller';

type Props = {
  topBar: HTMLElement; tableBody: HTMLElement;
  state: WalkState; bridge: WalkBridge; controller: WalkController;
};

export function Walk({topBar, tableBody, state, bridge, controller}: Props) {
  const data = state.data;
  return <>
    {createPortal(<TopBar state={state} bridge={bridge} controller={controller}/>, topBar)}
    {data && createPortal(<TableRows data={data} bridge={bridge}/>, tableBody)}
  </>;
}

function TopBar({state, bridge, controller}: {state: WalkState; bridge: WalkBridge; controller: WalkController}) {
  return <>
    <div className="f"><label htmlFor="wk-shift">{tr('Смена')}</label>
      <select id="wk-shift" value={state.shiftIndex} onChange={e => {
        controller.setShiftIndex(+e.target.value); void controller.load();
      }}>
        {state.shifts.map((s, i) => <option key={i} value={i}>{shiftLabel(bridge.fday, s)}</option>)}
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="wk-go" onClick={() => {void controller.load();}}>{tr('Показать')}</button></div>
  </>;
}

function TableRows({data, bridge}: {data: WalkResponse; bridge: WalkBridge}) {
  const nf = bridge.nf;
  return <>{data.rows.map(r => <Row key={r.loom} r={r} nf={nf}/>)}</>;
}

function Row({r, nf}: {r: WalkRow; nf: (x: unknown, d?: number) => string}) {
  const style = styleText(r.style);
  return <tr>
    <td><strong>{r.loom}</strong>{r.idle ? <span className="note"> {tr('вся смена')}</span> : null}</td>
    <td>{style ?? <span className="note">{tr('не задан')}</span>}</td>
    <td>{r.main}</td><td className="n">{nf(r.main_min)}</td>
    <td className={'n' + (r.eff < 60 ? ' bad' : '')}>{nf(r.eff, 1)}</td><td className="n">{nf(r.stop_min)}</td>
    <td className="n">{nf(r.weft_ct)}</td><td className="n">{nf(r.top_ct)}</td><td className="n">{nf(r.warp_ct)}</td>
    <td className="n">{nf(r.manual_ct)}</td><td className={'n' + (r.wait_min > 60 ? ' bad' : '')}>{nf(r.wait_min)}</td>
  </tr>;
}
