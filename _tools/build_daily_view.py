"""Дашборд производственного отчёта: тот же лист, что в Excel, с выбором дня.

Читает таблицу report_daily из fact.db и кладёт все дни в одну HTML-страницу.

    python build_daily_view.py
"""
import io
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "fact.db")
OUT = os.path.join(HERE, "daily_report.html")

FIELDS = ["sr", "size_cm", "rpm", "ppt", "weight_kg", "panels", "prod100_kg", "design", "gsm",
          "pile_count", "ground_count", "loto", "weft1", "weft2", "weft3", "weft4", "loom",
          "eff_a", "eff_b", "eff_c", "eff_total",
          "pile_a", "pile_b", "pile_c", "pile_total",
          "weft_a", "weft_b", "weft_c", "weft_total",
          "ground_a", "ground_b", "ground_c", "ground_total",
          "other_a", "other_b", "other_c", "other_total",
          "picks", "achieved_kg"]


def build():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    days = [r[0] for r in db.execute("SELECT DISTINCT day FROM report_daily ORDER BY day")]
    data = []
    for day in days:
        rows = [[r[f] for f in FIELDS] for r in db.execute(
            "SELECT * FROM report_daily WHERE day=? ORDER BY sr", (day,))]
        if rows:
            data.append({"day": day, "rows": rows})
    db.close()

    payload = {"fields": FIELDS, "days": data}
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    io.open(OUT, "w", encoding="utf-8").write(html)
    print(f"Готово: {OUT}")
    print(f"  дней: {len(data)} ({data[0]['day']} … {data[-1]['day']}), "
          f"строк: {sum(len(d['rows']) for d in data)}, размер {os.path.getsize(OUT)/1024:.0f} КБ")


