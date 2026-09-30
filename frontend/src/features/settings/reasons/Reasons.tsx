import { createPortal } from 'react-dom';
import { tr } from '../../setup/bridge';
import type { SettingsBridge } from '../bridge';
import { appliesLabel, categoryLabel, places } from './model';
import type { Reason, ReasonsResponse } from './model';
import type { ReasonsController, ReasonsState } from './controller';

type Props = {
  topBar: HTMLElement; tableBody: HTMLElement;
  state: ReasonsState; bridge: SettingsBridge;
};

export function Reasons({topBar, tableBody, state, bridge}: Props) {
  return <>
    {createPortal(<TopBar bridge={bridge}/>, topBar)}
    {state.data && createPortal(<Rows data={state.data} bridge={bridge}/>, tableBody)}
  </>;
}

function TopBar({bridge}: {bridge: SettingsBridge}) {
  return <>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="rs-add" onClick={() => bridge.openReasonDialog('')}>{tr('Добавить причину…')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="rs-docs" onClick={bridge.showReasonChanges}>{tr('Изменения справочника')}</button></div>
  </>;
}

function Rows({data, bridge}: {data: ReasonsResponse; bridge: SettingsBridge}) {
  return <>{data.reasons.map(r => <Row key={r.id} r={r} data={data} bridge={bridge}/>)}</>;
}

function Row({r, data, bridge}: {r: Reason; data: ReasonsResponse; bridge: SettingsBridge}) {
  const placeList = places(r);
  return <tr style={r.active ? undefined : {opacity: 0.55}}>
    <td>{r.color ? <span style={{display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: r.color, marginRight: 6}}/> : null}
      {r.name}<br/><span className="note">{r.id}</span></td>
    <td>{r.reason}</td><td>{tr(categoryLabel(data, r.category))}</td><td>{tr(appliesLabel(data, r.applies))}</td>
    <td>{placeList.length ? placeList.map(tr).join(', ') : '—'}</td>
    <td className="n">{r.sort}</td>
    <td>{r.active ? tr('действует') : tr('скрыта')}{r.important ? ', ' + tr('важная') : ''}</td>
    <td><button className="act" onClick={() => bridge.openReasonDialog(r.id)}>{tr('Изменить…')}</button></td>
  </tr>;
}
