import { describe, expect, it } from 'vitest';
import {
  buildPrintHtml, buildSummary, byOperator, dash2dot, editableOperators, foremenOptions, isLocked,
  mapLayout, mastersOptions, nextSuggestIndex, opLabel, ownMasterOf, searchOperators, selectedMasters,
  shiftNow, sortSuggestions, weekRange,
} from './model';
import type { AssignmentRow, Doc, Operator } from './model';

const ops: Operator[] = [
  {id: 1, code: 'O1', name: 'Иванова', role: 'operator', active: 1},
  {id: 2, code: 'O2', name: 'Сидорова', role: 'operator', active: 0},
  {id: 3, code: 'M1', name: 'Петрова', role: 'master', active: 1},
  {id: 4, code: 'F1', name: 'Кузнецов', role: 'foreman', active: 1},
];

describe('shiftNow', () => {
  it('picks shift A during the morning', () => {
    expect(shiftNow(new Date('2026-09-25T09:00:00'))).toEqual({day: '2026-09-25', shift: 'A'});
  });
  it('picks shift B in the afternoon', () => {
    expect(shiftNow(new Date('2026-09-25T16:00:00'))).toEqual({day: '2026-09-25', shift: 'B'});
  });
  it('picks shift C at night and keeps the day', () => {
    expect(shiftNow(new Date('2026-09-25T23:30:00'))).toEqual({day: '2026-09-25', shift: 'C'});
  });
  it('attributes the early night hours to the previous day (shift C)', () => {
    expect(shiftNow(new Date('2026-09-25T02:00:00'))).toEqual({day: '2026-09-24', shift: 'C'});
  });
});

describe('opLabel', () => {
  it('formats name and code', () => { expect(opLabel(ops[0])).toBe('Иванова (O1)'); });
});

describe('ownMasterOf', () => {
  it('returns the employee id for a master account', () => {
    expect(ownMasterOf({role: 'master', employee_id: 7})).toBe(7);
  });
  it('returns null for other roles', () => {
    expect(ownMasterOf({role: 'admin', employee_id: 7})).toBeNull();
    expect(ownMasterOf(null)).toBeNull();
  });
});

describe('isLocked', () => {
  it('is locked only when confirmed', () => {
    expect(isLocked({status: 'confirmed'} as Doc)).toBe(true);
    expect(isLocked({status: 'draft'} as Doc)).toBe(false);
    expect(isLocked(null)).toBe(false);
  });
});

describe('editableOperators', () => {
  it('includes active operators and inactive ones already assigned', () => {
    const assignments: AssignmentRow[] = [{loom: 'D1', operator_id: 2}];
    const result = editableOperators(ops, assignments);
    expect(result.map(o => o.code)).toEqual(['O1', 'O2']);
  });
});

describe('searchOperators / sortSuggestions', () => {
  it('filters active operators by code or name, case-insensitively', () => {
    expect(searchOperators(ops, 'ива').map(o => o.code)).toEqual(['O1']);
    expect(searchOperators(ops, 'o1').map(o => o.code)).toEqual(['O1']);
  });
  it('excludes inactive operators and non-operator roles', () => {
    expect(searchOperators(ops, '').map(o => o.code)).toEqual(['O1']);
  });
  it('puts an exact code match first', () => {
    const wider = [...ops, {id: 5, code: 'O10', name: 'Орлова', role: 'operator', active: 1}];
    expect(sortSuggestions(searchOperators(wider, 'o1'), 'O1').map(o => o.code)).toEqual(['O1', 'O10']);
  });
});

describe('nextSuggestIndex', () => {
  it('starts at 0 moving down from nothing selected', () => { expect(nextSuggestIndex(-1, 3, 1)).toBe(0); });
  it('starts at the last item moving up from nothing selected', () => { expect(nextSuggestIndex(-1, 3, -1)).toBe(2); });
  it('wraps around at the end', () => { expect(nextSuggestIndex(2, 3, 1)).toBe(0); });
  it('wraps around at the start', () => { expect(nextSuggestIndex(0, 3, -1)).toBe(2); });
  it('returns -1 for an empty list', () => { expect(nextSuggestIndex(-1, 0, 1)).toBe(-1); });
});

