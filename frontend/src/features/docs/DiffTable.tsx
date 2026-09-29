import type { DiffField } from './model';
import { diffRows } from './model';

export function DiffTable({fields, only, before = 'Было', after = 'Стало'}: {fields: DiffField[]; only?: boolean; before?: string; after?: string}) {
  const {rows, hiddenCount} = diffRows(fields, only);
  if (!rows.length) return <p className="note">Реквизиты не менялись.</p>;
  return <>
    <div className="tbl-wrap"><table className="dx-diff"><thead><tr><th>Реквизит</th><th>{before}</th><th>{after}</th><th className="n">Разница</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.key} className={'dx-' + r.kind}>
        <th scope="row">{r.label}</th>
        <td className="dx-was">{r.before.empty ? <span className="dx-none">{r.before.text}</span> : <>{r.before.text}{r.before.source ? <span className="dx-src">{r.before.source}</span> : null}</>}</td>
        <td className="dx-now">{r.after.empty ? <span className="dx-none">{r.after.text}</span> : <>{r.after.text}{r.after.source ? <span className="dx-src">{r.after.source}</span> : null}</>}</td>
        <td className="n">{r.delta ? <span className="dx-delta">{r.delta.sign}{r.delta.text}</span> : null}</td>
      </tr>)}</tbody>
    </table></div>
    {hiddenCount ? <p className="note">Не изменились ещё {hiddenCount} реквизитов — снимите «Только изменённые», чтобы увидеть все.</p> : null}
  </>;
}
