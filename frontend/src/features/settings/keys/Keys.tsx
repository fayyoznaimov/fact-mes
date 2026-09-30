import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { tr } from '../../setup/bridge';
import type { SettingsBridge } from '../bridge';
import { ALL_SCOPES, scopesText } from './model';
import type { ApiKey, Scope } from './model';
import type { KeysController, KeysState } from './controller';

type Props = {
  topBar: HTMLElement; revealBox: HTMLElement; tableBody: HTMLElement;
  state: KeysState; bridge: SettingsBridge; controller: KeysController;
};

export function Keys({topBar, revealBox, tableBody, state, bridge, controller}: Props) {
  useEffect(() => { revealBox.classList.toggle('hidden', !state.revealedKey); }, [revealBox, state.revealedKey]);
  return <>
    {createPortal(<TopBar state={state} controller={controller}/>, topBar)}
    {createPortal(<>
      <p className="note">{tr('Ключ показывается один раз — скопируйте его сейчас и передайте программисту 1С:')}</p>
      <div className="keybox" id="key-value">{state.revealedKey}</div>
    </>, revealBox)}
    {state.loaded && createPortal(<Rows state={state} bridge={bridge} controller={controller}/>, tableBody)}
  </>;
}

function TopBar({state, controller}: {state: KeysState; controller: KeysController}) {
  return <>
    <div className="f"><label htmlFor="key-name">{tr('Для кого')}</label>
      <input id="key-name" size={18} placeholder="1С, бот, BI" value={state.name} onChange={e => controller.setName(e.target.value)}/></div>
    <div className="f"><label>{tr('Права')}</label>
      <div className="checks">{ALL_SCOPES.map(s => <label key={s}>
        <input type="checkbox" value={s} checked={state.selectedScopes.has(s)} onChange={() => controller.toggleScope(s)}/> {tr(SCOPE_LABEL[s])}
      </label>)}</div></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="key-add" onClick={() => {void controller.add();}}>{tr('Выдать ключ')}</button></div>
    <div className="f"><label>{' '}</label>
      <a className="act" href="/api/docs" target="_blank" rel="noreferrer">{tr('Описание API')}</a></div>
  </>;
}

const SCOPE_LABEL: Record<Scope, string> = {read: 'читать', write: 'присылать заказы', tickets: 'тикеты'};

function Rows({state, bridge, controller}: {state: KeysState; bridge: SettingsBridge; controller: KeysController}) {
  if (!state.keys.length) return <tr><td colSpan={6} className="note">{tr('Ключей пока нет.')}</td></tr>;
  return <>{state.keys.map(k => <Row key={k.id} k={k} state={state} bridge={bridge} controller={controller}/>)}</>;
}

function Row({k, state, bridge, controller}: {k: ApiKey; state: KeysState; bridge: SettingsBridge; controller: KeysController}) {
  return <tr className={k.active ? '' : 'note'}>
    <td>{k.name}</td><td className="n">{k.prefix}…</td>
    <td>{scopesText(k, state.scopes)}</td>
    <td className="n">{(k.created_at || '').slice(0, 16)}</td>
    <td className="n">{k.last_used_at ? bridge.ftime(k.last_used_at) : '—'}</td>
    <td>{k.active ? <button className="act" onClick={() => {void controller.revoke(k.id);}}>{tr('Отозвать')}</button> : tr('отозван')}</td>
  </tr>;
}