describe('foremenOptions / mastersOptions', () => {
  it('includes the currently selected foreman even if inactive', () => {
    const inactive = [...ops, {id: 6, code: 'F2', name: 'Старый', role: 'foreman', active: 0}];
    expect(foremenOptions(inactive, 6).map(o => o.code)).toEqual(['F1', 'F2']);
    expect(foremenOptions(inactive, null).map(o => o.code)).toEqual(['F1']);
  });
  it('includes currently selected masters even if inactive', () => {
    const inactive = [...ops, {id: 7, code: 'M2', name: 'Старая', role: 'master', active: 0}];
    expect(mastersOptions(inactive, [7]).map(o => o.code)).toEqual(['M1', 'M2']);
  });
});

describe('selectedMasters', () => {
  it('forces the own master onto an unlocked doc', () => {
    expect(selectedMasters(3, false, [9])).toEqual([3]);
  });
  it('keeps the document masters once locked', () => {
    expect(selectedMasters(3, true, [9])).toEqual([9]);
  });
  it('keeps the document masters when not acting as master', () => {
    expect(selectedMasters(null, false, [9])).toEqual([9]);
  });
});

describe('byOperator / buildSummary', () => {
  const assignments: AssignmentRow[] = [
    {loom: 'D1', operator_id: 1}, {loom: 'D2', operator_id: 1}, {loom: 'D3', operator_id: null},
  ];
  it('groups looms by operator', () => {
    expect(byOperator(assignments)).toEqual({1: ['D1', 'D2']});
  });
  it('summarises totals and free looms', () => {
    expect(buildSummary(assignments, ops)).toEqual({
      total: 3, withOperator: 2, freeLooms: ['D3'],
      byOperator: [{id: 1, name: 'Иванова', count: 2}],
    });
  });
});

describe('mapLayout', () => {
  it('lays out looms on a grid with an aisle gap for skipped columns', () => {
    const layout = {D1: [1, 1] as [number, number], D2: [1, 3] as [number, number], J1: [2, 1] as [number, number]};
    const m = mapLayout(layout, ['D1', 'D2', 'J1', 'D9']);
    expect(m.rows).toEqual([1, 2]);
    expect(m.template).toBe('minmax(92px,1fr) 18px minmax(92px,1fr)');
    expect(m.colTrack).toEqual({1: 1, 3: 3});
    expect(m.cells).toEqual([{loom: 'D1', row: 1, col: 1}, {loom: 'D2', row: 1, col: 3}, {loom: 'J1', row: 2, col: 1}]);
  });
});

describe('weekRange', () => {
  it('spans the 7 days ending on the given day', () => {
    expect(weekRange('2026.09.25')).toEqual({from: '2026.09.19', to: '2026.09.25'});
  });
});

describe('dash2dot', () => {
  it('converts dashes to dots', () => { expect(dash2dot('2026-09-25')).toBe('2026.09.25'); });
});

describe('buildPrintHtml', () => {
  const fday = (v: unknown) => String(v).split('.').reverse().join('.');
  const ftime = (v: unknown) => String(v);
  it('lists operators sorted by name with their looms and escapes note text', () => {
    const html = buildPrintHtml({
      day: '2026.09.25', shift: 'A', hours: '07:00–15:00',
      doc: {status: 'draft', foreman_id: null, note: null, source: null, updated_by: null, updated_at: null, confirmed_by: null, confirmed_at: null},
      assignments: [{loom: 'D1', operator_id: 1}, {loom: 'D2', operator_id: null}],
      masters: [3], foremanId: 4, note: '<script>x</script>', operators: ops,
    }, fday, ftime);
    expect(html).toContain('Иванова (O1)');
    expect(html).toContain('D1');
    expect(html).toContain('Без оператора: D2');
    expect(html).toContain('&lt;script&gt;x&lt;/script&gt;');
    expect(html).toContain('Кузнецов (F1)');
    expect(html).toContain('Петрова (M1)');
    expect(html).toContain('Черновик — не утверждено');
  });
  it('shows the confirmation line for a posted document', () => {
    const html = buildPrintHtml({
      day: '2026.09.25', shift: 'A', hours: '07:00–15:00',
      doc: {status: 'confirmed', foreman_id: null, note: null, source: null, updated_by: null, updated_at: null, confirmed_by: 'Мастер', confirmed_at: '2026-09-25 08:00'},
      assignments: [], masters: [], foremanId: null, note: '', operators: ops,
    }, fday, ftime);
    expect(html).toContain('Утверждено: Мастер 2026-09-25 08:00');
  });
});
