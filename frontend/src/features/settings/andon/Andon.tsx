import { createPortal } from 'react-dom';
import { tr } from '../../setup/bridge';
import type { AndonController, AndonState } from './controller';

type Props = {topBar: HTMLElement; state: AndonState; controller: AndonController};

export function Andon({topBar, state, controller}: Props) {
  return createPortal(<TopBar state={state} controller={controller}/>, topBar);
}

function TopBar({state, controller}: {state: AndonState; controller: AndonController}) {
  return <>
    <div className="f"><label htmlFor="an-warn">{tr('Тикет, если стоит дольше, мин')}</label>
      <input id="an-warn" size={4} inputMode="numeric" value={state.warn} onChange={e => controller.setWarn(e.target.value)}/></div>
    <div className="f"><label htmlFor="an-alarm">{tr('Тревога на доске через, мин')}</label>
      <input id="an-alarm" size={4} inputMode="numeric" value={state.alarm} onChange={e => controller.setAlarm(e.target.value)}/></div>
    <div className="f"><label htmlFor="an-notify">{tr('Мастеру в телеграм через, мин')}</label>
      <input id="an-notify" size={4} inputMode="numeric" value={state.notify} onChange={e => controller.setNotify(e.target.value)}/></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="an-save" onClick={() => {void controller.save();}}>{tr('Сохранить')}</button></div>
  </>;
}
