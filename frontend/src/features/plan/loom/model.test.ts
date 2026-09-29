import { describe, expect, it } from 'vitest';
import {
  cellSnapshot, cellView, dash2dot, daysFrom, dialogInitial, filterOrders, idxOf, isFilled, key,
  orderByNo, orderProgress, productOptions, split, topLeft,
} from './model';
import type { CatalogOrder, LoomGrid } from './model';

const nf = (x: unknown, d = 0) => x == null || x === '' ? '' : Number(x).toLocaleString('ru-RU', {minimumFractionDigits: d, maximumFractionDigits: d});
const dmy = (d: string) => d ? d.slice(8, 10) + '.' + d.slice(5, 7) : '';

const grid = (): LoomGrid => ({
  days: ['2026.09.21', '2026.09.22', '2026.09.23'], last_fact_day: '2026.09.22', plan_from: '2026.09.21',
  plan_to: '2026.09.27', plan_loaded_at: '2026-09-20T10:00:00',
  looms: [
    {loom: 'D1', cells: {
      '2026.09.21': {order_no: '1557', product: 'P1', size: '150', design: 'D144', gsm: 420, product_code: 'P1',
        fact: {towels: 300, eff: 88, norm: 95}},
      '2026.09.22': {order_no: '1557', product: 'P1', note: 'ручной', product_code: null, pick: 'ambiguous'},
    }},
    {loom: 'D2', cells: {}},
  ],
});
const catalog = (): CatalogOrder[] => [
  {order_no: '1557', in_1c: true, in_plan: true, qty: 5000, products: [
    {product_code: 'P1', size: '150', design: 'D144', gsm: 420, qty: 5000, done: 300, expected: 400},
    {product_code: 'P2', size: '150', design: 'D144', gsm: 400, qty: 1000, done: 0, expected: 0},
  ], cells: 2, done: 300, expected: 400, looms: ['D1']},
];

describe('key/split/idxOf/topLeft', () => {
  it('round-trips loom and day through a key', () => { expect(split(key('D1', '2026.09.21'))).toEqual(['D1', '2026.09.21']); });
  it('finds grid indices for a key', () => { expect(idxOf(key('D2', '2026.09.22'), ['D1', 'D2'], grid().days)).toEqual([1, 1]); });
  it('picks the top-left-most key of a selection', () => {
    const keys = [key('D2', '2026.09.22'), key('D1', '2026.09.23'), key('D1', '2026.09.21')];
    expect(topLeft(keys, ['D1', 'D2'], grid().days)).toBe(key('D1', '2026.09.21'));
  });
});

describe('cellSnapshot / isFilled', () => {
  it('captures the fields that round-trip through the API', () => {
    expect(cellSnapshot(grid().looms[0].cells['2026.09.21'])).toEqual(
      {order_no: '1557', note: null, product: 'P1', pile_yarn: null, product_code: 'P1', pick: null});
  });
  it('treats an empty object as not filled and an order/product/note as filled', () => {
    expect(isFilled(undefined)).toBe(false);
    expect(isFilled({})).toBe(false);
    expect(isFilled({order_no: '1557'})).toBe(true);
    expect(isFilled({note: 'x'})).toBe(true);
  });
});

describe('cellView', () => {
  it('renders an assigned, matched cell with its fact line', () => {
    const v = cellView('D1', '2026.09.21', grid(), catalog(), '2026.09.22', false, null, nf);
    expect(v.headOrder).toEqual({order_no: '1557', ambiguous: false});
    expect(v.body).toBe('150 D144 · 420 GSM');
    expect(v.fact?.text).toBe(`${nf(300)} шт · норма ${nf(95)}%`);
    expect(v.draggable).toBe(true);
  });
  it('flags an ambiguous cell needing product disambiguation', () => {
    const v = cellView('D1', '2026.09.22', grid(), catalog(), '2026.09.22', false, null, nf);
    expect(v.classes).toContain('amb');
    expect(v.title).toContain('подходят несколько изделий');
  });
  it('hides the fact line for days after the last fact day', () => {
    const v = cellView('D1', '2026.09.21', {...grid(), last_fact_day: '2026.09.20'}, catalog(), '2026.09.22', false, null, nf);
    expect(v.fact).toBeNull();
  });
  it('marks the current day and reflects selection', () => {
    const v = cellView('D2', '2026.09.21', grid(), catalog(), '2026.09.21', true, '1557', nf);
    expect(v.classes).toEqual(expect.arrayContaining(['today', 'sel']));
    expect(v.draggable).toBe(false);
  });
  it('marks a day before today as past', () => {
    const v = cellView('D2', '2026.09.21', grid(), catalog(), '2026.09.25', false, null, nf);
    expect(v.classes).toContain('past');
  });
  it('renders an empty cell with no data-bearing fields', () => {
    const v = cellView('D2', '2026.09.22', grid(), catalog(), '2026.09.22', false, null, nf);
    expect(v.headOrder).toBeNull(); expect(v.body).toBe(''); expect(v.draggable).toBe(false);
  });
});

