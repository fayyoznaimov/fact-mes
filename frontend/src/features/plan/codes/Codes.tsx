import { useRef } from 'react';
import { createPortal } from 'react-dom';
import type { PlanBridge } from '../bridge';
import type { CodesState } from './controller';

type Props = {
  unmappedBody: HTMLElement;
  mapBody: HTMLElement;
  state: CodesState;
  bridge: PlanBridge;
  link: (cloth: string, product: string) => void;
  unlink: (cloth: string) => void;
};

export function Codes({unmappedBody, mapBody, state, bridge, link, unlink}: Props) {
  const inputs = useRef<Record<number, HTMLInputElement | null>>({});
  const canSetup = bridge.can('setup_edit');

  const unmappedRows = state.loaded && !state.unmapped.length
    ? <tr><td colSpan={5} className="note">Все коды ткани за две недели опознаны.</td></tr>
    : state.unmapped.map((u, i) => (
      <tr key={u.cloth}>
        <td><b>{u.cloth}</b>{u.variants > 1 ? <> <small className="note">и ещё {u.variants - 1} написания</small></> : null}</td>
        <td>{u.looms.join(', ')}</td>
        <td className="n">{bridge.nf(u.rows)}</td>
        <td>{bridge.fday(u.last_day || '')}</td>
        <td>
          <input size={24} list="pl-products" placeholder="артикул 1С" autoComplete="off" disabled={!canSetup}
            ref={el => {inputs.current[i] = el;}}/>
          <button className="act" disabled={!canSetup} onClick={() => link(u.cloth, (inputs.current[i]?.value || '').trim())}>Связать</button>
        </td>
      </tr>
    ));

  const mapRows = state.loaded && !state.clothMap.length
    ? <tr><td colSpan={4} className="note">Связок пока нет.</td></tr>
    : state.clothMap.map(m => (
      <tr key={m.cloth_code}>
        <td>{m.cloth_code}</td><td>{m.product_code}</td><td>{m.set_by || ''}</td>
        <td><button className="act" disabled={!canSetup} onClick={() => unlink(m.cloth_code)}>Снять</button></td>
      </tr>
    ));

  return <>{createPortal(unmappedRows, unmappedBody)}{createPortal(mapRows, mapBody)}</>;
}
