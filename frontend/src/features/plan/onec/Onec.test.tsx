import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Onec } from './Onec';
import type { OnecState } from './controller';
import type { OnecMessage } from './model';
import { legacyFormatters, legacyOnec, legacyOnecDetail, onecDetailOutput, onecMarkup, onecOutput } from '../../../test/legacyPlan';
import type { PlanBridge } from '../bridge';

const messages: OnecMessage[] = [
  {id: 1, received_at: '2026-09-24T07:05:00', who: 'orders@1c', action: 'заказы', order_numbers: '1557, 1558',
    ok: true, result: {cards: 3, yarns_added: 2}},
  {id: 2, received_at: '2026-09-24T08:00:00', who: 'orders@1c', action: 'заказы', order_numbers: '<bad>',
    ok: false, error: 'нет техкарты < & "'},
];
function bridge(): PlanBridge {
  const f = legacyFormatters();
  return {can: () => true, say: vi.fn(), expire: vi.fn(), esc: f.esc, nf: f.nf, fday: f.fday, ftime: f.ftime, dmy: f.dmy};
}
function mount(state: OnecState, loadDetail = vi.fn()) {
  document.body.innerHTML = onecMarkup;
  const tbody = document.querySelector('#oc-msgs tbody')!;
  const dialog = document.querySelector<HTMLDialogElement>('#oc-dlg')!;
  tbody.replaceChildren(); dialog.replaceChildren();
  const b = bridge();
  render(<Onec tbody={tbody as HTMLElement} dialog={dialog} state={state} bridge={b} loadDetail={loadDetail}/>);
  return {tbody, dialog, bridge: b, loadDetail};
}
beforeEach(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {configurable: true, value(this: HTMLDialogElement) {this.open = true;}},
    close: {configurable: true, value(this: HTMLDialogElement) {if (this.open) {this.open = false; this.dispatchEvent(new Event('close'));}}},
  });
});
afterEach(() => {cleanup(); document.body.innerHTML = '';});

describe('Parity with the original 1C-exchange table', () => {
  it('renders the message list exactly like the legacy renderer', async () => {
    mount({messages, loading: false, loaded: true});
    expect(onecOutput(document)).toEqual(onecOutput(await legacyOnec(messages)));
  });
  it('shows the legacy empty-state row once loaded with no messages', async () => {
    mount({messages: [], loading: false, loaded: true});
    expect(onecOutput(document)).toEqual(onecOutput(await legacyOnec([])));
  });
  it('stays empty before the first load resolves, like the legacy tbody', () => {
    mount({messages: [], loading: true, loaded: false});
    expect(document.querySelectorAll('#oc-msgs tbody tr')).toHaveLength(0);
  });
});

describe('Message detail dialog', () => {
  it('opens with the same title and JSON body as the legacy dialog', async () => {
    const detail = {id: 1, received_at: '2026-09-24T07:05:00', payload: {order: 1557}, result: {cards: 3}};
    const {tbody, dialog} = mount({messages, loading: false, loaded: true}, vi.fn().mockResolvedValue(detail));
    fireEvent.click(tbody.querySelector('button')!);
    await waitFor(() => expect(dialog).toHaveAttribute('open'));
    expect(onecDetailOutput(document)).toEqual(onecDetailOutput(await legacyOnecDetail(detail)));
  });
  it('reports a failed detail fetch through bridge.say instead of opening the dialog', async () => {
    const {tbody, dialog, bridge: b} = mount({messages, loading: false, loaded: true},
      vi.fn().mockRejectedValue(new Error('нет связи')));
    fireEvent.click(tbody.querySelector('button')!);
    await waitFor(() => expect(b.say).toHaveBeenCalledWith('Не открылось: нет связи', true));
    expect(dialog.open).toBeFalsy();
  });
});