describe('daysFrom / dash2dot', () => {
  it('lists consecutive days, skipping Sundays when asked', () => {
    expect(daysFrom('2026.09.24', 3, false)).toEqual(['2026.09.24', '2026.09.25', '2026.09.26']);
    // 2026.09.27 is a Sunday.
    expect(daysFrom('2026.09.26', 3, true)).toEqual(['2026.09.26', '2026.09.28', '2026.09.29']);
  });
  it('normalises dashes to dots for the date-range query', () => { expect(dash2dot('2026-09-24')).toBe('2026.09.24'); });
});

describe('filterOrders / orderProgress', () => {
  it('excludes a closed order that is no longer in the plan', () => {
    const orders = catalog().map(o => ({...o, closed: true, in_plan: false}));
    expect(filterOrders(orders, '', 'all')).toHaveLength(0);
  });
  it('filters by 1C presence, shortfall and free-of-plan', () => {
    const orders = catalog();
    expect(filterOrders(orders, '', '1c')).toHaveLength(1);
    expect(filterOrders(orders, '', 'no1c')).toHaveLength(0);
    expect(filterOrders(orders, '', 'short')).toHaveLength(1);
    expect(filterOrders(orders, '', 'free')).toHaveLength(0);
  });
  it('searches the order number and each product code, but not a nested product design', () => {
    expect(filterOrders(catalog(), '1557', 'all')).toHaveLength(1);
    expect(filterOrders(catalog(), 'P2', 'all')).toHaveLength(1);
    expect(filterOrders(catalog(), 'D144', 'all')).toHaveLength(0);
    expect(filterOrders(catalog(), 'nope', 'all')).toHaveLength(0);
  });
  it('computes done/expected percentages capped at 100', () => {
    expect(orderProgress(catalog()[0])).toEqual({done: 6, expected: 8});
    expect(orderProgress({...catalog()[0], qty: 0})).toEqual({done: 0, expected: 0});
  });
});

describe('dialogInitial / productOptions', () => {
  it('seeds a single-cell dialog from the existing cell', () => {
    const d = dialogInitial([key('D1', '2026.09.21')], undefined, grid(), catalog(), dmy);
    expect(d.order).toBe('1557'); expect(d.selectedProduct).toBe('P1');
    expect(d.heading).toBe('D1 · 21.09.2026');
  });
  it('leaves fields blank for a multi-cell selection unless an order is forced', () => {
    const d = dialogInitial([key('D1', '2026.09.21'), key('D1', '2026.09.22')], undefined, grid(), catalog(), dmy);
    expect(d.order).toBe(''); expect(d.heading).toBe('Клеток: 2');
  });
  it('forces the order and hints at product disambiguation when dropped from the palette', () => {
    const d = dialogInitial([key('D2', '2026.09.21')], '1557', grid(), catalog(), dmy);
    expect(d.order).toBe('1557');
    expect(d.hint).toContain('несколько изделий');
    expect(d.heading).toContain('заказ 1557');
  });
  it('lists an order\'s products, empty for an unknown order', () => {
    expect(productOptions('1557', catalog())).toHaveLength(2);
    expect(productOptions('nope', catalog())).toHaveLength(0);
  });
  it('finds an order by number, tolerating a numeric-looking string', () => {
    expect(orderByNo(catalog(), '1557')?.order_no).toBe('1557');
    expect(orderByNo(catalog(), 'missing')).toBeUndefined();
  });
});
