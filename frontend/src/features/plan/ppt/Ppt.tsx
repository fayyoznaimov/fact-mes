import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import type { PlanBridge } from '../bridge';
import type { PptState } from './controller';
import { isBad, sign, verdictText } from './model';

type Props = {
  productsBody: HTMLElement;
  daysSummary: HTMLElement;
  daysBody: HTMLElement;
  daysDetails: HTMLDetailsElement;
  state: PptState;
  bridge: PlanBridge;
};

export function Ppt({productsBody, daysSummary, daysBody, daysDetails, state, bridge}: Props) {
  const [opened, setOpened] = useState(daysDetails.open);
  useEffect(() => {
    const onToggle = () => { if (daysDetails.open) setOpened(true); };
    daysDetails.addEventListener('toggle', onToggle);
    return () => daysDetails.removeEventListener('toggle', onToggle);
  }, [daysDetails]);

  const {nf} = bridge;
  const productRows = !state.products.length
    ? <tr><td colSpan={10} className="note">Нет станко-дней, где в плане изделие с PPT из 1С.</td></tr>
    : state.products.map(p => (
      <tr key={p.product_code}>
        <td>{p.product_code}</td><td>{p.orders.join(', ')}</td>
        <td className="n">{nf(p.ppt_1c)}</td><td className="n">{p.ppt_fact ? nf(p.ppt_fact) : '—'}</td>
        <td className={'n' + (isBad(p.dev, state.threshold) ? ' bad' : '')}>{sign(p.dev, nf)}</td>
        <td className="n">{p.sec_1c ? nf(p.sec_1c) : '—'}</td>
        <td className={'n' + (p.norm_pct != null && p.norm_pct < 90 ? ' bad' : '')}>{p.norm_pct != null ? nf(p.norm_pct) + '%' : '—'}</td>
        <td className="n" title={`из них с совпадающим кодом ткани: ${p.clean_days}`}>{p.days}</td>
        <td>{p.looms.join(', ')}</td>
        <td className={p.verdict === 'проверьте PPT в 1С' ? 'bad' : p.verdict === 'совпадает' ? 'ok' : 'note'}>{p.verdict}</td>
      </tr>
    ));

  const off = state.days.filter(d => d.verdict !== 'ok');
  const summary = state.loaded ? `По станкам и дням: ${nf(state.days.length)}, с расхождением больше ${state.threshold}% — ${nf(off.length)}` : 'По станкам и дням';

  const dayRows = state.days.slice().reverse().map(d => (
    <tr key={d.day + d.loom}>
      <td>{bridge.dmy(d.day)}</td><td><b>{d.loom}</b></td><td>{d.order_no}</td><td>{d.product_code}</td>
      <td className="n">{nf(d.ppt_1c)}</td><td className="n">{nf(d.ppt_fact)}</td>
      <td className={'n' + (d.verdict !== 'ok' ? ' bad' : '')}>{sign(d.dev, nf)}</td>
      <td className="n">{nf(d.rows)}</td>
      <td className={'n' + (d.norm_pct != null && d.norm_pct < 90 ? ' bad' : '')} title={`КПД по времени ${nf(d.time_eff, 1)}%`}>
        {d.norm_pct != null ? nf(d.norm_pct) + '%' : '—'}
      </td>
      <td className="n">{d.rpm ? nf(d.rpm) : ''}</td>
      <td>{(d.cloth || '').replace(/%20/g, ' ')}</td>
      <td className={d.verdict === 'ok' ? 'ok' : d.verdict === 'diff' ? '' : 'bad'} style={{whiteSpace: 'normal'}}>{verdictText(d)}</td>
    </tr>
  ));

  return <>
    {createPortal(productRows, productsBody)}
    {createPortal(summary, daysSummary)}
    {opened && createPortal(dayRows, daysBody)}
  </>;
}
