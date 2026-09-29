import { Fragment, useEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import type { PlanBridge } from '../bridge';
import type { LoomController, LoomState } from './controller';
import type { CatalogOrder, OrderFilter } from './model';
import { cellView, dialogInitial, filterOrders, hueOf, key, orderByNo, orderProgress, productOptions, SLOT_RU, split, weekday } from './model';

const WEEKDAYS = 'вс пн вт ср чт пт сб'.split(' ');
const FILTERS: [OrderFilter, string][] = [['all', 'Все'], ['1c', 'Из 1С'], ['no1c', 'Нет в 1С'], ['short', 'Не хватает'], ['free', 'Не в плане']];

type Props = {
  periodBar: HTMLElement; editBar: HTMLElement; noteEl: HTMLElement; contextEl: HTMLElement; table: HTMLElement;
  palette: HTMLElement; orderList: HTMLElement; dialog: HTMLDialogElement; wrapEl: HTMLElement; scrollEl: HTMLElement;
  state: LoomState; bridge: PlanBridge; controller: LoomController;
};

export function Loom({periodBar, editBar, noteEl, contextEl, table, palette, orderList, dialog, wrapEl, scrollEl, state, bridge, controller}: Props) {
  const {nf, dmy, ftime} = bridge;
  const canEdit = bridge.can('plan_edit');
  const fromRef = useRef<HTMLInputElement>(null), toRef = useRef<HTMLInputElement>(null), fileRef = useRef<HTMLInputElement>(null);
  const [panMode, setPanMode] = useState(false);
  const [ordersHidden, setOrdersHidden] = useState(false);
  const panState = useRef<{x: number; y: number; left: number; top: number} | null>(null);

  useEffect(() => { if (fromRef.current) fromRef.current.value = state.from; }, [state.from]);
  useEffect(() => { if (toRef.current) toRef.current.value = state.to; }, [state.to]);
  useEffect(() => { wrapEl.classList.toggle('orders-hidden', ordersHidden); }, [wrapEl, ordersHidden]);
  useEffect(() => {
    if (state.selection.size !== 1) return;
    const k = [...state.selection][0];
    for (const el of table.querySelectorAll<HTMLElement>('td.d')) if (el.dataset.k === k) { el.scrollIntoView({block: 'nearest', inline: 'nearest'}); break; }
  }, [state.selection, table]);

  useEffect(() => {
    const el = scrollEl;
    const onDown = (e: PointerEvent) => {
      if (!panMode || e.button !== 0) return;
      e.preventDefault(); e.stopPropagation();
      panState.current = {x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop};
      el.setPointerCapture(e.pointerId); el.classList.add('panning');
    };
    const onMove = (e: PointerEvent) => {
      if (!panState.current) return;
      el.scrollLeft = panState.current.left + panState.current.x - e.clientX;
      el.scrollTop = panState.current.top + panState.current.y - e.clientY;
    };
    const onUp = () => { panState.current = null; el.classList.remove('panning'); };
    const onBlock = (e: Event) => { if (panMode) { e.preventDefault(); e.stopImmediatePropagation(); } };
    el.addEventListener('pointerdown', onDown, true);
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onUp);
    el.addEventListener('click', onBlock, true);
    el.addEventListener('dblclick', onBlock, true);
    el.addEventListener('dragstart', onBlock, true);
    return () => {
      el.removeEventListener('pointerdown', onDown, true);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
      el.removeEventListener('click', onBlock, true);
      el.removeEventListener('dblclick', onBlock, true);
      el.removeEventListener('dragstart', onBlock, true);
    };
  }, [scrollEl, panMode]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (document.getElementById('tab-plan')?.classList.contains('hidden') || !state.grid) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest?.('input, textarea, select, dialog, button, a, [contenteditable]')) return;
      if (e.key === 'Escape') { controller.clearSelection(); return; }
      if (!canEdit) return;
      const ctrl = e.ctrlKey || e.metaKey, keys = [...state.selection];
      if (ctrl && e.key.toLowerCase() === 'z') { e.preventDefault(); controller.undo(); return; }
      if (!keys.length) return;
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); controller.deleteSelection(); }
      else if (ctrl && e.key.toLowerCase() === 'c') { controller.copySelection(); }
      else if (ctrl && e.key.toLowerCase() === 'v' && state.clipboard) { e.preventDefault(); controller.paste(); }
      else if (e.key === 'Enter') { e.preventDefault(); controller.openDialog(state.anchor || keys[0]); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [state.grid, state.selection, state.clipboard, state.anchor, canEdit, controller]);

  const onShow = () => {
    controller.setRange(fromRef.current?.value.trim() || '', toRef.current?.value.trim() || '');
    void controller.load();
  };
  const onFileChange = () => {
    const f = fileRef.current?.files?.[0]; if (!f) return;
    void controller.uploadExcel(f);
    if (fileRef.current) fileRef.current.value = '';
  };

  const g = state.grid;
  const noteText = !g ? '' : g.plan_from
    ? `В плане дни ${dmy(g.plan_from)}–${dmy(g.plan_to || '')}.${(g.plan_to || '').slice(0, 4)}, последняя правка ${ftime(g.plan_loaded_at || '')}. Факт — по ${dmy(g.last_fact_day || '')}.`
    : 'План пуст: перетащите заказы на станки или загрузите Excel TOYOTA - LOOM PLAN.';

  const selectionText = state.selection.size === 1 ? (() => {
    const [l, d] = split([...state.selection][0]);
    return `${l} · ${dmy(d)}.${d.slice(0, 4)}${canEdit ? ' — можно редактировать' : ' — просмотр'}`;
  })() : state.selection.size ? `Выбрано ячеек: ${state.selection.size}` : 'Выберите ячейку станка для редактирования.';

  const filtered = filterOrders(state.catalog, state.query, state.filter);
  const cardOrder = state.focus ? orderByNo(state.catalog, state.focus) : undefined;

  return <>
    {createPortal(<>
      <div className="f"><label htmlFor="lp-from">Период с</label><input id="lp-from" size={10} autoComplete="off" ref={fromRef} defaultValue={state.from}/></div>
      <div className="f"><label htmlFor="lp-to">По</label><input id="lp-to" size={10} autoComplete="off" ref={toRef} defaultValue={state.to}/></div>
      <div className="f"><label>{' '}</label><button className="act" onClick={onShow}>Показать</button></div>
      <div className="lp-actions" aria-label="Навигация по датам">
        <button className="act" title="Сдвинуть показанный период на неделю назад" onClick={() => controller.movePeriod(-7)}>← 7 дней</button>
        <button className="act" onClick={() => controller.movePeriod(null)}>Сегодня</button>
        <button className="act" title="Сдвинуть показанный период на неделю вперёд" onClick={() => controller.movePeriod(7)}>7 дней →</button>
        <button className="act" aria-expanded={!ordersHidden} onClick={() => setOrdersHidden(v => !v)}>{ordersHidden ? 'Показать заказы' : 'Скрыть заказы'}</button>
        <button className="act" aria-pressed={panMode} onClick={() => setPanMode(v => !v)}>Перемещать таблицу</button>
      </div>
    </>, periodBar)}

    {createPortal(<>
      <div className="f"><label htmlFor="lp-span">Назначить на дней</label>
        <input id="lp-span" size={3} defaultValue="1" inputMode="numeric" autoComplete="off" onChange={e => controller.setSpan(parseInt(e.target.value, 10) || 1)}/></div>
      <div className="f"><label>{' '}</label><label className="checks" style={{paddingTop: 0}}>
        <input type="checkbox" checked={state.skipSundays} onChange={e => controller.setSkipSundays(e.target.checked)}/> без воскресений</label></div>
      <div className="f"><label>{' '}</label><button className="act" id="lp-edit" disabled={!state.selection.size || !canEdit}
        onClick={() => { const k = [...state.selection][0]; if (k) controller.openDialog(k); }}>Редактировать</button></div>
      <div className="f"><label>{' '}</label><button className="act" id="lp-undo" disabled={!state.undoStack.length} onClick={() => controller.undo()}>Отменить правку</button></div>
      <div className="f"><label>{' '}</label><button className="act" onClick={() => fileRef.current?.click()}>Загрузить план из Excel</button>
        <input type="file" accept=".xlsx" className="hidden" ref={fileRef} onChange={onFileChange}/></div>
    </>, editBar)}

    {createPortal(noteText, noteEl)}

    {createPortal(<>
      <span id="lp-focus" className={'lp-focus' + (state.focus ? '' : ' hidden')}><span>Выбран заказ:</span> <b>{state.focus || ''}</b></span>
      <span id="lp-selection" role="status">{selectionText}</span>
    </>, contextEl)}

    {g && createPortal(<>
      <thead><tr><th>Станок</th>
        {g.days.map(d => {
          const wd = weekday(d);
          const selectedDay = [...state.selection].some(k => split(k)[1] === d);
          return <th key={d} className={'d' + (d === state.today ? ' today' : '') + (wd === 0 ? ' wk' : '') + (selectedDay ? ' axis-selected' : '')}>
            {dmy(d)}<small>{WEEKDAYS[wd]}{d === state.today ? ' · сегодня' : wd === 0 ? ' · выходной' : ''}</small>
          </th>;
        })}
      </tr></thead>
      <tbody>
        {g.looms.length ? g.looms.map(l => {
          const selectedLoom = [...state.selection].some(k => split(k)[0] === l.loom);
          return <tr key={l.loom}>
            <td className={'lm' + (selectedLoom ? ' axis-selected' : '')}>{l.loom}</td>
            {g.days.map(d => {
              const view = cellView(l.loom, d, g, state.catalog, state.today, state.selection.has(key(l.loom, d)), state.focus, nf);
              const style: CSSProperties & Record<string, string> = {};
              if (view.hue != null) style['--h'] = String(view.hue);
              return <td key={d} data-k={view.key} draggable={view.draggable || undefined} className={view.classes.join(' ')} style={style} title={view.title || undefined}
                onClick={e => controller.click(view.key, {shift: e.shiftKey, ctrl: e.ctrlKey || e.metaKey})}
                onDoubleClick={() => controller.openDialog(view.key)}
                onDragStart={e => {
                  if (!canEdit) { e.preventDefault(); return; }
                  e.dataTransfer.setData('text/plain', JSON.stringify({t: 'cell', k: view.key}));
                  e.dataTransfer.effectAllowed = 'copyMove';
                }}
                onDragOver={e => { e.preventDefault(); (e.currentTarget as HTMLElement).classList.add('over'); }}
                onDragLeave={e => (e.currentTarget as HTMLElement).classList.remove('over')}
                onDrop={e => {
                  if (!canEdit) { e.preventDefault(); return; }
                  e.preventDefault(); (e.currentTarget as HTMLElement).classList.remove('over');
                  let p: {t: string; k?: string; o?: string; p?: string};
                  try { p = JSON.parse(e.dataTransfer.getData('text/plain')); } catch { return; }
                  if (p.t === 'order' && p.o) controller.place(p.o, view.key);
                  else if (p.t === 'prod' && p.o) controller.place(p.o, view.key, p.p);
                  else if (p.t === 'cell' && p.k) controller.dropCellOnCell(p.k, view.key, !(e.ctrlKey || e.altKey));
                }}>
                {view.headOrder && <span className="lp-order">Заказ <b>{view.headOrder.order_no}</b>
                  {view.headOrder.ambiguous && <span className="lp-amb" title="Уточните изделие" aria-label="Уточните изделие">!</span>}</span>}
                <span className="lp-product">{view.body}</span>
                {view.yarn && <span className="lp-yarn"><span>Ворс:</span> <span>{view.yarn}</span></span>}
                {view.note && <> <span className="nt">{view.note}</span></>}
                {' '}{view.fact && <span className={'fx' + (view.fact.low ? ' lo' : '')} title={view.fact.title}>{view.fact.text}</span>}
              </td>;
            })}
          </tr>;
        }) : <tr><td className="note" colSpan={g.days.length + 1}>Станков нет.</td></tr>}
      </tbody>
    </>, table)}

    {createPortal(<>
      <div className="lp-heading"><h3>Заказы</h3><span className="note" id="lp-order-count">Найдено: {filtered.length}</span></div>
      <input id="lp-q" placeholder="Поиск: заказ, дизайн, клиент" autoComplete="off" aria-label="Поиск заказа"
        defaultValue={state.query} onChange={e => controller.setQuery(e.target.value)}/>
      <div className="lp-flt" id="lp-flt">
        {FILTERS.map(([f, label]) => <button key={f} aria-pressed={state.filter === f} onClick={() => controller.setFilter(f)}>{label}</button>)}
      </div>
      <div id="lp-orders" className="lp-orders">
        {filtered.length ? filtered.map(o => <OrderCard key={o.order_no} o={o} state={state} bridge={bridge} controller={controller}/>)
          : <p className="note">Заказов не найдено.</p>}
      </div>
      <div id="lp-card" className={'lp-card' + (cardOrder ? '' : ' hidden')}>
        {cardOrder && <OrderCardDetail o={cardOrder} bridge={bridge}/>}
      </div>
    </>, palette)}

    {createPortal(state.catalog.map(o => <option key={o.order_no} value={o.order_no}>{o.product || ''}</option>), orderList)}

    {state.dialog && g && <LoomDialog dialog={dialog} initial={dialogInitial(state.dialog.keys, state.dialog.forcedOrder, g, state.catalog, dmy)}
      catalog={state.catalog} bridge={bridge}
      onClose={(how, order, note, product) => {
        if (!how || how === 'cancel') controller.closeDialog();
        else controller.submitDialog(how as 'save' | 'clear', order, note, product);
      }}/>}
  </>;
}

