import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { UsersBridge } from './bridge';
import { tr } from './bridge';
import { accessSummary, copySourceOptions, effectiveAccess, employeeOptions, forbiddenPermission, forbiddenSection, genPassword, isPreset } from './model';
import type { UsersController, UsersState } from './controller';

type Props = {
  bar: HTMLElement;
  tbody: HTMLElement;
  dialog: HTMLDialogElement;
  pwDialog: HTMLDialogElement;
  state: UsersState;
  bridge: UsersBridge;
  controller: UsersController;
};

export function Users({bar, tbody, dialog, pwDialog, state, bridge, controller}: Props) {
  return <>
    {createPortal(<div className="f"><label>{' '}</label>
      <button className="act primary" id="u-new" onClick={() => {void controller.openDialog(null);}}>{tr('Добавить пользователя…')}</button>
    </div>, bar)}
    {createPortal(<UsersRows state={state} bridge={bridge} controller={controller}/>, tbody)}
    {state.dialog && state.catalog && createPortal(
      <UserDialog dialog={dialog} state={state} bridge={bridge} controller={controller}/>, dialog)}
    {state.pw && createPortal(
      <PasswordDialog dialog={pwDialog} pw={state.pw} controller={controller}/>, pwDialog)}
  </>;
}

function UsersRows({state, bridge, controller}: {state: UsersState; bridge: UsersBridge; controller: UsersController}) {
  if (state.loaded && !state.rows.length) return <tr><td colSpan={7} className="note">{tr('Пользователей пока нет.')}</td></tr>;
  const roles = bridge.roles();
  return <>{state.rows.map(u => {
    const summary = accessSummary(u);
    return <tr key={u.id}>
      <td data-i18n-skip>{u.login}</td><td data-i18n-skip>{u.name}</td>
      <td>{tr(roles[u.role] || u.role)}{u.employee_id ? <><br/><small className="note">{'сотрудник №' + u.employee_id}</small></> : null}</td>
      <td>{tr(summary.mode)} · {summary.count}</td>
      <td>{tr(u.active ? 'Да' : 'Нет')}</td>
      <td className="n">{u.last_login ? bridge.ftime(u.last_login) : '—'}</td>
      <td>
        <button className="act" onClick={() => {void controller.openDialog(u);}}>{tr('Изменить')}</button>{' '}
        <button className="act" onClick={() => controller.openPassword(u)}>{tr('Пароль…')}</button>{' '}
        <button className="act" onClick={() => {void controller.toggleActive(u);}}>{tr(u.active ? 'Отключить' : 'Включить')}</button>
      </td>
    </tr>;
  })}</>;
}

