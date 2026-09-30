import { createPortal } from 'react-dom';
import { tr } from '../../setup/bridge';
import type { SettingsBridge } from '../bridge';
import { docStatusLabel, unitLabel } from './model';
import type { RatePeriod } from './model';
import type { RateController, RateState } from './controller';

type Props = {
  topBar: HTMLElement; tableBody: HTMLElement;
  state: RateState; bridge: SettingsBridge; controller: RateController;
};

export function Rate({topBar, tableBody, state, bridge, controller}: Props) {
  return <>
    {createPortal(<TopBar state={state} controller={controller}/>, topBar)}
    {state.loaded && createPortal(<Rows periods={state.periods} bridge={bridge}/>, tableBody)}
  </>;
}

function TopBar({state, controller}: {state: RateState; controller: RateController}) {
  return <>
    <div className="f"><label htmlFor="set-from">{tr('Действует с')}</label>
      <input id="set-from" type="date" value={state.from} onChange={e => controller.setFrom(e.target.value)}/></div>
    <div className="f"><label htmlFor="set-rate">{tr('Ставка, сум')}</label>
      <input id="set-rate" size={10} inputMode="decimal" value={state.rate} onChange={e => controller.setRate(e.target.value)}/></div>
    <div className="f"><label htmlFor="set-unit">{tr('За что')}</label>
      <select id="set-unit" value={state.unit} onChange={e => controller.setUnit(e.target.value as 'kpick' | 'pick')}>
        <option value="kpick">{tr('за 1000 пиков')}</option><option value="pick">{tr('за один пик')}</option>
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="set-save" onClick={() => {void controller.save();}}>{tr('Проверить и провести…')}</button></div>
  </>;
}

function Rows({periods, bridge}: {periods: RatePeriod[]; bridge: SettingsBridge}) {
  return <>{periods.map(p => <tr key={p.id} style={p.status === 'cancelled' ? {opacity: 0.55} : undefined}>
    <td>{bridge.fday(p.valid_from)}</td><td className="n">{bridge.nf(p.rate, 2)}</td><td>{tr(unitLabel(p.unit))}</td>
    <td>{p.doc_id
      ? <>{p.number ? <button className="act" data-doc={p.doc_id}>{p.number}</button> : null} {p.status ? <span className={'doc-status ' + p.status}>{tr(docStatusLabel(p.status))}</span> : null}</>
      : <span className="note">{tr('начальная настройка')}</span>}</td>
    <td>{p.set_by}</td><td>{bridge.ftime(p.set_at)}</td>
  </tr>)}</>;
}
