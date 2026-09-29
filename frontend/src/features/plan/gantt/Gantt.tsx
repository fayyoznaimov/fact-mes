import { Fragment, useEffect, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import type { PlanBridge } from '../bridge';
import type { GanttState, TimelineState } from './controller';
import {
  CAUSE_COLOR, addDays, eventBarView, eventRowStart, factBarView, lastWorkedFact,
  planBarView, rangeText, tickLabels, timeScale, timelineSummary, timelineTitle, weekdayOf,
} from './model';
import type { GanttLoom } from './model';

function groupConsecutive(looms: GanttLoom[]) {
  const out: {group: string; looms: GanttLoom[]}[] = [];
  for (const l of looms) {
    const last = out[out.length - 1];
    if (last && last.group === l.group) last.looms.push(l); else out.push({group: l.group, looms: [l]});
  }
  return out;
}

type Props = {
  barEl: HTMLElement; wrapEl: HTMLElement; dialog: HTMLDialogElement;
  state: GanttState; timeline: TimelineState | null; bridge: PlanBridge;
  setDays: (n: number) => void; setGroup: (g: string) => void;
  prev: () => void; next: () => void; today: () => void;
  openTimeline: (loom: string, a: string, b: string) => void;
  stepTimeline: (hours: number) => void; closeTimeline: () => void;
};

export function Gantt({barEl, wrapEl, dialog, state, timeline, bridge, setDays, setGroup, prev, next, today,
  openTimeline, stepTimeline, closeTimeline}: Props) {
  const {nf, dmy, say} = bridge;
  useEffect(() => {
    const onClose = () => closeTimeline();
    dialog.addEventListener('close', onClose);
    return () => dialog.removeEventListener('close', onClose);
  }, [dialog, closeTimeline]);
  useEffect(() => { if (timeline && !dialog.open) dialog.showModal(); }, [timeline, dialog]);

  const onLoomClick = (l: GanttLoom) => {
    const f = lastWorkedFact(l);
    if (f) openTimeline(l.loom, f.start, f.end);
    else say(`По ${l.loom} за эти дни смен с работой нет`);
  };

  const g = state.data;
  const groups = g ? groupConsecutive(g.looms.filter(l => !state.group || l.group === state.group)) : [];

  return <>
    {createPortal(<>
      <div className="f"><label>Период</label><div style={{display: 'flex', gap: 4}}>
        <button className="act" type="button" onClick={prev} aria-label="Раньше">←</button>
        <button className="act" type="button" onClick={today}>Эта неделя</button>
        <button className="act" type="button" onClick={next} aria-label="Позже">→</button>
      </div></div>
      <div className="f"><label htmlFor="gt-days">Дней</label>
        <select id="gt-days" value={state.days} onChange={e => setDays(Number(e.target.value))}>
          <option value={3}>3</option><option value={7}>7</option><option value={14}>14</option>
        </select></div>
      <div className="f"><label htmlFor="gt-group">Станки</label>
        <select id="gt-group" value={state.group} onChange={e => setGroup(e.target.value)}>
          <option value="">все</option><option>Dobby</option><option>Jakart Bonas</option><option>Jakart Staubli</option>
        </select></div>
      <div className="f"><label>{' '}</label><span className="note" id="gt-range" style={{padding: '7px 0'}}>
        {g ? rangeText(g, dmy) : ''}</span></div>
    </>, barEl)}

    {createPortal(!g ? <p className="note" style={{padding: 12}}>Загружаю…</p> : (() => {
      const {pos, wid} = timeScale(g.from, g.to);
      const now = Date.parse(g.now), t0 = Date.parse(g.from), span = Date.parse(g.to) - t0;
      const nowVisible = now > t0 && now < t0 + span;
      return <div className="gt">
        <div className="gt-names">
          <div className="gt-ax-sp">Станок</div>
          {groups.map(group => <Fragment key={group.group}>
            <div className="gt-g">{group.group}</div>
            {group.looms.map(l => <div className="gt-n" key={l.loom}>
              <button type="button" className="gt-loom" title="Остановы станка по секундам" onClick={() => onLoomClick(l)}>{l.loom}</button>
            </div>)}
          </Fragment>)}
        </div>
        <div className="gt-canvas">
          <div className="gt-ax">
            {g.days.map(d => {
              const s = d.replace(/\./g, '-') + 'T07:00:00', e = addDays(d, 1).replace(/\./g, '-') + 'T07:00:00';
              return <b key={d} style={{left: pos(s) + '%', width: wid(s, e) + '%'}}>{dmy(d)} {weekdayOf(d)}</b>;
            })}
            {g.days.length <= 7 && g.schedule.map((s, i) => <small key={i} style={{left: pos(s.start) + '%'}}>{s.shift}</small>)}
          </div>
          <div className="gt-body">
            {g.schedule.map((s, i) => <i key={i} className={`gt-s ${s.off ? 'off' : 's' + s.shift}`}
              style={{left: pos(s.start) + '%', width: wid(s.start, s.end) + '%'}}/>)}
            {nowVisible && <i className="gt-now" style={{left: pos(g.now) + '%'}} title="сейчас"/>}
            {groups.map(group => <Fragment key={group.group}>
              <div className="gt-g"/>
              {group.looms.map(l => <div className="gt-r" key={l.loom}>
                <div className="gt-lane p">{l.plan.map((b, i) => {
                  const v = planBarView(b, dmy, nf);
                  const style: CSSProperties & Record<string, string> = {left: pos(b.start) + '%', width: wid(b.start, b.end) + '%'};
                  if (v.hue != null) style['--h'] = String(v.hue);
                  return <div key={i} className={'gt-b plan' + (v.hasOrder ? '' : ' nt')} style={style} title={v.tip}>{v.label}</div>;
                })}</div>
                <div className="gt-lane f">{l.fact.map((f, i) => {
                  const v = factBarView(f, dmy, nf);
                  return <div key={i} className={`gt-b fact ${v.cls}`} tabIndex={0} role="button"
                    style={{left: pos(f.start) + '%', width: wid(f.start, f.end) + '%'}} title={v.tip}
                    onClick={() => openTimeline(l.loom, f.start, f.end)}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openTimeline(l.loom, f.start, f.end); } }}>
                    {v.label}
                  </div>;
                })}</div>
              </div>)}
            </Fragment>)}
          </div>
        </div>
      </div>;
    })(), wrapEl)}

    {timeline && createPortal((() => {
      const {data} = timeline, t0 = Date.parse(data.from), span = Date.parse(data.to) - t0;
      const tlClass = 'tl' + (data.shift && !data.shift.worked ? ' off' : '');
      return <form method="dialog">
        <h3 id="gt-dlg-t" style={{margin: '0 0 4px', fontSize: 15}}>{timelineTitle(timeline.loom, data, dmy)}</h3>
        <p className="note" id="gt-dlg-sum" style={{margin: '0 0 8px'}}>{timelineSummary(data, nf)}</p>
        <div className={tlClass} id="gt-tl">
          {data.events.map((e, i) => {
            const v = eventBarView(e, t0, span);
            return <i key={i} style={{left: v.left + '%', width: v.width + '%', background: v.color}}
              title={`${e.start.slice(11, 19)}, ${e.cause_ru}, ${e.dur} с`}/>;
          })}
        </div>
        <div className="tl-ax" id="gt-tl-ax">
          {tickLabels(t0, span).map((tk, i) => <span key={i} style={{left: tk.left + '%'}}>{tk.text}</span>)}
        </div>
        <div className="legend" id="gt-tl-leg">
          <span><i style={{background: '#2f9e63'}}/>работа</span>
          {data.by_cause.map((c, i) => <span key={i}>
            <i style={{background: CAUSE_COLOR[c.cause] || CAUSE_COLOR.Other}}/>{c.cause_ru}: {c.n} раз, {nf(c.sec / 60, 0)} мин
          </span>)}
        </div>
        <div className="tbl-wrap" style={{maxHeight: '36vh', marginTop: 8}}>
          <table id="gt-tl-list">
            <thead><tr><th>Начало</th><th className="n">Стоял, с</th><th>Причина</th><th>Код</th><th className="n">Ждал оператора, с</th></tr></thead>
            <tbody>
              {data.events.length ? data.events.slice(0, 500).map((e, i) => <tr key={i}>
                <td>{eventRowStart(e, data.from, dmy)}</td><td className="n">{e.dur}</td>
                <td>{e.cause_ru}</td><td>{e.code || ''}</td><td className="n">{e.resp ?? ''}</td>
              </tr>) : <tr><td colSpan={5} className="note">Остановов за это время нет</td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{display: 'flex', gap: 6, marginTop: 10}}>
          <button className="act" type="button" onClick={() => stepTimeline(-8)}>← Смена раньше</button>
          <button className="act" type="button" onClick={() => stepTimeline(8)}>Смена позже →</button>
          <button className="act" value="close">Закрыть</button>
        </div>
      </form>;
    })(), dialog)}
  </>;
}
