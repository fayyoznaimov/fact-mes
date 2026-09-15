"""Веб-страница для самостоятельного разбора данных цеха: фильтры, графики, выгрузка.

Собирает все смены из fact.db, коды ткани — из локального зеркала FACT,
заправочные данные — из artikul_ref.json, и кладёт всё в одну HTML-страницу.

    python build_explorer.py
"""
import io
import json
import os
import re
import sqlite3
from collections import defaultdict

from build_shift_report import parse_cloth

HERE = os.path.dirname(os.path.abspath(__file__))
MIRROR = os.path.join(os.path.dirname(HERE), "factdata", "shift-shift")
DB = os.path.join(HERE, "fact.db")
OUT = os.path.join(HERE, "explorer.html")

# Индексы категорий остановов в сырых данных станка.
IDX_WARP_TOP, IDX_WARP, IDX_WEFT, IDX_MANUAL, IDX_POWER = 0, 1, 5, 8, 9

norm_cloth = lambda c: "CLOTH|" + re.sub(r"[^A-Z0-9]", "", (c or "").replace("%20", "").upper())


def cloth_map(shift):
    path = os.path.join(MIRROR, f"{shift}.txt")
    if not os.path.exists(path):
        return {}
    out = {}
    for line in io.open(path, encoding="utf-8", errors="replace"):
        d = {}
        for field in line.split(","):
            p = field.strip().split(" ", 1)
            if len(p) == 2:
                d[p[0]] = p[1]
        if "mac_name" in d:
            out[d["mac_name"]] = d.get("cloth", "")
    return out


def build():
    ref = json.load(io.open(os.path.join(HERE, "artikul_ref.json"), encoding="utf-8"))
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    looms, designs, days = [], [], []
    li, di, dyi = {}, {}, {}
    rows = []
    idle_shifts = 0

    shifts = [r[0] for r in db.execute("SELECT DISTINCT shift FROM shift_loom ORDER BY shift")]
    run_by_shift = {r[0]: r[1] for r in db.execute(
        "SELECT shift, SUM(run_min) FROM shift_loom GROUP BY shift")}

    for shift in shifts:
        if run_by_shift.get(shift, 0) < 400:      # выходные: цех обесточен целиком
            idle_shifts += 1
            continue
        clothes = cloth_map(shift)
        day, letter = shift[:10], int(shift[-1])
        if day not in dyi:
            dyi[day] = len(days); days.append(day)

        for r in db.execute("SELECT * FROM shift_loom WHERE shift=?", (shift,)):
            if r["run_min"] <= 5:                 # станок в смене не запускался
                continue
            loom = r["loom"]
            if loom not in li:
                li[loom] = len(looms); looms.append(loom)

            cloth = clothes.get(loom, "")
            size, design, gsm = parse_cloth(cloth)
            art = ref.get(norm_cloth(cloth), {})
            design = design or art.get("design_report") or "—"
            if design not in di:
                di[design] = len(designs); designs.append(design)

            ct = [int(x) for x in r["stop_ct_raw"].split()]
            tm = [float(x) for x in r["stop_tm_raw"].split()]
            pick = r["product_kpick"] * 1000
            ppt, wt, pn = art.get("ppt"), art.get("weight_kg"), art.get("panels")
            kg = round(pn * wt * (pick / ppt), 1) if (ppt and wt and pn) else 0

            other_ct = sum(c for i, c in enumerate(ct) if i not in (IDX_WARP_TOP, IDX_WARP, IDX_WEFT, IDX_MANUAL, IDX_POWER))
            other_tm = sum(t for i, t in enumerate(tm) if i not in (IDX_WARP_TOP, IDX_WARP, IDX_WEFT, IDX_MANUAL, IDX_POWER))

            rows.append([
                dyi[day], letter, li[loom], di[design],
                size or 0, art.get("gsm") or (gsm if gsm and 200 <= gsm <= 900 else 0) or 0,
                r["rpm"], round(r["effic_pct"], 1), round(r["run_min"], 1), round(r["stop_min"], 1),
                round(r["product_kpick"], 1), kg,
                ct[IDX_WEFT], round(tm[IDX_WEFT], 1),
                ct[IDX_WARP], round(tm[IDX_WARP], 1),
                ct[IDX_WARP_TOP], round(tm[IDX_WARP_TOP], 1),
                ct[IDX_MANUAL], round(tm[IDX_MANUAL], 1),
                ct[IDX_POWER], round(tm[IDX_POWER], 1),
                other_ct, round(other_tm, 1),
            ])

    data = {"looms": looms, "designs": designs, "days": days, "rows": rows,
            "idleShifts": idle_shifts}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    io.open(OUT, "w", encoding="utf-8").write(html)

    print(f"Готово: {OUT}")
    print(f"  дней {len(days)}, станков {len(looms)}, артикулов {len(designs)}, строк {len(rows)}")
    print(f"  выходных смен исключено: {idle_shifts}")
    print(f"  размер: {os.path.getsize(OUT)/1024:.0f} КБ")