function UserDialog({dialog, state, bridge, controller}: {dialog: HTMLDialogElement; state: UsersState; bridge: UsersBridge; controller: UsersController}) {
  const d = state.dialog!;
  const catalog = state.catalog!;
  const loginRef = useRef<HTMLInputElement>(null), nameRef = useRef<HTMLInputElement>(null);
  const passRef = useRef<HTMLInputElement>(null), mustRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (!dialog.open) dialog.showModal(); }, [dialog]);
  useEffect(() => {
    const onClose = () => controller.closeDialog();
    dialog.addEventListener('close', onClose);
    return () => dialog.removeEventListener('close', onClose);
  }, [dialog, controller]);

  const roles = bridge.roles();
  const admin = d.role === 'admin';
  const preset = isPreset(d.role, d.mode);
  const access = effectiveAccess(d.role, d.mode, d.draft, catalog);
  const currentEmployeeId = d.editId ? state.rows.find(x => x.id === d.editId)?.employee_id ?? null : null;
  const employees = employeeOptions(state.operators, state.rows, d.editId, currentEmployeeId);
  const copySources = copySourceOptions(state.rows, d.editId);
  const showEmployee = d.role === 'master';

  const onAdd = async () => {
    const login = loginRef.current?.value.trim().toLowerCase() || '';
    const name = nameRef.current?.value.trim() || '', password = passRef.current?.value || '';
    const must = mustRef.current?.checked || false;
    await controller.save(login, name, password, must);
  };

  return <form method="dialog" key={d.editId ?? 'new'}>
    <h3>{d.editId ? tr('Пользователь') + ' ' + d.login : tr('Новый пользователь')}</h3>
    <div className="bar">
      <div className="f"><label htmlFor="u-login">{tr('Логин')}</label>
        <input id="u-login" size={14} autoComplete="off" pattern="[a-z0-9][a-z0-9._\-]{1,31}" defaultValue={d.login} disabled={d.loginLocked} ref={loginRef}/></div>
      <div className="f"><label htmlFor="u-name">{tr('Имя')}</label>
        <input id="u-name" size={22} autoComplete="off" defaultValue={d.name} ref={nameRef}/></div>
      <div className="f"><label htmlFor="u-role">{tr('Роль')}</label>
        <select id="u-role" value={d.role} onChange={e => controller.setRole(e.target.value)}>
          {Object.entries(roles).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select></div>
      <div className={'f' + (showEmployee ? '' : ' hidden')} id="u-emp-wrap">
        <label htmlFor="u-emp">{tr('Сотрудник — её карточка')}</label>
        <select id="u-emp" value={d.employeeId} onChange={e => controller.setEmployeeId(e.target.value)}>
          <option value="">{'— не связана —'}</option>
          {employees.map(o => <option key={o.id} value={o.id}>{o.name} ({o.code})</option>)}
        </select></div>
    </div>
    <p className={'note' + (showEmployee ? '' : ' hidden')} id="u-emp-note">{tr('Мастерица со связанной карточкой правит расстановку своей смены и в ней отмечена сама.')}</p>
    <div className={'bar' + (d.editId ? ' hidden' : '')} id="u-pass-wrap">
      <div className="f"><label htmlFor="u-pass">{tr('Пароль')}</label>
        <input id="u-pass" type="text" size={16} autoComplete="new-password" spellCheck={false} defaultValue={d.password} ref={passRef}/></div>
      <div className="f"><label>{' '}</label>
        <button type="button" className="act" onClick={() => { if (passRef.current) passRef.current.value = genPassword(); }}>{tr('Придумать')}</button></div>
      <label className="ack"><input type="checkbox" ref={mustRef}/> {tr('попросить сменить пароль при первом входе')}</label>
    </div>
    <div className="bar">
      <div className="f"><label htmlFor="u-mode">{tr('Доступ')}</label>
        <select id="u-mode" value={d.mode} disabled={admin} onChange={e => controller.setMode(e.target.value as 'role' | 'custom')}>
          <option value="role">{tr('как у роли')}</option><option value="custom">{tr('выбрать вручную')}</option>
        </select></div>
      <div className="f"><label htmlFor="u-copy">{tr('Скопировать доступ у')}</label>
        <select id="u-copy" defaultValue="" onChange={e => { if (e.target.value) controller.copyFrom(e.target.value); }}>
          <option value="">—</option>
          {copySources.map(x => <option key={x.id} value={x.id}>{x.name} ({x.login})</option>)}
        </select></div>
    </div>
    <div className="access-panel" id="u-access">
      <fieldset><legend>{tr('Что пользователь видит')}</legend><div className="access-grid" id="u-sections">
        {catalog.sections.filter(x => !x.legacy).map(x => <label key={x.id}>
          <input type="checkbox" checked={access.sections.includes(x.id)} disabled={preset || forbiddenSection(x, admin)}
            onChange={() => controller.toggleSection(x.id)}/><span>{document.documentElement.lang === 'en' ? (x.name_en || x.name) : x.name}</span></label>)}
      </div></fieldset>
      <fieldset><legend>{tr('Что пользователь может менять')}</legend><div className="access-grid" id="u-actions">
        {catalog.permissions.map(x => <label key={x.id}>
          <input type="checkbox" checked={access.permissions.includes(x.id)} disabled={preset || forbiddenPermission(x, admin)}
            onChange={() => controller.togglePermission(x.id)}/><span>{document.documentElement.lang === 'en' ? (x.name_en || x.name) : x.name}</span></label>)}
      </div></fieldset>
      <p className="note">{tr(admin ? 'Администратор: полный доступ.' : 'Для просмотра оставьте действия выключенными.')}</p>
    </div>
    <p className="err" role="alert">{d.err}</p>
    <div className="btns"><button className="act" value="cancel" formNoValidate>{tr('Отмена')}</button>
      <button className="act primary" type="button" disabled={d.saving} onClick={() => {void onAdd();}}>{tr(d.editId ? 'Сохранить' : 'Создать')}</button></div>
  </form>;
}

function PasswordDialog({dialog, pw, controller}: {dialog: HTMLDialogElement; pw: NonNullable<UsersState['pw']>; controller: UsersController}) {
  const passRef = useRef<HTMLInputElement>(null), mustRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (!dialog.open) dialog.showModal(); }, [dialog]);
  useEffect(() => {
    const onClose = () => controller.closePassword();
    dialog.addEventListener('close', onClose);
    return () => dialog.removeEventListener('close', onClose);
  }, [dialog, controller]);
  const onSave = async () => {
    const password = passRef.current?.value || '', must = mustRef.current?.checked || false;
    await controller.savePassword(password, must);
  };
  return <form method="dialog" key={pw.userId}>
    <h3>{tr('Пароль для') + ' ' + pw.login}</h3>
    <div className="bar">
      <div className="f"><label htmlFor="u-pw">{tr('Новый пароль')}</label>
        <input id="u-pw" type="text" size={18} autoComplete="new-password" spellCheck={false} defaultValue={pw.password} ref={passRef}/></div>
      <div className="f"><label>{' '}</label>
        <button type="button" className="act" onClick={() => { if (passRef.current) { passRef.current.value = genPassword(); passRef.current.select(); } }}>{tr('Придумать')}</button></div>
    </div>
    <label className="ack"><input type="checkbox" ref={mustRef}/> {tr('попросить сменить при следующем входе')}</label>
    <p className="note">{tr('Все открытые сеансы этого пользователя закроются.')}</p>
    <p className="err" role="alert">{pw.err}</p>
    <div className="btns"><button className="act" value="cancel" formNoValidate>{tr('Отмена')}</button>
      <button className="act primary" type="button" disabled={pw.saving} onClick={() => {void onSave();}}>{tr('Задать пароль')}</button></div>
  </form>;
}
