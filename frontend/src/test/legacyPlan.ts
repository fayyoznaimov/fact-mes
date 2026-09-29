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
