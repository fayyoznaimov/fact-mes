import { useRef } from 'react';
import { createPortal } from 'react-dom';
import type { PlanBridge } from '../bridge';
import type { OrdersState } from './controller';
import { PLAN_LIMIT, planOnlyNote, pptSourcesNote, progressColour, tiles } from './model';

type Props = {
  formBar: HTMLElement; pptBar: HTMLElement; productsList: HTMLElement;
  tilesEl: HTMLElement; tableBody: HTMLElement; pptNote: HTMLElement;
  state: OrdersState; bridge: PlanBridge;
  addOrder: (orderNo: string, product: string, qty: number, due: string) => Promise<boolean>;
  importFrom1c: () => void;
  toggleClosed: () => void;
  showAllOrders: () => void;
  assign: (orderId: number, loom: string) => void;
  toggleClose: (orderId: number, closed: boolean | undefined) => void;
  savePpt: (key: string, ppt: number, panels: number | null) => Promise<boolean>;
};

export function Orders({formBar, pptBar, productsList, tilesEl, tableBody, pptNote, state, bridge,
  addOrder, importFrom1c, toggleClosed, showAllOrders, assign, toggleClose, savePpt}: Props) {
  const {nf, fday} = bridge;
  const canPlan = bridge.can('plan_edit'), canSetup = bridge.can('setup_edit');
  const dmy = (d: string) => d ? d.slice(8, 10) + '.' + d.slice(5, 7) : '';
  const orderRef = useRef<HTMLInputElement>(null), productRef = useRef<HTMLInputElement>(null);
  const qtyRef = useRef<HTMLInputElement>(null), dueRef = useRef<HTMLInputElement>(null);
  const assignInputs = useRef<Record<number, HTMLInputElement | null>>({});
  const pptKeyRef = useRef<HTMLInputElement>(null), pptValRef = useRef<HTMLInputElement>(null), pptPanelsRef = useRef<HTMLInputElement>(null);

  const onAdd = async () => {
    const orderNo = orderRef.current?.value.trim() || '', product = productRef.current?.value.trim() || '';
    const qty = Number(qtyRef.current?.value), due = dueRef.current?.value || '';
    if (await addOrder(orderNo, product, qty, due)) {
      if (orderRef.current) orderRef.current.value = '';
      if (qtyRef.current) qtyRef.current.value = '';
    }
  };
  const onSavePpt = async () => {
    const key = pptKeyRef.current?.value.trim() || '', ppt = Number(pptValRef.current?.value);
    const panels = Number(pptPanelsRef.current?.value) || null;
    if (await savePpt(key, ppt, panels) && pptValRef.current) pptValRef.current.value = '';
  };

  const shown = state.showAll ? state.orders : state.orders.slice(0, PLAN_LIMIT);
  const rows = !state.orders.length
    ? <tr><td colSpan={11} className="note">План пуст. Добавьте заказ или возьмите из 1С.</td></tr>
    : <>
      {shown.map(x => {
        const pct = Math.min(100, x.percent), colour = progressColour(x.late_days);
        return <tr key={x.id}>
          <td><b>{x.order_no}</b><br/><small>{x.source || ''}</small></td>
          <td>{x.product_code}</td>
          <td className="n">{nf(x.qty_towels)}</td>
          <td className="n">{nf(x.done)}</td>
          <td><div style={{background: 'var(--hair)', height: 14, width: 120, position: 'relative'}}>
            <div style={{background: colour, height: 14, width: pct + '%'}}/>
            <span style={{position: 'absolute', left: 4, top: 0, fontSize: 11}}>{nf(x.percent, 1)}%</span>
          </div></td>
          <td className="n">{x.rate_per_day ? nf(x.rate_per_day) : '—'}</td>
          <td className="n">{x.days_left != null ? nf(x.days_left, 1) : '—'}</td>
          <td>{x.eta ? fday(x.eta) : '—'}</td>
          <td>{x.due_day ? fday(x.due_day) : '—'}
            {x.late_days != null && <><br/><small className={x.late_days > 0 ? 'bad' : 'ok'}>
              {x.late_days > 0 ? `отстаём на ${nf(x.late_days, 1)} дн.` : 'успеваем'}</small></>}
          </td>
          {x.plan ? <td>
            {x.looms.map((l, i) => <span key={l.loom} title={`по плану ${dmy(l.from_day)}–${dmy(l.to_day || '')}, ${l.days} дн.`}>
              {i > 0 ? ', ' : ''}{l.loom} <small>{nf(l.done)}</small></span>)}
            {' '}<br/><small className="note">{x.plan.cells ? `по плану цеха ${dmy(x.plan.first_day)}–${dmy(x.plan.last_day)}` : 'изделие не поставлено в план цеха'}</small>
            {!!x.plan.shortfall && <>{' '}<br/><small className="bad">к концу плана ≈ {nf(x.plan.expected)}, не хватит {nf(x.plan.shortfall)}</small></>}
          </td> : <td>
            {x.looms.length ? x.looms.map((l, i) => <span key={l.loom} className={l.matched ? '' : 'note'}>
              {i > 0 ? ', ' : ''}{l.loom} <small>{nf(l.done)}</small></span>) : '—'}
            {!!x.looms.length && !x.matched && <>{' '}<br/><small className="bad">код ткани на станке не совпал с изделием</small></>}
            {' '}<br/><input size={5} placeholder="станок" style={{fontSize: 12}} disabled={!canPlan} ref={el => {assignInputs.current[x.id] = el;}}/>
            {' '}<button className="act" style={{padding: '2px 6px'}} disabled={!canPlan} onClick={() => assign(x.id, assignInputs.current[x.id]?.value || '')}>+</button>
          </td>}
          <td><button className="act" disabled={!canPlan} onClick={() => toggleClose(x.id, x.closed)}>{x.closed ? 'Вернуть' : 'Закрыть'}</button></td>
        </tr>;
      })}
      {state.orders.length > shown.length && <tr><td colSpan={11}>
        <button className="act" onClick={showAllOrders}>Показать все заказы ({state.orders.length})</button>
        {' '}<span className="note">сейчас — {shown.length} ближайших по сроку</span>
      </td></tr>}
    </>;

  return <>
    {createPortal(<>
      <div className="f"><label htmlFor="pl-order">Заказ</label><input id="pl-order" size={10} autoComplete="off" ref={orderRef}/></div>
      <div className="f"><label htmlFor="pl-product">Изделие</label><input id="pl-product" size={20} list="pl-products" autoComplete="off" ref={productRef}/></div>
      <div className="f"><label htmlFor="pl-qty">Полотенец</label><input id="pl-qty" size={8} autoComplete="off" ref={qtyRef}/></div>
      <div className="f"><label htmlFor="pl-due">Срок</label><input id="pl-due" size={10} placeholder="2026.10.01" autoComplete="off" ref={dueRef}/></div>
      <div className="f"><label>{' '}</label><button className="act primary" id="pl-add" disabled={!canPlan} onClick={() => {void onAdd();}}>Поставить в план</button></div>
      <div className="f"><label>{' '}</label><button className="act" id="pl-1c" disabled={!canPlan} onClick={importFrom1c}>Взять заказы из 1С</button></div>
      <div className="f"><label>{' '}</label><button className="act" id="pl-closed" onClick={toggleClosed}>{state.closed ? 'Только открытые' : 'Показать закрытые'}</button></div>
    </>, formBar)}
    {createPortal((state.products || []).map(p => <option key={p} value={p}/>), productsList)}
    {createPortal(tiles(state.orders, nf).map(t => <div className="tile" key={t.label}>
      <div className="l">{t.label}</div><div className="v">{t.bad !== undefined ? <span className={t.bad ? 'bad' : ''}>{t.value}</span> : t.value}</div>
    </div>), tilesEl)}
    {createPortal(rows, tableBody)}
    {createPortal(state.loaded ? pptSourcesNote(state.orders) + planOnlyNote(state.planOnly) : '', pptNote)}
    {createPortal(<>
      <div className="f"><label htmlFor="ppt-key">Артикул 1С или код ткани</label><input id="ppt-key" size={24} list="pl-products" autoComplete="off" ref={pptKeyRef}/></div>
      <div className="f"><label htmlFor="ppt-val">Пиков на изделие</label><input id="ppt-val" size={7} inputMode="numeric" ref={pptValRef}/></div>
      <div className="f"><label htmlFor="ppt-panels">Панелей</label><input id="ppt-panels" size={4} inputMode="numeric" ref={pptPanelsRef}/></div>
      <div className="f"><label>{' '}</label><button className="act primary" id="ppt-save" disabled={!canSetup} onClick={() => {void onSavePpt();}}>Сохранить</button></div>
    </>, pptBar)}
  </>;
}