function OrderCard({o, state, bridge, controller}: {o: CatalogOrder; state: LoomState; bridge: PlanBridge; controller: LoomController}) {
  const {nf, dmy} = bridge;
  const {done, expected} = orderProgress(o);
  const multi = o.products.length > 1, open = multi && state.open.has(o.order_no);
  const style: CSSProperties & Record<string, string> = {'--h': String(hueOf(o.order_no))};
  return <div className={'oc' + (o.order_no === state.focus ? ' on' : '')} draggable data-o={o.order_no} style={style}
    onDragStart={e => { e.dataTransfer.setData('text/plain', JSON.stringify({t: 'order', o: o.order_no})); e.dataTransfer.effectAllowed = 'copy'; }}
    onClick={() => controller.clickOrderCard(o.order_no, false)}>
    <div className="t"><span><b>{o.order_no}</b> {multi ? <span className="m">изделий: {o.products.length}</span> : <>{o.size || ''} {o.design || ''}</>}
      {o.client ? ' /' + o.client : ''}</span>
      {' '}<span>{multi ? <button className="tg" aria-expanded={open} title={(open ? 'Свернуть' : 'Показать') + ' изделия'}
        onClick={e => { e.stopPropagation(); controller.toggleOrderOpen(o.order_no); }}>{open ? '▾' : '▸'}</button> : (o.gsm || '')}</span>
    </div>
    {' '}<div className="m">{o.in_1c ? '1С' : 'нет в 1С'}{o.qty ? ' · ' + nf(o.qty) + ' шт' : ''}{o.due_day ? ' · срок ' + dmy(o.due_day) : ''} · {o.cells ? o.cells + ' ст.-дн.' : 'не в плане'}
      {!!o.unpicked && <> · <span className="bad">без изделия: {o.unpicked}</span></>}</div>
    {!!o.qty && <div className="b2" title={`сделано ${nf(o.done)}, к концу плана ≈${nf(o.expected)} из ${nf(o.qty)}`}>
      <i className="p" style={{width: expected + '%'}}/><i style={{width: done + '%'}}/></div>}
    {o.order_no === state.focus && <span className="oc-selected">✓ <span>Выбран</span></span>}
    {open && <div className="pls">{o.products.map(p => <div key={p.product_code} className="pl" draggable data-o={o.order_no} data-p={p.product_code}
      title={`${p.product_code} — перетащите на станок`}
      onDragStart={e => { e.stopPropagation(); e.dataTransfer.setData('text/plain', JSON.stringify({t: 'prod', o: o.order_no, p: p.product_code})); e.dataTransfer.effectAllowed = 'copy'; }}
      onClick={e => { e.stopPropagation(); controller.clickOrderCard(o.order_no, true); }}>
      <span>{p.size || ''} <b>{p.design || ''}</b>{p.gsm ? ' · ' + p.gsm : ''}</span>
      <span className="m">{nf(p.qty)} шт{p.cells ? ' · ' + p.cells + ' ст.-дн.' : ''}</span>
    </div>)}</div>}
  </div>;
}