TEMPLATE = r"""<meta charset="utf-8">
<title>Производственный отчёт по дням</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --page:#f4f3ef; --surface:#fcfcfb; --surface-2:#efeee9; --ink:#14130f; --ink-2:#52514e;
  --muted:#898781; --hair:#e1e0d9; --rule:#c3c2b7; --accent:#2a78d6;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --critical:#d03b3b;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#232321; --ink:#fff; --ink-2:#c3c2b7;
  --muted:#898781; --hair:#2c2c2a; --rule:#383835; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
}}
:root[data-theme="dark"]{
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#232321; --ink:#fff; --ink-2:#c3c2b7;
  --muted:#898781; --hair:#2c2c2a; --rule:#383835; --accent:#3987e5;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font-family:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif;font-size:14px;line-height:1.45}
.wrap{max-width:1400px;margin:0 auto;padding:16px 12px 56px;display:flex;flex-direction:column;gap:16px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:10px}
h1{margin:0;font-size:19px;font-weight:600;letter-spacing:-.01em}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
select,button{font:inherit;padding:6px 10px;background:var(--surface);color:var(--ink);border:1px solid var(--rule);border-radius:3px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair)}
.tile{background:var(--surface);padding:11px 13px;display:flex;flex-direction:column;gap:2px}
.tile .l{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-size:24px;font-weight:600;line-height:1.05}
.tile .v small{font-size:12px;font-weight:500;color:var(--ink-2)}
.tbl-wrap{overflow:auto;border:1px solid var(--hair);background:var(--surface);max-height:78vh}
table{border-collapse:collapse;min-width:100%;font-size:13px}
th,td{padding:5px 7px;text-align:left;border-bottom:1px solid var(--hair);white-space:nowrap}
thead tr.grp th{position:sticky;top:0;z-index:2;background:var(--surface-2);text-align:center;font-size:11px;color:var(--ink-2);border-bottom:1px solid var(--rule);text-transform:uppercase;letter-spacing:.04em}
thead tr.cols th{position:sticky;top:26px;z-index:2;background:var(--surface);font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);font-weight:600;cursor:pointer}
th.n,td.n{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
th[aria-sort="descending"],th[aria-sort="ascending"]{color:var(--ink)}
td.sep,th.sep{border-left:1px solid var(--rule)}
tbody tr:hover{background:var(--surface-2)}
tfoot td{position:sticky;bottom:0;font-weight:600;background:var(--surface-2);border-top:2px solid var(--rule)}
.bad{color:var(--critical);font-weight:600}
.note{color:var(--muted);font-size:12px;max-width:78ch}
</style>

<div class="wrap">
  <header>
    <h1>Производственный отчёт</h1>
    <div class="controls">
      <button id="prev">← день</button>
      <select id="day"></select>
      <button id="next">день →</button>
      <button class="primary" id="csv">Скачать CSV</button>
    </div>
  </header>

  <div class="tiles" id="tiles"></div>

  <div class="tbl-wrap">
    <table id="t">
      <thead>
        <tr class="grp">
          <th colspan="17"></th>
          <th colspan="4" class="sep">Efficiency</th>
          <th colspan="4" class="sep">Pile (Vors) — ворс</th>
          <th colspan="4" class="sep">Weft (Utog) — уток</th>
          <th colspan="4" class="sep">Ground (Karenoy) — основа</th>
          <th colspan="4" class="sep">Other stops</th>
        </tr>
        <tr class="cols">
          <th class="n" data-k="0">Sr#</th><th class="n" data-k="1">Size cm</th><th class="n" data-k="2">RPM</th>
          <th class="n" data-k="3">PPT</th><th class="n" data-k="4">P Pc Wt Kg</th><th class="n" data-k="5"># panels</th>
          <th class="n" data-k="6">100% Prod Kg</th><th data-k="7">MODEL</th><th class="n" data-k="8">GSM</th>
          <th data-k="9">Pile Count</th><th data-k="10">Ground Count</th><th data-k="11">LOTO</th>
          <th data-k="12">WEFT 1</th><th data-k="13">WEFT 2</th><th data-k="14">WEFT 3</th><th data-k="15">WEFT 4</th>
          <th data-k="16">L#</th>
          <th class="n sep" data-k="17">A</th><th class="n" data-k="18">B</th><th class="n" data-k="19">C</th><th class="n" data-k="20">Total</th>
          <th class="n sep" data-k="21">A</th><th class="n" data-k="22">B</th><th class="n" data-k="23">C</th><th class="n" data-k="24">Total</th>
          <th class="n sep" data-k="25">A</th><th class="n" data-k="26">B</th><th class="n" data-k="27">C</th><th class="n" data-k="28">Total</th>
          <th class="n sep" data-k="29">A</th><th class="n" data-k="30">B</th><th class="n" data-k="31">C</th><th class="n" data-k="32">Total</th>
          <th class="n sep" data-k="33">A</th><th class="n" data-k="34">B</th><th class="n" data-k="35">C</th><th class="n" data-k="36">Total</th>
        </tr>
      </thead>
      <tbody></tbody>
      <tfoot></tfoot>
    </table>
  </div>
  <p class="note">Колонка MODEL пока не заполняется — артикул из кода ткани определяется неверно. PPT, вес штуки, число панелей и номера пряжи — заправочные данные артикула, в Toyota FACT их нет. Всё остальное посчитано по данным станков.</p>
</div>

<script>
const D = __DATA__;
const F = {}; D.fields.forEach((f,i)=>F[f]=i);
const nf = (x,d=0) => (x==null || x==="") ? "" : Number(x).toLocaleString("ru-RU",{minimumFractionDigits:d,maximumFractionDigits:d});
// Открываем последний ЗАВЕРШЁННЫЙ день: у текущего смена C ещё не прошла,
// и итоги по нему выглядят провалом, хотя станки работали нормально.
const complete = i => {
  const rows = D.days[i].rows;
  if (!rows.length) return false;
  const withC = rows.filter(r => r[D.fields.indexOf("eff_c")] != null).length;
  return withC >= rows.length / 2;
};
let idx = (() => { for (let i = D.days.length-1; i >= 0; i--) if (complete(i)) return i;
                   return D.days.length-1; })();
let sortK = null, sortD = 1;

const sel = document.getElementById("day");
sel.innerHTML = D.days.map((d,i)=>`<option value="${i}">${d.day.replace(/\./g,"/")}</option>`).join("");
sel.value = idx;
sel.onchange = () => { idx = +sel.value; render(); };
document.getElementById("prev").onclick = () => { idx = Math.max(0, idx-1); sel.value = idx; render(); };
document.getElementById("next").onclick = () => { idx = Math.min(D.days.length-1, idx+1); sel.value = idx; render(); };
document.querySelectorAll("#t thead tr.cols th").forEach(th => th.onclick = () => {
  const k = +th.dataset.k;
  sortD = (k === sortK) ? -sortD : 1;
  sortK = k; render();
});

let current = [];

function render() {
  const day = D.days[idx];
  let rows = day.rows.slice();
  if (sortK != null) {
    rows.sort((a,b) => {
      const x = a[sortK], y = b[sortK];
      if (x == null) return 1; if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortD;
    });
  }
  current = rows;
  document.querySelectorAll("#t thead tr.cols th").forEach(th =>
    th.setAttribute("aria-sort", +th.dataset.k===sortK ? (sortD<0?"descending":"ascending") : "none"));

  const S = i => rows.reduce((a,r)=>a+(Number(r[i])||0), 0);
  const avg = i => { const v = rows.map(r=>r[i]).filter(x=>x!=null && x!=="");
    return v.length ? v.reduce((a,b)=>a+Number(b),0)/v.length : 0; };
  const prod100 = S(F.prod100_kg), achieved = S(F.achieved_kg);

  document.getElementById("tiles").innerHTML = [
    ["100% Production", `${nf(prod100)}<small> кг</small>`],
    ["Achieved Production", `${nf(achieved)}<small> кг</small>`],
    ["Production Efficiency", prod100 ? `${nf(100*achieved/prod100,1)}<small> %</small>` : "—"],
    ["Avg RPM", nf(avg(F.rpm))],
    ["Всего пиков", `${nf(S(F.picks)/1e6,2)}<small> млн</small>`],
    ["Станков", String(rows.length)],
  ].map(([l,v]) => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("");

  const cell = (r,i,dec) => {
    const sep = [17,21,25,29,33].includes(i) ? " sep" : "";
    const isNum = i !== 7 && i < 9 || i >= 17 || [8].includes(i);
    const v = r[i];
    if (i === 16 || (i >= 9 && i <= 15) || i === 7)
      return `<td class="${sep}">${v == null ? "" : v}</td>`;
    const bad = (i === 20 && v != null && v < 60) ? " bad" : "";
    return `<td class="n${sep}${bad}">${nf(v, dec||0)}</td>`;
  };
  document.querySelector("#t tbody").innerHTML = rows.map(r => "<tr>" +
    [0,1,2,3].map(i=>cell(r,i)).join("") +
    cell(r,4,3) + cell(r,5) + cell(r,6,1) + cell(r,7) + cell(r,8) +
    [9,10,11,12,13,14,15,16].map(i=>cell(r,i)).join("") +
    [17,18,19].map(i=>cell(r,i)).join("") + cell(r,20,1) +
    [21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36].map(i=>cell(r,i)).join("") +
    "</tr>").join("");

  const grp = (name, keep) => {
    const s = rows.filter(r => keep(String(r[F.loom] || "")));
    if (!s.length) return "";
    const SS = i => s.reduce((a,r)=>a+(Number(r[i])||0),0);
    const AA = i => { const v = s.map(r=>r[i]).filter(x=>x!=null && x!=="");
      return v.length ? v.reduce((a,b)=>a+Number(b),0)/v.length : 0; };
    return `<tr><td colspan="6">${name}</td><td class="n">${nf(SS(F.prod100_kg))}</td>
      <td colspan="9">${s.length} станков</td><td class="n">${nf(SS(F.achieved_kg))} кг</td>
      <td class="n sep">${nf(AA(17),1)}</td><td class="n">${nf(AA(18),1)}</td><td class="n">${nf(AA(19),1)}</td><td class="n">${nf(AA(20),1)}</td>
      <td class="n sep">${nf(SS(21))}</td><td class="n">${nf(SS(22))}</td><td class="n">${nf(SS(23))}</td><td class="n">${nf(SS(24))}</td>
      <td class="n sep">${nf(SS(25))}</td><td class="n">${nf(SS(26))}</td><td class="n">${nf(SS(27))}</td><td class="n">${nf(SS(28))}</td>
      <td class="n sep">${nf(SS(29))}</td><td class="n">${nf(SS(30))}</td><td class="n">${nf(SS(31))}</td><td class="n">${nf(SS(32))}</td>
      <td class="n sep">${nf(SS(33))}</td><td class="n">${nf(SS(34))}</td><td class="n">${nf(SS(35))}</td><td class="n">${nf(SS(36))}</td></tr>`;
  };
  document.querySelector("#t tfoot").innerHTML =
    grp("ALL TOTAL", () => true) +
    grp("DOBBY TOTAL (D)", l => l[0] === "D") +
    grp("JACQUARD TOTAL (J)", l => l[0] === "J");
}

let downloads = null;
if (window.claude && typeof claude.use === "function") {
  claude.use("downloads").then(d => { downloads = d; }).catch(() => {});
}
document.getElementById("csv").onclick = async () => {
  const head = [...document.querySelectorAll("#t thead tr.cols th")].map(th => th.textContent);
  const csv = "﻿" + [head.join(";"), ...current.map(r =>
    r.slice(0, 37).map(v => v == null ? "" : String(v).replace(".", ",")).join(";"))].join("\r\n");
  const name = `Отчёт_${D.days[idx].day.replace(/\./g,"-")}.csv`;
  if (downloads) {
    try { await downloads.save({ filename: name, data: csv }); } catch (e) {}
    return;
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type:"text/csv"}));
  a.download = name; document.body.appendChild(a); a.click(); a.remove();
};

render();
</script>
"""

if __name__ == "__main__":
    build()
