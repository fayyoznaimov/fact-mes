"""Посменная страница: к какому станку идти в начале смены.

Показывает по каждому станку за выбранную смену: обрывы утка, ворса и основы,
время их устранения, среднее время устранения (MTTR), ожидание оператора и
выработку в уточинах. Данные — из базы fact.db (таблица shift_full).

    python build_shift_view.py
"""
import io
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "fact.db")
OUT = os.path.join(HERE, "shift_view.html")
SHIFT_COUNT = 60          # сколько последних смен класть в страницу


def build():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    shifts = [r[0] for r in db.execute(
        "SELECT DISTINCT shift FROM shift_full ORDER BY shift DESC LIMIT ?", (SHIFT_COUNT,))]
    shifts.reverse()

    data = []
    for shift in shifts:
        rows = []
        for r in db.execute(
                "SELECT * FROM shift_full WHERE shift=? AND run_min > 5 ORDER BY loom", (shift,)):
            rows.append({
                "loom": r["loom"], "style": r["style"] or "—", "cloth": r["cloth"] or "",
                "rpm": r["rpm"], "eff": r["effic_pct"],
                "picks": r["picks"], "meters": r["meters"], "pieces": r["pieces"],
                "run": r["run_min"], "stop": r["stop_min"],
                "weft": [r["weft_ct"], r["weft_fix_min"], r["weft_mttr_sec"], r["weft_wait_min"]],
                "top": [r["top_ct"], r["top_fix_min"], r["top_mttr_sec"], r["top_wait_min"]],
                "warp": [r["warp_ct"], r["warp_fix_min"], r["warp_mttr_sec"], r["warp_wait_min"]],
                "manual": [r["manual_ct"], r["manual_min"]],
                "wait": r["wait_total_min"],
            })
        if rows:
            data.append({"shift": shift, "rows": rows})

    payload = {"shifts": data}
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    io.open(OUT, "w", encoding="utf-8").write(html)

    last = data[-1]
    worst = sorted(last["rows"], key=lambda x: x["stop"], reverse=True)[:3]
    print(f"Готово: {OUT}")
    print(f"  смен на странице: {len(data)} ({data[0]['shift']} … {last['shift']})")
    print(f"  размер: {os.path.getsize(OUT)/1024:.0f} КБ")
    print(f"  худшие станки последней смены: " +
          ", ".join(f"{w['loom']} ({w['stop']:.0f} мин простоя)" for w in worst))
    db.close()


