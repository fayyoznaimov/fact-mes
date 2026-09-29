import { runInNewContext } from 'node:vm';
import { source } from './legacy';

// Independent oracle for the Plan tab, same approach as legacy.ts: execute the
// original renderer, not a second copy of React logic.
const between = (start: string, end: string, from = 0) => {
  const at = source.indexOf(start, from);
  return source.slice(at, source.indexOf(end, at));
};

// Real formatter functions from the source, so component tests build their bridge
// mock from the actual legacy behaviour instead of a hand-copied re-implementation.
export function legacyFormatters() {
  const script = [
    source.match(/^const esc = .*$/m)![0],
    source.match(/^const nf = .*$/m)![0],
    source.match(/^const fday = .*$/m)![0],
    source.match(/^const ftime = .*$/m)![0],
    source.match(/^const dmy = .*$/m)![0],
    '({esc, nf, fday, ftime, dmy})',
  ].join('\n');
  return runInNewContext(script, {document: {documentElement: {lang: 'ru'}}}) as {
    esc: (s: unknown) => string; nf: (x: unknown, d?: number) => string;
    fday: (v: unknown) => string; ftime: (v: unknown) => string; dmy: (d: string) => string;
  };
}

// --- Обмен с 1С (onec) ---
export const onecMarkup = between(
  '<div class="pane hidden" data-pane="onec" role="tabpanel">',
  '<div class="pane hidden" data-pane="orders" role="tabpanel">',
);

export async function legacyOnec(messages: unknown[]) {
  const doc = document.implementation.createHTMLDocument();
  doc.body.innerHTML = onecMarkup;
  const script = [
    source.match(/^const esc = .*$/m)![0],
    source.match(/^const fday = .*$/m)![0],
    source.match(/^const ftime = .*$/m)![0],
    between('async function loadOneC() {', '\n$("#oc-msgs").addEventListener'),
    'loadOneC();',
  ].join('\n');
  const result = runInNewContext(script, {document: doc, window: {}, $: (s: string) => doc.querySelector(s),
    api: () => Promise.resolve({messages})}, {timeout: 2000});
  await result;
  return doc;
}

export function onecOutput(doc: Document) {
  return Array.from(doc.querySelectorAll('#oc-msgs tbody tr')).map(row => ({
    cells: Array.from(row.querySelectorAll('td')).map(td => ({
      text: td.textContent, classes: [...td.classList].sort(), colspan: td.getAttribute('colspan'),
    })),
  }));
}

export async function legacyOnecDetail(message: unknown) {
  const doc = document.implementation.createHTMLDocument();
  doc.body.innerHTML = onecMarkup;
  const dialog = doc.querySelector<HTMLDialogElement>('#oc-dlg')!;
  Object.defineProperties(dialog, {
    showModal: {configurable: true, value() { this.setAttribute('open', ''); }},
  });
  const script = [
    source.match(/^const ftime = .*$/m)![0],
    source.match(/^const fday = .*$/m)![0],
    'const say=(t,e)=>{globalThis.__say=[t,e];};',
    '(async e => {' + between('$("#oc-msgs").addEventListener("click", async e => {', '});\n$("#lp-show")')
      .slice('$("#oc-msgs").addEventListener("click", async e => {'.length)
      + '})({target:{closest:()=>({dataset:{m:"1"}})}});',
  ].join('\n');
  const result = runInNewContext(script, {document: doc, window: {}, $: (s: string) => doc.querySelector(s),
    api: () => Promise.resolve(message), globalThis}, {timeout: 2000});
  await result;
  return doc;
}

export function onecDetailOutput(doc: Document) {
  return {title: doc.querySelector('#oc-dlg-t')?.textContent, json: doc.querySelector('#oc-json')?.textContent};
}

// --- Коды ткани (codes) ---
export const codesMarkup = between(
  '<div class="pane hidden" data-pane="codes" role="tabpanel">',
  '<!-- ДОКУМЕНТЫ:',
);

// renderClothMap() is synchronous (no fetch): it only lays out the two tables and
// wires their buttons. api()/say()/loadPlan() calls made when a button is clicked are
// recorded for assertions instead of hitting the network.
export function legacyCodes(data: {unmapped?: unknown[]; cloth_map?: unknown[]}) {
  const doc = document.implementation.createHTMLDocument();
  doc.body.innerHTML = codesMarkup;
  const calls: {api: unknown[][]; say: unknown[][]; loadPlan: number} = {api: [], say: [], loadPlan: 0};
  const script = [
    source.match(/^const esc = .*$/m)![0],
    source.match(/^const nf = .*$/m)![0],
    source.match(/^const fday = .*$/m)![0],
    between('function renderClothMap(d) {', '\n$("#ppt-save").onclick'),
    'renderClothMap(data);',
  ].join('\n');
  runInNewContext(script, {
    document: doc, data, $: (s: string) => doc.querySelector(s),
    api: (...args: unknown[]) => {calls.api.push(args); return Promise.resolve({});},
    say: (...args: unknown[]) => {calls.say.push(args);},
    loadPlan: () => {calls.loadPlan++;},
  }, {timeout: 2000});
  return {doc, calls};
}