function OrderCardDetail({o, bridge}: {o: CatalogOrder; bridge: PlanBridge}) {
  const {nf, dmy, ftime} = bridge;
  const short = o.qty ? o.qty - o.expected : 0;
  return <>
    <b>{o.order_no}</b>{o.client ? ' · клиент ' + o.client : ''}
    {' '}<dl>
      {!!o.qty && <><dt>Заказ</dt><dd>{nf(o.qty)} шт{o.products.length > 1 ? ', изделий ' + o.products.length : ''}</dd></>}
      {' '}{o.due_day && <><dt>Срок</dt><dd>{dmy(o.due_day)}</dd></>}
      {' '}<dt>Сделано</dt><dd>{nf(o.done)} шт</dd>
      {' '}{!!o.qty && <><dt>К концу плана</dt><dd>≈{nf(o.expected)}{short > 0 ? <> <span className="bad">не хватит {nf(short)}</span></> : <> <span className="ok">хватает</span></>}</dd></>}
      {' '}{!!o.cells && <><dt>В плане</dt><dd>{dmy(o.first_day || '')}–{dmy(o.last_day || '')}, {o.cells} ст.-дн.: {o.looms.join(', ')}</dd></>}
      {' '}{!!o.unpicked && <><dt>Без изделия</dt><dd className="bad">{o.unpicked} клеток — выберите изделие двойным щелчком по клетке</dd></>}
      {' '}{o.loaded_at && <><dt>Из 1С</dt><dd>{ftime(o.loaded_at)}</dd></>}
    </dl>
    {' '}{o.products.length ? <div className="tbl-wrap" style={{maxHeight: '42vh', marginTop: 6}}>
      <table className="lp-prods"><thead><tr><th>Изделие</th><th className="n">GSM</th><th className="n">Шт</th><th className="n">PPT</th><th className="n">Вес</th><th className="n">{'Пан. '}</th>
        <th className="n">Сделано / к концу</th></tr></thead>
      <tbody>{o.products.map(p => {
        const ys = Object.entries(p.yarns || {}).map(([s, y]) => `${SLOT_RU[s] || s} ${y.yarn || ''}${y.lot ? ' лот ' + y.lot : ''}`).join(', ');
        return <Fragment key={p.product_code}>
          <tr><td>{p.size || ''} <b>{p.design || ''}</b></td><td className="n">{(p.gsm || '') + ' '}</td>
            <td className="n">{nf(p.qty)}</td><td className="n">{nf(p.ppt)}</td><td className="n">{(p.weight_kg ? nf(p.weight_kg, 3) : '') + ' '}</td>
            <td className="n">{p.panels || ''}</td><td className="n">{p.cells ? nf(p.done) + ' / ≈' + nf(p.expected) : 'не в плане'}</td></tr>
          {ys && <tr className="ys"><td colSpan={7}>{ys}</td></tr>}
        </Fragment>;
      })}</tbody>
      </table>
    </div> : <p className="bad" style={{margin: '6px 0 0'}}>Заказа нет в 1С — PPT, вес и пряжу отчёт возьмёт из справочника.</p>}
  </>;
}

