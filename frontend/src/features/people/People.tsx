import { createPortal } from 'react-dom';
import { tr } from '../setup/bridge';
import type { PeopleBridge } from './bridge';
import { roleLabel } from './model';
import type { Operator } from './model';
import type { PeopleController, PeopleState } from './controller';

type Props = {
  topBar: HTMLElement; pasteBar: HTMLElement; tableBody: HTMLElement;
  state: PeopleState; bridge: PeopleBridge; controller: PeopleController;
};

export function People({topBar, pasteBar, tableBody, state, bridge, controller}: Props) {
  return <>
    {createPortal(<TopBar state={state} controller={controller}/>, topBar)}
    {createPortal(<PasteBox state={state} controller={controller}/>, pasteBar)}
    {createPortal(<TableRows state={state} bridge={bridge} controller={controller}/>, tableBody)}
  </>;
}

function TopBar({state, controller}: {state: PeopleState; controller: PeopleController}) {
  return <>
    <div className="f"><label htmlFor="op-code">{tr('Код')}</label>
      <input id="op-code" size={8} autoComplete="off" value={state.form.code} onChange={e => controller.setCode(e.target.value)}/></div>
    <div className="f"><label htmlFor="op-name">{tr('Имя')}</label>
      <input id="op-name" size={22} autoComplete="off" value={state.form.name} onChange={e => controller.setName(e.target.value)}/></div>
    <div className="f"><label htmlFor="op-role">{tr('Роль')}</label>
      <select id="op-role" value={state.form.role} onChange={e => controller.setRole(e.target.value)}>
        <option value="operator">{tr('оператор')}</option>
        <option value="master">{tr('мастерица')}</option>
        <option value="foreman">{tr('мастер')}</option>
      </select></div>
    <div className="f"><label>{' '}</label>
      <button className="act primary" id="op-add" onClick={() => {void controller.add();}}>{tr('Добавить')}</button></div>
    <div className="f"><label>{' '}</label>
      <button className="act" id="op-import" onClick={() => {void controller.importFact();}}>{tr('Взять имена из FACT')}</button></div>
  </>;
}

function PasteBox({state, controller}: {state: PeopleState; controller: PeopleController}) {
  return <>
    <p className="note">{tr('Выделите строки в таблице пользователей (удобнее — вместе с заголовком) или в')}{' '}
      {tr('Excel, скопируйте и вставьте сюда. Человек ищется по табельному номеру — это тот же код, что')}{' '}
      {tr('у оператора в FACT: знакомым обновятся имя, должность и блокировка, новые добавятся.')}{' '}
      {tr('Должность «Мастер» и «Мастерица» — это мастерица, «Мастер смены» — мастер смены;')}{' '}
      {tr('поправить роль можно прямо в таблице ниже. Повторы считаются один раз.')}</p>
    <textarea id="op-paste" rows={7} style={{font: "12px 'IBM Plex Mono',monospace", width: '100%'}}
      placeholder={'Отображаемое имя\tФамилия\tИмя\tОтчество\tТабельный номер\tДолжность'}
      value={state.pasteText} onChange={e => controller.setPasteText(e.target.value)}/>
    <div style={{display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap'}}>
      <button className="act primary" id="op-paste-go" onClick={() => {void controller.importPaste();}}>{tr('Загрузить')}</button>
      <span className="note" id="op-paste-res">{state.pasteResult}</span></div>
  </>;
}

function TableRows({state, bridge, controller}: {state: PeopleState; bridge: PeopleBridge; controller: PeopleController}) {
  if (!state.operators.length) {
    return <tr><td colSpan={5} className="note">{tr('Справочник пуст. Добавьте людей или возьмите имена из FACT.')}</td></tr>;
  }
  const editable = bridge.can('people');
  return <>{state.operators.map(o => <Row key={o.id} o={o} editable={editable} controller={controller}/>)}</>;
}

function Row({o, editable, controller}: {o: Operator; editable: boolean; controller: PeopleController}) {
  return <tr>
    <td className="n">{o.code}</td><td>{o.name}</td>
    <td>{editable
      ? <select aria-label={`${tr('Роль')}: ${o.name}`} value={o.role} onChange={e => {void controller.setOperatorRole(o.id, e.target.value);}}>
          <option value="operator">{tr('оператор')}</option>
          <option value="master">{tr('мастерица')}</option>
          <option value="foreman">{tr('мастер')}</option>
        </select>
      : roleLabel(o.role)}</td>
    <td>{o.active ? <span className="ok">{tr('да')}</span> : tr('нет')}</td>
    <td><button className="act" onClick={() => {void controller.remove(o.id);}}>{tr('Удалить')}</button></td>
  </tr>;
}
