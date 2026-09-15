"""Собирает дашборд простоев из fact.db в один HTML-файл.

    python build_dashboard.py            # -> dashboard.html
"""
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE / "fact.db"
OUT = HERE / "dashboard.html"

# Индексы категорий остановов в сырых данных станка -> подписи.
# Порядок подтверждён сверкой с журналом остановов и шаблоном отчёта Toyota.
IDX_NAME = {
    0: "Верхний навой", 1: "Основа", 2: "Ложная кромка", 5: "Уток",
    6: "Конец навоя", 7: "Съём ткани", 8: "Ручной останов", 9: "Питание выключено",
    10: "Прочее",
}
UNMAPPED = "Не расшифровано"           # индексы 3, 4, 11, 12 — Toyota их не подписывает

# Что показываем отдельными сериями; остальное (ложная кромка, конец навоя,
# съём ткани, «прочее» станка) сворачивается в «Прочее».
SERIES = ["Уток", "Ручной останов", "Основа", "Верхний навой",
          "Питание выключено", UNMAPPED, "Прочее"]
SHIFT_LETTER = {"0": "A", "1": "B", "2": "C"}

# Смена считается нерабочей, если весь цех (40 станков) наработал меньше этого.
# Такие смены — выходные; они дают 7300 ч «питание выключено» и занижают КПД.
IDLE_SHIFT_RUN_MIN = 400


def split_stops(ct_raw, tm_raw):
    """Сырые 13 категорий -> {название: [кол-во, минуты]} по нашим сериям."""
    out = {s: [0, 0.0] for s in SERIES}
    for i, (c, t) in enumerate(zip(ct_raw.split(), tm_raw.split())):
        name = IDX_NAME.get(i, UNMAPPED)
        if name not in out:
            name = "Прочее"
        out[name][0] += int(c)
        out[name][1] += float(t)
    return out