// --- Ганта (gantt) ---
export const ganttMarkup = between(
  '<div class="pane hidden" data-pane="gantt" role="tabpanel">',
  '<div class="pane hidden" data-pane="orders" role="tabpanel">',
);

export function legacyGantt(data: unknown, group = '') {
  const doc = document.implementation.createHTMLDocument();
  doc.body.innerHTML = ganttMarkup;
  (doc.querySelector('#gt-group') as HTMLSelectElement).value = group;
  const script = [
    source.match(/^const esc = .*$/m)![0],
    source.match(/^const nf = .*$/m)![0],
    source.match(/^const dmy = .*$/m)![0],
    source.match(/^const ymd = .*$/m)![0],
    source.match(/^const hueOf = .*$/m)![0],
    source.match(/^const gtAdd = .*$/m)![0],
    'const GT = {data};',
    between('function renderGantt() {', '\nfunction gtOpenFrom'),
    'renderGantt();',
  ].join('\n');
  runInNewContext(script, {document: doc, $: (s: string) => doc.querySelector(s), data}, {timeout: 2000});
  return doc;
}

// Compares parsed CSSOM values, not the raw attribute string: React and the legacy
// HTML string normalize property order, spacing and colour notation differently
// even when the rendered result (and this comparison) is identical.
const styleOf = (el: Element) => {
  const s = (el as HTMLElement).style;
  return {left: s.left, width: s.width, background: s.background};
};

export function ganttOutput(doc: Document) {
  const shallow = (sel: string) => Array.from(doc.querySelectorAll(sel)).map(el => ({
    tag: el.tagName, classes: [...el.classList].sort(), text: el.textContent,
  }));
  const bars = (sel: string) => Array.from(doc.querySelectorAll(sel)).map(b => ({
    text: b.textContent, classes: [...b.classList].sort(), title: b.getAttribute('title'), style: styleOf(b),
  }));
  return {
    names: shallow('.gt-names > *'),
    axisLabels: bars('.gt-ax > b'), shiftLabels: bars('.gt-ax > small'),
    background: bars('.gt-body > i.gt-s'), nowLine: bars('.gt-body > i.gt-now'),
    rowStructure: shallow('.gt-body > .gt-g, .gt-body > .gt-r'),
    planBars: bars('.gt-lane.p .gt-b'), factBars: bars('.gt-lane.f .gt-b'),
    range: doc.querySelector('#gt-range')?.textContent,
  };
}

export async function legacyTimeline(loom: string, a: string, b: string, data: unknown) {
  const doc = document.implementation.createHTMLDocument();
  doc.body.innerHTML = ganttMarkup;
  const dialog = doc.querySelector<HTMLDialogElement>('#gt-dlg')!;
  Object.defineProperties(dialog, {showModal: {configurable: true, value() { this.setAttribute('open', ''); }}});
  const script = [
    source.match(/^const esc = .*$/m)![0],
    source.match(/^const nf = .*$/m)![0],
    source.match(/^const dmy = .*$/m)![0],
    between('const CAUSE_COLOR = {', '\nconst ICONS'),
    'const TL_COL = CAUSE_COLOR; const GT = {tl: null}; const say = () => {};',
    between('async function openTimeline(loom, a, b) {', '\nconst gtStep'),
    `openTimeline(${JSON.stringify(loom)}, ${JSON.stringify(a)}, ${JSON.stringify(b)});`,
  ].join('\n');
  const result = runInNewContext(script, {document: doc, $: (s: string) => doc.querySelector(s),
    api: () => Promise.resolve(data)}, {timeout: 2000});
  await result;
  return doc;
}

export function timelineOutput(doc: Document) {
  const el = (sel: string) => doc.querySelector(sel);
  const bars = (sel: string) => Array.from(doc.querySelectorAll(sel)).map(b => ({
    style: styleOf(b), title: b.getAttribute('title'), text: b.textContent,
  }));
  return {
    title: el('#gt-dlg-t')?.textContent, summary: el('#gt-dlg-sum')?.textContent,
    tlClass: [...(el('#gt-tl')?.classList ?? [])].sort(), events: bars('#gt-tl i'),
    ticks: bars('#gt-tl-ax span'), legend: bars('#gt-tl-leg span'),
    rows: Array.from(doc.querySelectorAll('#gt-tl-list tbody tr')).map(row => ({
      cells: Array.from(row.querySelectorAll('td')).map(td => ({text: td.textContent, colspan: td.getAttribute('colspan')})),
    })),
  };
}