function LoomDialog({dialog, initial, catalog, bridge, onClose}: {
  dialog: HTMLDialogElement; initial: ReturnType<typeof dialogInitial>; catalog: CatalogOrder[]; bridge: PlanBridge;
  onClose: (how: string, order: string, note: string, product: string) => void;
}) {
  const {nf} = bridge;
  const [order, setOrder] = useState(initial.order);
  const [note, setNote] = useState(initial.note);
  const [product, setProduct] = useState(initial.selectedProduct || '');
  const latest = useRef({order, note, product});
  latest.current = {order, note, product};
  useEffect(() => {
    const handler = () => onClose(dialog.returnValue, latest.current.order, latest.current.note, latest.current.product);
    dialog.addEventListener('close', handler);
    return () => dialog.removeEventListener('close', handler);
  }, [dialog, onClose]);
  useEffect(() => { if (!dialog.open) dialog.showModal(); }, [dialog]);

  const products = productOptions(order, catalog);
  return createPortal(<form method="dialog">
    <h3 id="lp-dlg-t" style={{margin: '0 0 12px', fontSize: 15}}>{initial.heading}</h3>
    <div className="bar" style={{padding: 0, border: 0, background: 'none'}}>
      <div className="f"><label htmlFor="lp-d-order">Заказ</label>
        <input id="lp-d-order" list="lp-order-list" size={10} autoComplete="off" value={order}
          onChange={e => { setOrder(e.target.value); setProduct(''); }}/></div>
      <div className="f"><label htmlFor="lp-d-prod">Изделие заказа</label>
        <select id="lp-d-prod" value={product} disabled={products.length < 2} onChange={e => setProduct(e.target.value)}>
          <option value="">{products.length > 1 ? 'подобрать по размеру и GSM' : '—'}</option>
          {products.map(p => <option key={p.product_code} value={p.product_code}>
            {[p.size, p.design, p.gsm && p.gsm + ' GSM'].filter(Boolean).join(' · ')} — {nf(p.qty)} шт</option>)}
        </select></div>
      <div className="f"><label htmlFor="lp-d-note">Пометка</label>
        <input id="lp-d-note" size={28} placeholder="Praborka 35 sm, рулон…" autoComplete="off" value={note} onChange={e => setNote(e.target.value)}/></div>
    </div>
    <p className="note" id="lp-d-hint">{initial.hint}</p>
    <div style={{display: 'flex', gap: 6, marginTop: 10}}>
      <button className="act primary" value="save">Сохранить</button>
      <button className="act" value="clear">Очистить клетку</button>
      <button className="act" value="cancel">Отмена</button>
    </div>
  </form>, dialog);
}