TEMPLATE = r"""<meta charset="utf-8">
<title>Разбор простоев цеха</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --page:#f4f3ef; --surface:#fcfcfb; --surface-2:#efeee9; --ink:#14130f; --ink-2:#52514e;
  --muted:#898781; --hair:#e1e0d9; --rule:#c3c2b7; --accent:#2a78d6;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#e87ba4; --s6:#008300;
  --critical:#d03b3b;
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
.wrap{max-width:1200px;margin:0 auto;padding:18px 16px 64px;display:flex;flex-direction:column;gap:18px}
header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:10px}
h1{margin:0;font-size:20px;font-weight:600;letter-spacing:-.01em}
h2{margin:0 0 9px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.meta{color:var(--ink-2);font-size:13px}

.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;background:var(--surface);border:1px solid var(--hair);padding:12px}
.f{display:flex;flex-direction:column;gap:4px}
.f label{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
select,input[type=date],button{font:inherit;padding:6px 9px;background:var(--surface);color:var(--ink);border:1px solid var(--rule);border-radius:3px}
select[multiple]{min-height:76px;min-width:110px}
button{cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.chips{display:flex;gap:6px}
.chip{padding:6px 11px;border:1px solid var(--rule);background:var(--surface);cursor:pointer;border-radius:3px;font-size:13px}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair)}
.tile{background:var(--surface);padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.tile .l{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-size:25px;font-weight:600;line-height:1.05}
.tile .v small{font-size:12px;font-weight:500;color:var(--ink-2)}
.tile .n{font-size:12px;color:var(--muted)}

.card{background:var(--surface);border:1px solid var(--hair);padding:14px}
svg{display:block;width:100%;height:auto;overflow:visible}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);margin-top:9px}
.legend b{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px}
.stack{display:flex;width:100%;height:24px;gap:2px}

.tbl-wrap{overflow-x:auto;border:1px solid var(--hair);background:var(--surface);max-height:70vh}
table{width:100%;border-collapse:collapse;min-width:860px}
th,td{padding:6px 9px;text-align:left;border-bottom:1px solid var(--hair);white-space:nowrap}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600;cursor:pointer;position:sticky;top:0;background:var(--surface);z-index:1}
th.n,td.n{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
th[aria-sort="descending"],th[aria-sort="ascending"]{color:var(--ink)}
tbody tr:hover{background:var(--surface-2)}
tfoot td{font-weight:600;border-top:2px solid var(--rule);background:var(--surface-2)}
.bar{display:inline-block;height:7px;background:var(--s1);vertical-align:middle;margin-right:6px}
.bar.low{background:var(--critical)}
.note{color:var(--muted);font-size:12px;max-width:74ch}
.tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--rule);padding:6px 9px;font-size:12px;box-shadow:0 3px 12px rgba(0,0,0,.15);opacity:0;transition:opacity .1s;z-index:9;white-space:nowrap}
.tip.on{opacity:1}
</style>

<div class="wrap">
  <header>
    <h1>Разбор простоев цеха</h1>
    <div class="meta" id="period"></div>
  </header>

  <div class="filters">
    <div class="f"><label for="from">Период с</label><select id="from"></select></div>
    <div class="f"><label for="to">по</label><select id="to"></select></div>
    <div class="f"><label>Быстрый выбор</label>
      <div class="chips">
        <button class="chip" data-days="7">7 дней</button>
        <button class="chip" data-days="30">30 дней</button>
        <button class="chip" data-days="0">всё</button>
      </div>
    </div>
    <div class="f"><label>Смены</label>
      <div class="chips" id="shifts">
        <button class="chip" data-shift="0" aria-pressed="true">A</button>
        <button class="chip" data-shift="1" aria-pressed="true">B</button>
        <button class="chip" data-shift="2" aria-pressed="true">C</button>
      </div>
    </div>
    <div class="f"><label>Группа</label>
      <div class="chips" id="group">
        <button class="chip" data-g="all" aria-pressed="true">все</button>
        <button class="chip" data-g="D">махровые D</button>
        <button class="chip" data-g="J">жаккард J</button>
      </div>
    </div>
    <div class="f"><label for="loomSel">Станки</label><select id="loomSel" multiple></select></div>
    <div class="f"><label for="designSel">Артикул</label><select id="designSel" multiple></select></div>
    <div class="f"><label>&nbsp;</label><button id="reset">Сбросить</button></div>
    <div class="f"><label>&nbsp;</label><button class="primary" id="csv">Скачать CSV</button></div>
  </div>

  <section>
    <div class="tiles" id="tiles"></div>
    <p class="note" id="note"></p>
  </section>

  <section>
    <h2>Куда уходит время</h2>
    <div class="card">
      <div class="stack" id="stack"></div>
      <div class="legend" id="stackLegend"></div>
    </div>
  </section>

  <section>
    <h2>КПД по дням</h2>
    <div class="card"><figure id="trend" style="margin:0"></figure></div>
  </section>

  <section>
    <h2>Станки</h2>
    <div class="tbl-wrap">
      <table id="t">
        <thead><tr>
          <th data-k="loom">Станок</th>
          <th class="n" data-k="eff">КПД, %</th>
          <th class="n" data-k="mpick">Млн уточин</th>
          <th class="n" data-k="kg">Кг</th>
          <th class="n" data-k="weftC">Уток, шт</th>
          <th class="n" data-k="weftCmpx">Уток /cmpx</th>
          <th class="n" data-k="warpC">Основа</th>
          <th class="n" data-k="topC">Ворс</th>
          <th class="n" data-k="manC">Ручные, шт</th>
          <th class="n" data-k="manH">Ручные, ч</th>
          <th class="n" data-k="powH">Питание, ч</th>
          <th class="n" data-k="shifts">Смен</th>
        </tr></thead>
        <tbody></tbody><tfoot></tfoot>
      </table>
    </div>
    <p class="note">«Ворс» — обрывы верхнего навоя, «основа» — нижнего. «Уток /cmpx» — обрывы на 100 000 уточин: показатель не зависит от скорости станка, поэтому станки сравнимы между собой. «Ручные» — остановы, которые сделал человек; их причина в Toyota FACT не фиксируется.</p>
  </section>
</div>
<div class="tip" id="tip"></div>

<script>
const D = __DATA__;
const C = { DAY:0, SH:1, LOOM:2, DES:3, SIZE:4, GSM:5, RPM:6, EFF:7, RUN:8, STOP:9, KPICK:10, KG:11,
            WEFTC:12, WEFTT:13, WARPC:14, WARPT:15, TOPC:16, TOPT:17, MANC:18, MANT:19, POWC:20, POWT:21, OTHC:22, OTHT:23 };
const CAUSES = [["Уток","WEFTT","--s1"],["Ручные остановы","MANT","--s2"],["Основа","WARPT","--s3"],
                ["Верхний навой","TOPT","--s4"],["Питание выключено","POWT","--s5"],["Прочее","OTHT","--s6"]];
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const nf = (x,d=0) => x==null ? "—" : Number(x).toLocaleString("ru-RU",{minimumFractionDigits:d,maximumFractionDigits:d});
const tip = document.getElementById("tip");
const showTip = (h,e) => { tip.innerHTML=h; tip.classList.add("on");
  tip.style.left = Math.min(e.clientX+14, innerWidth-tip.offsetWidth-8)+"px";
  tip.style.top = (e.clientY-tip.offsetHeight-10)+"px"; };
const hideTip = () => tip.classList.remove("on");

const st = { from:0, to:D.days.length-1, shifts:new Set([0,1,2]), group:"all", looms:new Set(), designs:new Set(), sortK:"eff", sortD:1 };

const fromSel = document.getElementById("from"), toSel = document.getElementById("to");
const opts = D.days.map((d,i)=>`<option value="${i}">${d.replace(/\./g,"/")}</option>`).join("");
fromSel.innerHTML = opts; toSel.innerHTML = opts;
fromSel.value = st.from; toSel.value = st.to;
document.getElementById("loomSel").innerHTML = D.looms.map((l,i)=>`<option value="${i}">${l}</option>`).join("");
document.getElementById("designSel").innerHTML = D.designs.map((d,i)=>`<option value="${i}">${d}</option>`).join("");

fromSel.onchange = () => { st.from = +fromSel.value; if (st.from > st.to) { st.to = st.from; toSel.value = st.to; } render(); };
toSel.onchange = () => { st.to = +toSel.value; if (st.to < st.from) { st.from = st.to; fromSel.value = st.from; } render(); };
document.querySelectorAll("[data-days]").forEach(b => b.onclick = () => {
  const n = +b.dataset.days;
  st.to = D.days.length-1; st.from = n ? Math.max(0, D.days.length-n) : 0;
  fromSel.value = st.from; toSel.value = st.to; render();
});
document.querySelectorAll("#shifts .chip").forEach(b => b.onclick = () => {
  const s = +b.dataset.shift;
  st.shifts.has(s) ? st.shifts.delete(s) : st.shifts.add(s);
  if (!st.shifts.size) st.shifts.add(s);
  document.querySelectorAll("#shifts .chip").forEach(x => x.setAttribute("aria-pressed", st.shifts.has(+x.dataset.shift)));
  render();
});
document.querySelectorAll("#group .chip").forEach(b => b.onclick = () => {
  st.group = b.dataset.g;
  document.querySelectorAll("#group .chip").forEach(x => x.setAttribute("aria-pressed", x.dataset.g === st.group));
  render();
});
document.getElementById("loomSel").onchange = e => {
  st.looms = new Set([...e.target.selectedOptions].map(o => +o.value)); render(); };
document.getElementById("designSel").onchange = e => {
  st.designs = new Set([...e.target.selectedOptions].map(o => +o.value)); render(); };
document.getElementById("reset").onclick = () => {
  st.from = 0; st.to = D.days.length-1; st.shifts = new Set([0,1,2]); st.group = "all";
  st.looms = new Set(); st.designs = new Set();
  fromSel.value = st.from; toSel.value = st.to;
  document.querySelectorAll("#shifts .chip").forEach(x => x.setAttribute("aria-pressed", true));
  document.querySelectorAll("#group .chip").forEach(x => x.setAttribute("aria-pressed", x.dataset.g === "all"));
  document.getElementById("loomSel").selectedIndex = -1;
  document.getElementById("designSel").selectedIndex = -1;
  render();
};
document.querySelectorAll("#t thead th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  st.sortD = (k === st.sortK) ? -st.sortD : 1;
  st.sortK = k; render();
});

function filtered() {
  return D.rows.filter(r => {
    if (r[C.DAY] < st.from || r[C.DAY] > st.to) return false;
    if (!st.shifts.has(r[C.SH])) return false;
    const name = D.looms[r[C.LOOM]];
    if (st.group !== "all" && name[0] !== st.group) return false;
    if (st.looms.size && !st.looms.has(r[C.LOOM])) return false;
    if (st.designs.size && !st.designs.has(r[C.DES])) return false;
    return true;
  });
}

function render() {
  const rows = filtered();
  document.getElementById("period").textContent =
    `${D.days[st.from].replace(/\./g,"/")} — ${D.days[st.to].replace(/\./g,"/")} · смены ${[...st.shifts].sort().map(s=>"ABC"[s]).join("")} · записей ${nf(rows.length)}`;

  const s = k => rows.reduce((a,r) => a + r[C[k]], 0);
  const run = s("RUN"), stop = s("STOP"), cal = run + stop;
  const eff = cal ? 100*run/cal : 0;
  const kpick = s("KPICK"), kg = s("KG");
  const manH = s("MANT")/60, weftH = s("WEFTT")/60;

  document.getElementById("tiles").innerHTML = [
    ["КПД", `${nf(eff,1)}<small> %</small>`, `отработано ${nf(run/60)} ч из ${nf(cal/60)} ч`],
    ["Выработка", `${nf(kpick/1000,1)}<small> млн уточин</small>`, kg ? `${nf(kg)} кг там, где есть артикул` : "артикулы не найдены"],
    ["Ручные остановы", `${nf(manH)}<small> ч</small>`, `${nf(s("MANC"))} остановов без причины`],
    ["Обрывы утка", `${nf(s("WEFTC"))}`, `${nf(weftH)} ч простоя`],
    ["Обрывы навоев", `${nf(s("WARPC")+s("TOPC"))}`, `основа ${nf(s("WARPC"))} · ворс ${nf(s("TOPC"))}`],
    ["Станков в срезе", `${new Set(rows.map(r=>r[C.LOOM])).size}`, `дней ${new Set(rows.map(r=>r[C.DAY])).size}`],
  ].map(([l,v,n]) => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join("");
  document.getElementById("note").textContent =
    `Выходные смены, когда цех был обесточен целиком, исключены из данных (${D.idleShifts} смен). КПД считается по формуле Toyota: время работы к календарному времени смены.`;

  // структура потерь
  const tot = CAUSES.map(([name,key,color]) => ({ name, color, h: s(key)/60 }));
  const lost = tot.reduce((a,x)=>a+x.h,0) || 1;
  tot.sort((a,b)=>b.h-a.h);
  document.getElementById("stack").innerHTML = tot.filter(x=>x.h>0).map(x =>
    `<div data-n="${x.name}" data-h="${x.h}" style="width:${100*x.h/lost}%;background:var(${x.color})"></div>`).join("");
  document.querySelectorAll("#stack div").forEach(el => {
    el.onmousemove = e => showTip(`<b>${el.dataset.n}</b><br>${nf(+el.dataset.h)} ч · ${nf(100*el.dataset.h/lost,1)}% простоев`, e);
    el.onmouseleave = hideTip;
  });
  document.getElementById("stackLegend").innerHTML = tot.filter(x=>x.h>0).map(x =>
    `<span><b style="background:var(${x.color})"></b>${x.name} — ${nf(x.h)} ч</span>`).join("");

  trend(rows);

  // таблица по станкам
  const by = new Map();
  rows.forEach(r => {
    const k = r[C.LOOM];
    if (!by.has(k)) by.set(k, { loom: D.looms[k], run:0, stop:0, kpick:0, kg:0, weftC:0, warpC:0, topC:0, manC:0, manT:0, powT:0, shifts:0 });
    const a = by.get(k);
    a.run += r[C.RUN]; a.stop += r[C.STOP]; a.kpick += r[C.KPICK]; a.kg += r[C.KG];
    a.weftC += r[C.WEFTC]; a.warpC += r[C.WARPC]; a.topC += r[C.TOPC];
    a.manC += r[C.MANC]; a.manT += r[C.MANT]; a.powT += r[C.POWT]; a.shifts += 1;
  });
  const list = [...by.values()].map(a => ({
    ...a, eff: a.run+a.stop ? 100*a.run/(a.run+a.stop) : 0,
    mpick: a.kpick/1000, weftCmpx: a.kpick ? 100*a.weftC/a.kpick : 0,
    manH: a.manT/60, powH: a.powT/60,
  }));
  list.sort((x,y) => { const a=x[st.sortK], b=y[st.sortK];
    return (typeof a === "string" ? a.localeCompare(b) : a-b) * st.sortD; });
  document.querySelectorAll("#t thead th").forEach(th =>
    th.setAttribute("aria-sort", th.dataset.k===st.sortK ? (st.sortD<0?"descending":"ascending") : "none"));
  document.querySelector("#t tbody").innerHTML = list.map(a => `
    <tr><td><strong>${a.loom}</strong></td>
      <td class="n"><span class="bar${a.eff<60?" low":""}" style="width:${Math.max(2,a.eff*0.5)}px"></span>${nf(a.eff,1)}</td>
      <td class="n">${nf(a.mpick,1)}</td><td class="n">${a.kg?nf(a.kg):"—"}</td>
      <td class="n">${nf(a.weftC)}</td><td class="n">${nf(a.weftCmpx,1)}</td>
      <td class="n">${nf(a.warpC)}</td><td class="n">${nf(a.topC)}</td>
      <td class="n">${nf(a.manC)}</td><td class="n">${nf(a.manH)}</td>
      <td class="n">${nf(a.powH)}</td><td class="n">${nf(a.shifts)}</td></tr>`).join("");
  const T = k => list.reduce((x,a)=>x+a[k],0);
  document.querySelector("#t tfoot").innerHTML = list.length ? `<tr>
      <td>Итого ${list.length} станков</td><td class="n">${nf(eff,1)}</td>
      <td class="n">${nf(T("mpick"),1)}</td><td class="n">${nf(T("kg"))}</td>
      <td class="n">${nf(T("weftC"))}</td><td class="n">${nf(T("kpick")?100*T("weftC")/T("kpick"):0,1)}</td>
      <td class="n">${nf(T("warpC"))}</td><td class="n">${nf(T("topC"))}</td>
      <td class="n">${nf(T("manC"))}</td><td class="n">${nf(T("manH"))}</td>
      <td class="n">${nf(T("powH"))}</td><td class="n">${nf(T("shifts"))}</td></tr>` : "";

  window.__csv = list;
}

function trend(rows) {
  const byDay = new Map();
  rows.forEach(r => {
    const d = r[C.DAY];
    if (!byDay.has(d)) byDay.set(d, { run:0, stop:0, man:0 });
    const a = byDay.get(d); a.run += r[C.RUN]; a.stop += r[C.STOP]; a.man += r[C.MANT];
  });
  const data = [...byDay.entries()].sort((a,b)=>a[0]-b[0])
    .map(([d,a]) => ({ day: D.days[d], eff: a.run+a.stop ? 100*a.run/(a.run+a.stop) : 0, manH: a.man/60 }));
  const W=1000,H=230,L=38,R=10,T=10,B=26;
  const x = i => L + i*(W-L-R)/Math.max(1,data.length-1);
  const y = v => T + (1-v/100)*(H-T-B);
  const grid = [0,25,50,75,100].map(v =>
    `<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="${css("--hair")}"/>
     <text x="${L-6}" y="${y(v)+4}" text-anchor="end" font-size="10" fill="${css("--muted")}">${v}</text>`).join("");
  const path = data.map((d,i)=>`${i?"L":"M"}${x(i).toFixed(1)},${y(d.eff).toFixed(1)}`).join("");
  const step = Math.max(1, Math.ceil(data.length/8));
  const ticks = data.map((d,i)=> i%step===0
    ? `<text x="${x(i)}" y="${H-6}" text-anchor="middle" font-size="10" fill="${css("--muted")}">${d.day.slice(5).replace(".","/")}</text>` : "").join("");
  document.getElementById("trend").innerHTML = data.length
    ? `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="КПД по дням в выбранном срезе">${grid}${ticks}
       <path d="${path}" fill="none" stroke="${css("--s1")}" stroke-width="2"/><g id="hit"></g></svg>`
    : `<p class="note">Нет данных под выбранные фильтры.</p>`;
  const g = document.getElementById("hit");
  if (!g) return;
  data.forEach((d,i) => {
    const r = document.createElementNS("http://www.w3.org/2000/svg","rect");
    r.setAttribute("x", x(i)-(W-L-R)/data.length/2); r.setAttribute("y", T);
    r.setAttribute("width",(W-L-R)/data.length); r.setAttribute("height",H-T-B);
    r.setAttribute("fill","transparent");
    r.onmousemove = e => showTip(`<b>${d.day}</b><br>КПД ${nf(d.eff,1)}% · ручные ${nf(d.manH,1)} ч`, e);
    r.onmouseleave = hideTip;
    g.appendChild(r);
  });
}

// Сохранение среза. На опубликованной странице файл отдаёт платформа (она же
// спрашивает согласие); при локальном открытии этой возможности нет — тогда
// работает обычная ссылка на файл в памяти.
const csvBtn = document.getElementById("csv");
let downloads = null;
if (window.claude && typeof claude.use === "function") {
  claude.use("downloads").then(d => { downloads = d; }).catch(() => {});
}
csvBtn.onclick = async () => {
  const head = ["Станок","КПД %","Млн уточин","Кг","Уток шт","Уток /cmpx","Основа","Ворс","Ручные шт","Ручные ч","Питание ч","Смен"];
  const body = (window.__csv||[]).map(a => [a.loom, a.eff.toFixed(1), a.mpick.toFixed(2), a.kg.toFixed(1),
    a.weftC, a.weftCmpx.toFixed(1), a.warpC, a.topC, a.manC, a.manH.toFixed(1), a.powH.toFixed(1), a.shifts]);
  const csv = "﻿" + [head, ...body].map(r => r.join(";")).join("\r\n");
  const name = `цех_${D.days[st.from]}_${D.days[st.to]}.csv`.replace(/\./g,"-");
  const say = (t) => { const was = csvBtn.textContent; csvBtn.textContent = t;
    setTimeout(() => { csvBtn.textContent = was; }, 2500); };

  if (downloads) {
    try {
      await downloads.save({ filename: name, data: csv });
    } catch (e) {
      if (e && e.code === "declined") return;          // viewer сказал «нет» — молча
      say("Не удалось сохранить");
    }
    return;
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type:"text/csv" }));
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
};

render();
</script>
"""

if __name__ == "__main__":
    build()