TEMPLATE = r"""<meta charset="utf-8">
<title>Обход цеха по сменам</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --page:#f4f3ef; --surface:#fcfcfb; --surface-2:#efeee9; --ink:#14130f; --ink-2:#52514e;
  --muted:#898781; --hair:#e1e0d9; --rule:#c3c2b7; --accent:#2a78d6;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#232321; --ink:#fff; --ink-2:#c3c2b7;
  --muted:#898781; --hair:#2c2c2a; --rule:#383835; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
}}
:root[data-theme="dark"]{
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#232321; --ink:#fff; --ink-2:#c3c2b7;
  --muted:#898781; --hair:#2c2c2a; --rule:#383835; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font-family:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif;font-size:14px;line-height:1.45}
.wrap{max-width:1240px;margin:0 auto;padding:18px 14px 60px;display:flex;flex-direction:column;gap:18px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:10px}
h1{margin:0;font-size:20px;font-weight:600;letter-spacing:-.01em}
h2{margin:0 0 9px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
select,button{font:inherit;padding:6px 10px;background:var(--surface);color:var(--ink);border:1px solid var(--rule);border-radius:3px;cursor:pointer}
button:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair)}
.tile{background:var(--surface);padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.tile .l{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-size:25px;font-weight:600;line-height:1.05}
.tile .v small{font-size:12px;font-weight:500;color:var(--ink-2)}
.tile .n{font-size:12px;color:var(--muted)}

.walk{display:grid;grid-template-columns:repeat(auto-fit,minmax(232px,1fr));gap:10px}
.stop-card{background:var(--surface);border:1px solid var(--hair);border-left:3px solid var(--critical);padding:11px 13px;display:flex;flex-direction:column;gap:5px}
.stop-card h3{margin:0;font-size:16px;font-weight:600}
.stop-card .why{color:var(--ink-2);font-size:13px}
.stop-card .kv{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
.stop-card .kv b{color:var(--ink);font-weight:500;font-family:"IBM Plex Mono",monospace}
.stop-card.warn{border-left-color:var(--warning)}

.tbl-wrap{overflow-x:auto;border:1px solid var(--hair);background:var(--surface);max-height:74vh}
table{width:100%;border-collapse:collapse;min-width:1080px}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--hair);white-space:nowrap}
thead tr.grp th{border-bottom:1px solid var(--rule);color:var(--ink-2);text-align:center;font-size:11px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--surface);cursor:pointer;z-index:1}
thead tr.grp th{top:0;cursor:default}
thead tr.cols th{top:27px}
th.n,td.n{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
th[aria-sort="descending"],th[aria-sort="ascending"]{color:var(--ink)}
tbody tr:hover{background:var(--surface-2)}
tfoot td{font-weight:600;border-top:2px solid var(--rule);background:var(--surface-2)}
td.sep,th.sep{border-left:1px solid var(--hair)}
.bad{color:var(--critical);font-weight:600}
.note{color:var(--muted);font-size:12px;max-width:76ch}
</style>

<div class="wrap">
  <header>
    <h1>Обход цеха по сменам</h1>
    <div class="controls">
      <button id="prev">← смена</button>
      <select id="shift"></select>
      <button id="next">смена →</button>
    </div>
  </header>

  <section>
    <div class="tiles" id="tiles"></div>
  </section>

  <section>
    <h2>Куда идти в первую очередь</h2>
    <div class="walk" id="walk"></div>
    <p class="note">Отобраны станки с наибольшими потерями за смену. Указано, что именно их держало: обрывы утка, ворса, основы — или ожидание оператора, когда станок стоял, а к нему никто не подошёл.</p>
  </section>

  <section>
    <h2>Все станки за смену</h2>
    <div class="tbl-wrap">
      <table id="t">
        <thead>
          <tr class="grp">
            <th colspan="5"></th>
            <th colspan="3" class="sep">Уток</th>
            <th colspan="3" class="sep">Ворс (верхний навой)</th>
            <th colspan="3" class="sep">Основа (нижний навой)</th>
            <th colspan="3" class="sep">Прочее</th>
          </tr>
          <tr class="cols">
            <th data-k="loom">Станок</th>
            <th data-k="style">Артикул</th>
            <th class="n" data-k="eff">КПД</th>
            <th class="n" data-k="kpick">Тыс. уточин</th>
            <th class="n" data-k="stop">Простой, мин</th>
            <th class="n sep" data-k="weftC">шт</th>
            <th class="n" data-k="weftF">устранение, мин</th>
            <th class="n" data-k="weftM">MTTR, сек</th>
            <th class="n sep" data-k="topC">шт</th>
            <th class="n" data-k="topF">устранение, мин</th>
            <th class="n" data-k="topM">MTTR, сек</th>
            <th class="n sep" data-k="warpC">шт</th>
            <th class="n" data-k="warpF">устранение, мин</th>
            <th class="n" data-k="warpM">MTTR, сек</th>
            <th class="n sep" data-k="wait">ожидание, мин</th>
            <th class="n" data-k="manC">ручных</th>
            <th class="n" data-k="manT">ручные, мин</th>
          </tr>
        </thead>
        <tbody></tbody><tfoot></tfoot>
      </table>
    </div>
    <p class="note">«Устранение» — сколько времени заняла починка без учёта ожидания. «MTTR» — среднее время на один обрыв: по нему видно, быстро ли работает смена. «Ожидание» — простой станка до прихода человека.</p>
  </section>
</div>

<script>
const D = __DATA__;
const nf = (x,d=0) => x==null ? "—" : Number(x).toLocaleString("ru-RU",{minimumFractionDigits:d,maximumFractionDigits:d});
const shiftName = s => `${s.slice(0,10).replace(/\./g,"/")} · смена ${"ABC"[+s.slice(-1)]}`;
let idx = D.shifts.length - 1, sortK = "stop", sortD = -1;

const sel = document.getElementById("shift");
sel.innerHTML = D.shifts.map((s,i)=>`<option value="${i}">${shiftName(s.shift)}</option>`).join("");
sel.value = idx;
sel.onchange = () => { idx = +sel.value; render(); };
document.getElementById("prev").onclick = () => { idx = Math.max(0, idx-1); sel.value = idx; render(); };
document.getElementById("next").onclick = () => { idx = Math.min(D.shifts.length-1, idx+1); sel.value = idx; render(); };
document.querySelectorAll("#t thead tr.cols th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  sortD = (k === sortK) ? -sortD : -1;
  sortK = k; render();
});

const flat = r => ({
  loom: r.loom, style: r.style, eff: r.eff, kpick: r.picks/1000, stop: r.stop, run: r.run,
  weftC: r.weft[0], weftF: r.weft[1], weftM: r.weft[2],
  topC: r.top[0], topF: r.top[1], topM: r.top[2],
  warpC: r.warp[0], warpF: r.warp[1], warpM: r.warp[2],
  wait: r.wait, manC: r.manual[0], manT: r.manual[1],
});

function render() {
  const sh = D.shifts[idx];
  const rows = sh.rows.map(flat);
  const S = k => rows.reduce((a,r)=>a+r[k],0);
  const run = S("run"), stop = S("stop");
  const eff = run+stop ? 100*run/(run+stop) : 0;

  document.getElementById("tiles").innerHTML = [
    ["КПД смены", `${nf(eff,1)}<small> %</small>`, `${rows.length} станков в работе`],
    ["Выработка", `${nf(S("kpick"))}<small> тыс. уточин</small>`, "итог по цеху за смену"],
    ["Обрывы утка", nf(S("weftC")), `устранение ${nf(S("weftF"))} мин`],
    ["Обрывы ворса", nf(S("topC")), `устранение ${nf(S("topF"))} мин`],
    ["Обрывы основы", nf(S("warpC")), `устранение ${nf(S("warpF"))} мин`],
    ["Ожидание оператора", `${nf(S("wait"))}<small> мин</small>`, "станок стоял, никто не подошёл"],
  ].map(([l,v,n]) => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join("");

  // карточки обхода: три станка с наибольшим простоем
  const worst = [...rows].sort((a,b)=>b.stop-a.stop).slice(0,6);
  document.getElementById("walk").innerHTML = worst.map(r => {
    const parts = [["уток", r.weftF], ["ворс", r.topF], ["основа", r.warpF], ["ручные", r.manT], ["ожидание", r.wait]]
      .filter(p => p[1] > 0).sort((a,b)=>b[1]-a[1]);
    const top = parts[0];
    return `<div class="stop-card${r.eff >= 70 ? " warn" : ""}">
      <h3>${r.loom} <span style="font-weight:400;color:var(--ink-2);font-size:13px">${r.style}</span></h3>
      <div class="why">Главная потеря: <strong>${top ? top[0] : "—"}</strong>${top ? ` · ${nf(top[1])} мин` : ""}</div>
      <div class="kv"><span>КПД</span><b>${nf(r.eff,1)} %</b></div>
      <div class="kv"><span>простой</span><b>${nf(r.stop)} мин</b></div>
      <div class="kv"><span>уток / ворс / основа</span><b>${r.weftC} / ${r.topC} / ${r.warpC}</b></div>
      <div class="kv"><span>ожидание оператора</span><b>${nf(r.wait)} мин</b></div>
    </div>`;
  }).join("");

  rows.sort((a,b) => {
    const x = a[sortK], y = b[sortK];
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortD;
  });
  document.querySelectorAll("#t thead tr.cols th").forEach(th =>
    th.setAttribute("aria-sort", th.dataset.k===sortK ? (sortD<0?"descending":"ascending") : "none"));

  const maxStop = Math.max(...rows.map(r=>r.stop), 1);
  document.querySelector("#t tbody").innerHTML = rows.map(r => `
    <tr>
      <td><strong>${r.loom}</strong></td><td>${r.style}</td>
      <td class="n${r.eff<60?" bad":""}">${nf(r.eff,1)}</td>
      <td class="n">${nf(r.kpick)}</td>
      <td class="n${r.stop>maxStop*0.7?" bad":""}">${nf(r.stop)}</td>
      <td class="n sep">${nf(r.weftC)}</td><td class="n">${nf(r.weftF)}</td><td class="n">${nf(r.weftM)}</td>
      <td class="n sep">${nf(r.topC)}</td><td class="n">${nf(r.topF)}</td><td class="n">${nf(r.topM)}</td>
      <td class="n sep">${nf(r.warpC)}</td><td class="n">${nf(r.warpF)}</td><td class="n">${nf(r.warpM)}</td>
      <td class="n sep${r.wait>30?" bad":""}">${nf(r.wait)}</td>
      <td class="n">${nf(r.manC)}</td><td class="n">${nf(r.manT)}</td>
    </tr>`).join("");

  const mttr = (f,c) => c ? nf(S(f)*60/S(c)) : "—";
  document.querySelector("#t tfoot").innerHTML = `<tr>
    <td>Итого</td><td>${rows.length} станков</td>
    <td class="n">${nf(eff,1)}</td><td class="n">${nf(S("kpick"))}</td><td class="n">${nf(stop)}</td>
    <td class="n sep">${nf(S("weftC"))}</td><td class="n">${nf(S("weftF"))}</td><td class="n">${mttr("weftF","weftC")}</td>
    <td class="n sep">${nf(S("topC"))}</td><td class="n">${nf(S("topF"))}</td><td class="n">${mttr("topF","topC")}</td>
    <td class="n sep">${nf(S("warpC"))}</td><td class="n">${nf(S("warpF"))}</td><td class="n">${mttr("warpF","warpC")}</td>
    <td class="n sep">${nf(S("wait"))}</td><td class="n">${nf(S("manC"))}</td><td class="n">${nf(S("manT"))}</td></tr>`;
}

render();
</script>
"""

if __name__ == "__main__":
    build()