def build():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    all_rows = [dict(r) for r in db.execute("SELECT * FROM shift_loom ORDER BY shift, loom")]

    # Выходные смены исключаем: в них весь цех обесточен, и они искажают и КПД, и причины.
    run_by_shift = {}
    for r in all_rows:
        run_by_shift[r["shift"]] = run_by_shift.get(r["shift"], 0.0) + r["run_min"]
    idle = {s for s, run in run_by_shift.items() if run < IDLE_SHIFT_RUN_MIN}
    rows = [r for r in all_rows if r["shift"] not in idle]
    idle_hours = round(sum(r["run_min"] + r["stop_min"] for r in all_rows if r["shift"] in idle) / 60)

    days, looms, shifts = {}, {}, {}
    totals = {"run": 0.0, "cal": 0.0, "pick": 0.0, "stops": 0, "by_cause": {s: [0, 0.0] for s in SERIES}}

    for r in rows:
        day = r["shift"][:10]
        letter = SHIFT_LETTER.get(r["shift"][11], "?")
        cal = r["run_min"] + r["stop_min"]
        parts = split_stops(r["stop_ct_raw"], r["stop_tm_raw"])

        for bucket, key in ((days, day), (looms, r["loom"]), (shifts, letter)):
            b = bucket.setdefault(key, {"run": 0.0, "cal": 0.0, "pick": 0.0, "stops": 0,
                                        "by_cause": {s: [0, 0.0] for s in SERIES}})
            b["run"] += r["run_min"]; b["cal"] += cal
            b["pick"] += r["product_kpick"]; b["stops"] += r["total_ct"]
            for name, (c, t) in parts.items():
                b["by_cause"][name][0] += c
                b["by_cause"][name][1] += t

        totals["run"] += r["run_min"]; totals["cal"] += cal
        totals["pick"] += r["product_kpick"]; totals["stops"] += r["total_ct"]
        for name, (c, t) in parts.items():
            totals["by_cause"][name][0] += c
            totals["by_cause"][name][1] += t

    def pack(b):
        return {
            "eff": round(100 * b["run"] / b["cal"], 1) if b["cal"] else 0,
            "pick": round(b["pick"] / 1000, 2),          # млн уточин
            "stops": b["stops"],
            "hours": {k: round(v[1] / 60, 1) for k, v in b["by_cause"].items()},
            "counts": {k: v[0] for k, v in b["by_cause"].items()},
            "cal_h": round(b["cal"] / 60, 1),
        }

    last_shift_id = max(r["shift"] for r in rows)
    last_rows = [r for r in rows if r["shift"] == last_shift_id]
    last_table = []
    for r in sorted(last_rows, key=lambda x: x["effic_pct"]):
        p = split_stops(r["stop_ct_raw"], r["stop_tm_raw"])
        last_table.append({
            "loom": r["loom"], "style": r["style"], "eff": r["effic_pct"], "rpm": r["rpm"],
            "pick": r["product_kpick"], "stops": r["total_ct"],
            "weft": p["Уток"][0], "warp": p["Основа"][0] + p["Верхний навой"][0],
            "manual_min": round(p["Ручной останов"][1]), "stop_min": round(r["stop_min"]),
        })

    loom_table = []
    for loom, b in sorted(looms.items(), key=lambda x: 100 * x[1]["run"] / x[1]["cal"]):
        p = pack(b)
        kp = b["pick"] or 1
        loom_table.append({
            "loom": loom, "eff": p["eff"], "pick": p["pick"],
            "weft_cmpx": round(100 * b["by_cause"]["Уток"][0] / kp, 1),
            "warp_cmpx": round(100 * (b["by_cause"]["Основа"][0] + b["by_cause"]["Верхний навой"][0]) / kp, 1),
            "manual_h": round(b["by_cause"]["Ручной останов"][1] / 60),
            "manual_ct": b["by_cause"]["Ручной останов"][0],
        })

    data = {
        "period": {"from": min(days), "to": max(days), "days": len(days),
                   "looms": len(looms), "shifts": len({r["shift"] for r in rows}),
                   "idle_shifts": len(idle), "idle_hours": idle_hours},
        "totals": pack(totals),
        "daily": [{"day": d, **pack(b)} for d, b in sorted(days.items())],
        "by_shift": [{"shift": s, **pack(b)} for s, b in sorted(shifts.items())],
        "looms": loom_table,
        "last_shift": {"id": last_shift_id, "rows": last_table},
        "series": SERIES,
    }

    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    print(f"Готово: {OUT.name}")
    print(f"  период {data['period']['from']}…{data['period']['to']}  "
          f"({data['period']['days']} дней, {data['period']['shifts']} смен, {data['period']['looms']} станков)")
    print(f"  КПД {data['totals']['eff']}%   потери по причинам, ч: " +
          ", ".join(f"{k} {v}" for k, v in data["totals"]["hours"].items() if v))