// --- Заказы и сроки (orders) ---
export const ordersMarkup = between(
  '<div class="pane hidden" data-pane="orders" role="tabpanel">',
  '<div class="pane hidden" data-pane="ppt" role="tabpanel">',
);

export async function legacyOrders(data: unknown, opts: {closed?: boolean; all?: boolean} = {}) {
  const doc = document.implementation.createHTMLDocument();
  doc.body.innerHTML = ordersMarkup;
  const script = [
    source.match(/^const esc = .*$/m)![0],
    source.match(/^const nf = .*$/m)![0],
    source.match(/^const fday = .*$/m)![0],
    source.match(/^const dmy = .*$/m)![0],
    `let PLAN_CLOSED=${opts.closed ? 'true' : 'false'}, PL_ALL=${opts.all ? 'true' : 'false'}, PL_LIMIT=60;`,
    between('async function loadPlan() {', '\n/* план цеха по станкам'),
    'loadPlan();',
  ].join('\n');
  const result = runInNewContext(script, {document: doc, window: {}, $: (s: string) => doc.querySelector(s),
    api: () => Promise.resolve(data), renderClothMap: () => {}, loadLoomPlan: () => {}, say: () => {}}, {timeout: 2000});
  await result;
  return doc;
}

export function ordersOutput(doc: Document) {
  const table = (sel: string) => Array.from(doc.querySelectorAll(sel)).map(row => ({
    cells: Array.from(row.querySelectorAll('td')).map(td => ({
      text: td.textContent?.replace(/\s+/g, ' ').trim(), classes: [...td.classList].sort(), colspan: td.getAttribute('colspan'),
    })),
  }));
  return {
    tiles: Array.from(doc.querySelectorAll('#pl-tiles .tile')).map(t => ({
      label: t.querySelector('.l')?.textContent, value: t.querySelector('.v')?.textContent,
      badClass: t.querySelector('.v span')?.className ?? null,
    })),
    rows: table('#pl-table tbody tr'),
    pptNote: doc.querySelector('#pl-ppt-note')?.textContent,
  };
}

// --- Сверка PPT (ppt) ---
export const pptMarkup = between(
  '<div class="pane hidden" data-pane="ppt" role="tabpanel">',
  '<div class="pane hidden" data-pane="onec" role="tabpanel">',
);

export async function legacyPpt(data: {products?: unknown[]; days?: unknown[]; threshold?: number}, opened = false) {
  const doc = document.implementation.createHTMLDocument();
  doc.body.innerHTML = pptMarkup;
  (doc.querySelector('#ppt-days-box') as HTMLDetailsElement).open = opened;
  const script = [
    source.match(/^const esc = .*$/m)![0],
    source.match(/^const nf = .*$/m)![0],
    source.match(/^const dmy = .*$/m)![0],
    between('async function loadPpt() {', '\n// Станко-дни'),
    between('let PPT_DAYS = null;', '\n$("#ppt-days-box").addEventListener'),
    'loadPpt();',
  ].join('\n');
  const result = runInNewContext(script, {document: doc, window: {}, $: (s: string) => doc.querySelector(s),
    api: () => Promise.resolve(data)}, {timeout: 2000});
  await result;
  return doc;
}

export function pptOutput(doc: Document) {
  const table = (sel: string) => Array.from(doc.querySelectorAll(sel)).map(row => ({
    cells: Array.from(row.querySelectorAll('td')).map(td => ({
      text: td.textContent?.replace(/\s+/g, ' ').trim(), classes: [...td.classList].sort(),
      title: td.getAttribute('title'), colspan: td.getAttribute('colspan'),
    })),
  }));
  return {
    products: table('#ppt-prod tbody tr'), days: table('#ppt-days tbody tr'),
    summary: doc.querySelector('#ppt-days-sum')?.textContent,
  };
}

export function codesOutput(doc: Document) {
  // Whitespace between inline elements is layout noise, not a design difference —
  // legacy builds rows from an indented template string, React from adjacent JSX.
  const table = (sel: string) => Array.from(doc.querySelectorAll(sel)).map(row => ({
    cells: Array.from(row.querySelectorAll('td')).map(td => ({
      text: td.textContent?.replace(/\s+/g, ' ').trim(), classes: [...td.classList].sort(), colspan: td.getAttribute('colspan'),
    })),
  }));
  return {unmapped: table('#cm-unmapped tbody tr'), map: table('#cm-map tbody tr')};
}
