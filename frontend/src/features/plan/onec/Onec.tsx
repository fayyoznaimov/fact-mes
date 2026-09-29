import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import type { PlanBridge } from '../bridge';
import type { OnecState } from './controller';
import type { OnecDetail, OnecMessage } from './model';
import { outcomeText } from './model';

type Detail = {id: number; receivedAt: string; text: string};
type Props = {
  tbody: HTMLElement;
  dialog: HTMLDialogElement;
  state: OnecState;
  bridge: PlanBridge;
  loadDetail: (id: number) => Promise<OnecDetail>;
};

export function Onec({tbody, dialog, state, bridge, loadDetail}: Props) {
  const [detail, setDetail] = useState<Detail | null>(null);
  useEffect(() => {
    const onClose = () => setDetail(null);
    dialog.addEventListener('close', onClose);
    return () => dialog.removeEventListener('close', onClose);
  }, [dialog]);
  useEffect(() => { if (detail && !dialog.open) dialog.showModal(); }, [detail, dialog]);

  const open = async (m: OnecMessage) => {
    try {
      const d = await loadDetail(m.id);
      setDetail({id: d.id, receivedAt: d.received_at,
        text: JSON.stringify({прислали: d.payload, ответили: d.result || {error: d.error}}, null, 2)});
    } catch (e) {
      bridge.say('Не открылось: ' + (e instanceof Error ? e.message : String(e)), true);
    }
  };

  const rows = state.loaded && !state.messages.length
    ? <tr><td colSpan={6} className="note">1С ещё ничего не присылала.</td></tr>
    : state.messages.map(m => (
      <tr key={m.id}>
        <td>{bridge.ftime(m.received_at || '')}</td>
        <td>{m.who || ''}</td>
        <td>{m.action || '—'}</td>
        <td style={{whiteSpace: 'normal', maxWidth: '30ch'}}>{m.order_numbers || '—'}</td>
        <td className={m.ok ? 'ok' : 'bad'}>{outcomeText(m)}</td>
        <td><button className="act" style={{padding: '2px 8px'}} onClick={() => void open(m)}>Что прислали</button></td>
      </tr>
    ));

  return <>
    {createPortal(rows, tbody)}
    {detail && createPortal(<form method="dialog">
      <h3 id="oc-dlg-t" style={{margin: '0 0 10px', fontSize: 15}}>{`Сообщение 1С №${detail.id} · ${bridge.ftime(detail.receivedAt || '')}`}</h3>
      <pre id="oc-json">{detail.text}</pre>
      <div style={{marginTop: 10}}><button className="act" value="close">Закрыть</button></div>
    </form>, dialog)}
  </>;
}