TEMPLATE = r"""<meta charset="utf-8">
<title>Простои ткацкого цеха</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --page:#f4f3ef; --surface:#fcfcfb; --surface-2:#efeee9; --ink:#14130f; --ink-2:#52514e;
  --muted:#898781; --hair:#e1e0d9; --rule:#c3c2b7; --accent:#2a78d6;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#008300;
  --good:#0ca30c; --critical:#d03b3b;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#232321; --ink:#fff; --ink-2:#c3c2b7;
  --muted:#898781; --hair:#2c2c2a; --rule:#383835; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300;
}}
:root[data-theme="dark"]{
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#232321; --ink:#fff; --ink-2:#c3c2b7;
  --muted:#898781; --hair:#2c2c2a; --rule:#383835; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#d55181; --s6:#008300;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font-family:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif;font-size:14px;line-height:1.45}
.mono{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace}
.wrap{max-width:1120px;margin:0 auto;padding:24px 20px 72px;display:flex;flex-direction:column;gap:26px}
header{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:14px}
h1{margin:0;font-size:21px;font-weight:600;letter-spacing:-.01em}
.meta{color:var(--ink-2);font-size:13px}
section{display:flex;flex-direction:column;gap:12px}
h2{margin:0;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.lead{color:var(--ink-2);max-width:66ch;margin:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair)}
.tile{background:var(--surface);padding:13px 15px;display:flex;flex-direction:column;gap:3px}
.tile .l{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-size:27px;font-weight:600;line-height:1.05}
.tile .v small{font-size:13px;font-weight:500;color:var(--ink-2)}
.tile .n{font-size:12px;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--hair);padding:16px}
figure{margin:0}
svg{display:block;width:100%;height:auto;overflow:visible}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--ink-2);margin-top:10px}
.legend b{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px}
.stack{display:flex;width:100%;height:26px;gap:2px}
.stack div{height:100%}
.tbl-wrap{overflow-x:auto;border:1px solid var(--hair);background:var(--surface)}
table{width:100%;border-collapse:collapse;min-width:560px}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--hair);white-space:nowrap}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--surface)}
td.n,th.n{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--surface-2)}
.minibar{display:inline-block;height:8px;background:var(--s1);vertical-align:middle;margin-right:7px}
.minibar.low{background:var(--critical)}
.tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--rule);padding:7px 9px;font-size:12px;box-shadow:0 3px 12px rgba(0,0,0,.14);opacity:0;transition:opacity .1s;z-index:10;white-space:nowrap}
.tip.on{opacity:1}
.note{color:var(--muted);font-size:12px;max-width:70ch}
details summary{cursor:pointer;color:var(--ink-2);font-size:13px}
</style>

<div class="wrap">
  <header>
    <div>
      <h1>Простои ткацкого цеха</h1>
      <div class="meta" id="period"></div>
    </div>
    <div class="meta mono" id="src">источник: Toyota FACT</div>
  </header>

  <section>
    <h2>За период</h2>
    <div class="tiles" id="tiles"></div>
    <p class="note" id="tiles-note"></p>
  </section>

  <section>
    <h2>Куда уходит время</h2>
    <p class="lead" id="loss-lead"></p>
    <div class="card">
      <div class="stack" id="stack"></div>
      <div class="legend" id="stack-legend"></div>
    </div>
    <details>
      <summary>Таблица потерь по причинам</summary>
      <div class="tbl-wrap" style="margin-top:8px">
        <table id="loss-table"><thead><tr><th>Причина</th><th class="n">Часов</th><th class="n">Остановов</th><th class="n">Доля времени</th></tr></thead><tbody></tbody></table>
      </div>
    </details>
  </section>

  <section>
    <h2>КПД по дням</h2>
    <div class="card"><figure id="trend"></figure></div>
  </section>

  <section>
    <h2>Смены</h2>
    <div class="tiles" id="shifts"></div>
  </section>

  <section>
    <h2>Станки за период</h2>
    <p class="lead">Отсортировано по КПД. Обрывы приведены к выработке (на 100 000 уточин) — так станки сравнимы независимо от скорости.</p>
    <div class="tbl-wrap">
      <table id="looms"><thead><tr>
        <th>Станок</th><th class="n">КПД</th><th class="n">Уток /cmpx</th><th class="n">Основа /cmpx</th>
        <th class="n">Ручные, ч</th><th class="n">Ручных остановов</th><th class="n">Выработка, млн</th>
      </tr></thead><tbody></tbody></table>
    </div>
  </section>

  <section>
    <h2>Последняя смена</h2>
    <p class="lead" id="last-lead"></p>
    <div class="tbl-wrap">
      <table id="last"><thead><tr>
        <th>Станок</th><th>Артикул</th><th class="n">КПД</th><th class="n">Об/мин</th>
        <th class="n">Простой, мин</th><th class="n">Ручные, мин</th><th class="n">Уток</th><th class="n">Основа</th>
      </tr></thead><tbody></tbody></table>
    </div>
  </section>
</div>
<div class="tip" id="tip"></div>

<script>
const D = __DATA__;
const CLR = ["--s1","--s2","--s3","--s4","--s5","--s6"];
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const nf = (x, d = 0) => x.toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
const tip = document.getElementById("tip");
const showTip = (html, ev) => { tip.innerHTML = html; tip.classList.add("on");
  tip.style.left = Math.min(ev.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px";
  tip.style.top = (ev.clientY - tip.offsetHeight - 10) + "px"; };
const hideTip = () => tip.classList.remove("on");

document.getElementById("period").textContent =
  `${D.period.from} — ${D.period.to} · ${D.period.days} дней · ${D.period.shifts} рабочих смен · ${D.period.looms} станков`;

/* --- плитки --- */
const t = D.totals, manual = t.hours["Ручной останов"], weft = t.hours["Уток"];
const calH = t.cal_h, lostH = Object.values(t.hours).reduce((a, b) => a + b, 0);
document.getElementById("tiles").innerHTML = [
  ["КПД цеха", `${nf(t.eff,1)}<small> %</small>`, "время работы к календарному"],
  ["Потеряно", `${nf(lostH)}<small> ч</small>`, `${nf(100*lostH/calH,1)}% календарного времени`],
  ["Ручные остановы", `${nf(manual)}<small> ч</small>`, `${nf(t.counts["Ручной останов"])} остановов, причина неизвестна`],
  ["Обрывы утка", `${nf(weft)}<small> ч</small>`, `${nf(t.counts["Уток"])} обрывов`],
  ["Выработка", `${nf(t.pick,0)}<small> млн уточин</small>`, `${nf(t.stops)} остановов всего`],
].map(([l, v, n]) => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join("");
document.getElementById("tiles-note").textContent =
  `КПД считается по формуле Toyota: время работы делится на календарное время смены, плановые простои из знаменателя не вычитаются. `
  + `Выходные исключены — ${D.period.idle_shifts} смен, когда цех был обесточен целиком (${nf(D.period.idle_hours)} ч), в расчёт не входят.`;

/* --- структура потерь --- */
const order = D.series.filter(s => t.hours[s] > 0).sort((a, b) => t.hours[b] - t.hours[a]);
const colorOf = {}; order.forEach((s, i) => colorOf[s] = CLR[i % CLR.length]);
document.getElementById("stack").innerHTML = order.map(s =>
  `<div data-cause="${s}" style="width:${100*t.hours[s]/lostH}%;background:var(${colorOf[s]})"></div>`).join("");
document.querySelectorAll("#stack div").forEach(el => {
  const s = el.dataset.cause;
  el.onmousemove = e => showTip(`<b>${s}</b><br>${nf(t.hours[s])} ч · ${nf(100*t.hours[s]/lostH,1)}% простоев · ${nf(t.counts[s])} остановов`, e);
  el.onmouseleave = hideTip;
});
document.getElementById("stack-legend").innerHTML = order.map(s =>
  `<span><b style="background:var(${colorOf[s]})"></b>${s} — ${nf(t.hours[s])} ч</span>`).join("");
document.querySelector("#loss-table tbody").innerHTML = order.map(s =>
  `<tr><td>${s}</td><td class="n">${nf(t.hours[s])}</td><td class="n">${nf(t.counts[s])}</td><td class="n">${nf(100*t.hours[s]/calH,1)} %</td></tr>`).join("");
document.getElementById("loss-lead").textContent =
  `Из ${nf(calH)} часов календарного времени станки простояли ${nf(lostH)} ч. Самая крупная причина после обрывов утка — ручные остановы: ${nf(manual)} ч, и они ничем не расшифрованы: станок лишь фиксирует, что его остановил человек.`;

/* --- тренд КПД --- */
(function trend() {
  const data = D.daily.filter(d => d.eff > 0);
  const W = 1000, H = 260, L = 42, R = 12, T = 12, B = 30;
  const x = i => L + i * (W - L - R) / Math.max(1, data.length - 1);
  const y = v => T + (1 - v / 100) * (H - T - B);
  const grid = [0, 25, 50, 75, 100].map(v =>
    `<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="${css("--hair")}" stroke-width="1"/>
     <text x="${L-8}" y="${y(v)+4}" text-anchor="end" font-size="11" fill="${css("--muted")}" font-family="IBM Plex Mono,monospace">${v}</text>`).join("");
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.eff).toFixed(1)}`).join("");
  const ticks = data.map((d, i) => ({ d, i })).filter(({ i }) => i % Math.ceil(data.length / 8) === 0)
    .map(({ d, i }) => `<text x="${x(i)}" y="${H-8}" text-anchor="middle" font-size="11" fill="${css("--muted")}" font-family="IBM Plex Mono,monospace">${d.day.slice(5).replace(".", "/")}</text>`).join("");
  const last = data[data.length - 1];
  document.getElementById("trend").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="КПД цеха по дням">
    ${grid}${ticks}
    <path d="${path}" fill="none" stroke="${css("--s1")}" stroke-width="2" stroke-linejoin="round"/>
    <circle cx="${x(data.length-1)}" cy="${y(last.eff)}" r="4" fill="${css("--s1")}" stroke="${css("--surface")}" stroke-width="2"/>
    <text x="${x(data.length-1)-8}" y="${y(last.eff)-10}" text-anchor="end" font-size="12" font-weight="600" fill="${css("--ink")}">${nf(last.eff,1)}%</text>
    <g id="hit"></g></svg>`;
  const g = document.getElementById("hit");
  data.forEach((d, i) => {
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("x", x(i) - (W - L - R) / data.length / 2); r.setAttribute("y", T);
    r.setAttribute("width", (W - L - R) / data.length); r.setAttribute("height", H - T - B);
    r.setAttribute("fill", "transparent");
    r.onmousemove = e => showTip(`<b>${d.day}</b><br>КПД ${nf(d.eff,1)}% · ${nf(d.pick,1)} млн уточин<br>ручные остановы ${nf(d.hours["Ручной останов"],1)} ч`, e);
    r.onmouseleave = hideTip;
    g.appendChild(r);
  });
})();

/* --- смены --- */
document.getElementById("shifts").innerHTML = D.by_shift.map(s =>
  `<div class="tile"><div class="l">Смена ${s.shift}</div><div class="v">${nf(s.eff,1)}<small> %</small></div>
   <div class="n">ручные ${nf(s.hours["Ручной останов"])} ч · уток ${nf(s.hours["Уток"])} ч</div></div>`).join("");

/* --- станки --- */
document.querySelector("#looms tbody").innerHTML = D.looms.map(l => {
  const w = Math.max(2, l.eff * 0.6);
  return `<tr><td><strong>${l.loom}</strong></td>
    <td class="n"><span class="minibar${l.eff < 58 ? " low" : ""}" style="width:${w}px"></span>${nf(l.eff,1)}</td>
    <td class="n">${nf(l.weft_cmpx,1)}</td><td class="n">${nf(l.warp_cmpx,1)}</td>
    <td class="n">${nf(l.manual_h)}</td><td class="n">${nf(l.manual_ct)}</td><td class="n">${nf(l.pick,1)}</td></tr>`;
}).join("");

/* --- последняя смена --- */
const ls = D.last_shift;
document.getElementById("last-lead").textContent = `Смена ${ls.id}, отсортировано по КПД — худшие сверху.`;
document.querySelector("#last tbody").innerHTML = ls.rows.map(r =>
  `<tr><td><strong>${r.loom}</strong></td><td>${r.style}</td>
   <td class="n">${nf(r.eff,1)}</td><td class="n">${nf(r.rpm)}</td><td class="n">${nf(r.stop_min)}</td>
   <td class="n">${nf(r.manual_min)}</td><td class="n">${nf(r.weft)}</td><td class="n">${nf(r.warp)}</td></tr>`).join("");
</script>
"""

if __name__ == "__main__":
    build()
