import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import type { Snapshot } from '../features/report/model';

// Independent oracle: execute the original renderer, not a second copy of React logic.
export const source = readFileSync('../_app/ui.html', 'utf8');
const between = (start: string, end: string) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
export const reportMarkup = between('<section id="tab-report">', '    <p class="note" style="margin-top:6px">');
export function legacyReport(state: Snapshot, lang = 'ru') {
  const doc = document.implementation.createHTMLDocument();
  doc.documentElement.lang = lang;
  doc.body.innerHTML = reportMarkup;
  const script = [
    source.match(/^const nf = .*$/m)![0], source.match(/^const esc = .*$/m)![0],
    between('const paint = ', '/* --- отчёт --- */'),
    between('const grp4 = ', '// Шапка из трёх строк закреплена'),
    'REP_ROWS = state.rows; REP_F = state.filters; REP_SORT = state.sort; REP_HIDE = new Set(state.hidden);',
    '$("#rep-flag").value = state.flag; renderReport();',
  ].join('\n');
  runInNewContext(script, { document: doc, window: {}, state, can: () => state.setupEdit,
    $: (s: string) => doc.querySelector(s), repStick: () => {},
    localStorage: { getItem: () => null, setItem: () => {} } }, { timeout: 2000 });
  return doc;
}
export function reportOutput(doc: Document) {
  const text = (s: string) => doc.querySelector(s)?.textContent;
  return {
    cells: Array.from(doc.querySelectorAll('#rep-table th,#rep-table td')).map(e => ({
      text: e.textContent, classes: [...e.classList].sort(), title: e.getAttribute('title'),
      span: e.getAttribute('colspan'), sort: e.getAttribute('aria-sort'),
    })),
    filters: Array.from(doc.querySelectorAll<HTMLInputElement>('#rep-table input')).map(e => ({
      value: e.value, classes: [...e.classList].sort(), label: e.getAttribute('aria-label'), title: e.title,
    })),
    tiles: text('#rep-tiles'), count: text('#rep-count'),
  };
}
