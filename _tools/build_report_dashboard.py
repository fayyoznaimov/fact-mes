"""Дашборд сменного производственного отчёта: одна страница на все дни.

Данные — из локального зеркала FACT и базы fact.db, заправочные данные артикула —
из artikul_ref.json.

    python build_report_dashboard.py              # последние 30 дней
    python build_report_dashboard.py --days 60
"""
import argparse
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
OUT = os.path.join(HERE, "report_dashboard.html")

norm_cloth = lambda c: "CLOTH|" + re.sub(r"[^A-Z0-9]", "", (c or "").replace("%20", "").upper())


def cloth_map(shift):
    """Код ткани по станкам за смену — из зеркала."""
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


def build(days_limit):
    ref = json.load(io.open(os.path.join(HERE, "artikul_ref.json"), encoding="utf-8"))
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    all_days = [r[0] for r in db.execute(
        "SELECT DISTINCT substr(shift,1,10) d FROM shift_loom ORDER BY d DESC")][:days_limit]
    all_days.reverse()

    days = []
    for day in all_days:
        rows = defaultdict(dict)
        for r in db.execute("SELECT * FROM shift_loom WHERE shift LIKE ?", (day + ".%",)):
            rows[r["loom"]]["ABC"[int(r["shift"][-1])]] = r
        if not rows:
            continue
        clothes = {}
        for i in range(3):
            clothes.update({k: v for k, v in cloth_map(f"{day}.{i}").items() if v})

        looms, worked = [], 0
        for loom, sh in sorted(rows.items()):
            g = lambda L, k: (sh[L][k] if L in sh else 0)
            cloth = clothes.get(loom, "")
            size, design, gsm = parse_cloth(cloth)
            art = ref.get(norm_cloth(cloth), {})
            # Смена считается отработанной, если станок в ней запускался. Незавершённую
            # смену (например, текущую) в средние включать нельзя — иначе ноль тянет их вниз.
            worked_shifts = [L for L in "ABC" if g(L, "run_min") > 5]
            eff = [round(g(L, "effic_pct")) if L in worked_shifts else None for L in "ABC"]
            done = [e for e in eff if e is not None]
            picks = sum(g(L, "product_kpick") for L in "ABC") * 1000
            rpms = [g(L, "rpm") for L in "ABC" if g(L, "rpm")]
            rpm = round(sum(rpms) / len(rpms)) if rpms else 0
            ppt, wt, pn = art.get("ppt"), art.get("weight_kg"), art.get("panels")
            # 100% выработка — на фактически отработанные смены (по 480 мин), не на сутки.
            kg100 = (round(pn * wt * (rpm * 480 * len(worked_shifts) / ppt), 1)
                     if (ppt and wt and pn and rpm and worked_shifts) else None)
            kg = round(pn * wt * (picks / ppt), 1) if (ppt and wt and pn) else None
            if worked_shifts:
                worked += 1
            looms.append({
                "loom": loom, "design": design or art.get("design_report") or "",
                # Плотность: справочник главнее — его ведёт человек, а хвост кода ткани
                # иногда служебный (у D1 из «3050X7360» читается 736).
                "size": size, "gsm": art.get("gsm") or (gsm if gsm and 200 <= gsm <= 900 else None),
                "rpm": rpm, "eff": eff, "shifts": len(worked_shifts),
                "effT": round(sum(done) / len(done), 1) if done else 0,
                "pile": [g(L, "warp_top_ct") for L in "ABC"],
                "weft": [g(L, "weft_ct") for L in "ABC"],
                "ground": [g(L, "warp_ct") for L in "ABC"],
                "other": [g(L, "unselect_ct") for L in "ABC"],
                "mpick": round(picks / 1e6, 2), "kg": kg, "kg100": kg100,
                "hasArt": bool(art),
            })

        shift_eff = []
        for i, L in enumerate("ABC"):
            run = sum(r[L]["run_min"] for r in rows.values() if L in r)
            cal = sum(r[L]["run_min"] + r[L]["stop_min"] for r in rows.values() if L in r)
            # Смены, которой ещё не было, в отчёте быть не должно — пишем «нет данных».
            shift_eff.append(round(100 * run / cal, 1) if cal > 60 else None)

        days.append({"day": day, "looms": looms, "shiftEff": shift_eff, "worked": worked})

    data = {"days": days, "generated": days[-1]["day"] if days else ""}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    io.open(OUT, "w", encoding="utf-8").write(html)

    last = days[-1]
    kg = sum(l["kg"] for l in last["looms"] if l["kg"])
    print(f"Готово: {OUT}")
    print(f"  дней: {len(days)} ({days[0]['day']} … {last['day']}), станков: {len(last['looms'])}")
    print(f"  последний день: КПД смен {last['shiftEff']}, выработка {kg:.0f} кг")
    no_art = [l["loom"] for l in last["looms"] if not l["hasArt"]]
    if no_art:
        print(f"  без артикула в справочнике ({len(no_art)}): {', '.join(no_art)}")


TEMPLATE = r"""<meta charset="utf-8">
<title>Сменный отчёт цеха</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --page:#f4f3ef; --surface:#fcfcfb; --surface-2:#efeee9; --ink:#14130f; --ink-2:#52514e;
  --muted:#898781; --hair:#e1e0d9; --rule:#c3c2b7; --accent:#2a78d6;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --good:#0ca30c; --warn:#fab219; --critical:#d03b3b;
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
.mono{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 64px;display:flex;flex-direction:column;gap:22px}
header{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:12px}
h1{margin:0;font-size:20px;font-weight:600;letter-spacing:-.01em}
.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
select,button.nav{font:inherit;padding:6px 10px;background:var(--surface);color:var(--ink);border:1px solid var(--rule);border-radius:3px;cursor:pointer}
select:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
h2{margin:0 0 10px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;background:var(--hair);border:1px solid var(--hair)}
.tile{background:var(--surface);padding:12px 14px;display:flex;flex-direction:column;gap:2px}
.tile .l{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-size:25px;font-weight:600;line-height:1.05}
.tile .v small{font-size:12px;font-weight:500;color:var(--ink-2)}
.tile .n{font-size:12px;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--hair);padding:14px}
svg{display:block;width:100%;height:auto;overflow:visible}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink-2);margin-top:8px}
.legend b{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px}
.tbl-wrap{overflow-x:auto;border:1px solid var(--hair);background:var(--surface)}
table{width:100%;border-collapse:collapse;min-width:940px}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--hair);white-space:nowrap}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600;cursor:pointer;position:sticky;top:0;background:var(--surface)}
th.n,td.n{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
th[aria-sort]{color:var(--ink)}
tbody tr:hover{background:var(--surface-2)}
tbody tr:last-child td{border-bottom:none}
tfoot td{font-weight:600;border-top:2px solid var(--rule);background:var(--surface-2)}
.bar{display:inline-block;height:7px;background:var(--s1);vertical-align:middle;margin-right:6px}
.bar.low{background:var(--critical)}
.warnrow td:first-child::after{content:" ●";color:var(--warn)}
.note{color:var(--muted);font-size:12px;max-width:72ch}
.tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--rule);padding:6px 9px;font-size:12px;box-shadow:0 3px 12px rgba(0,0,0,.15);opacity:0;transition:opacity .1s;z-index:9;white-space:nowrap}
.tip.on{opacity:1}
</style>

<div class="wrap">
  <header>
    <h1>Сменный отчёт цеха</h1>
    <div class="controls">
      <button class="nav" id="prev">← день</button>
      <select id="day"></select>
      <button class="nav" id="next">день →</button>
    </div>
  </header>

  <section>
    <div class="tiles" id="tiles"></div>
    <p class="note" id="note"></p>
  </section>

  <section>
    <h2>КПД по сменам, последние дни</h2>
    <div class="card">
      <figure id="trend" style="margin:0"></figure>
      <div class="legend">
        <span><b style="background:var(--s1)"></b>смена A</span>
        <span><b style="background:var(--s2)"></b>смена B</span>
        <span><b style="background:var(--s3)"></b>смена C</span>
      </div>
    </div>
  </section>

  <section>
    <h2>Станки за выбранный день</h2>
    <div class="tbl-wrap">
      <table id="t">
        <thead><tr>
          <th data-k="loom">Станок</th><th data-k="design">Дизайн</th><th class="n" data-k="size">Размер</th>
          <th class="n" data-k="gsm">Плотн.</th><th class="n" data-k="rpm">Об/мин</th>
          <th class="n" data-k="effA">КПД A</th><th class="n" data-k="effB">КПД B</th><th class="n" data-k="effC">КПД C</th>
          <th class="n" data-k="effT">КПД</th>
          <th class="n" data-k="pile">Ворс</th><th class="n" data-k="weft">Уток</th>
          <th class="n" data-k="ground">Грунт</th><th class="n" data-k="other">Прочие</th>
          <th class="n" data-k="mpick">Млн уточин</th><th class="n" data-k="kg">Кг</th>
        </tr></thead>
        <tbody></tbody>
        <tfoot></tfoot>
      </table>
    </div>
    <p class="note">Ворс — обрывы верхнего навоя (vors), грунт — обрывы основы (karenoy), прочие — ручные и прочие остановы. Жёлтая точка у станка: артикула нет в справочнике, килограммы не посчитаны. Столбцы сортируются по щелчку.</p>
  </section>
</div>
<div class="tip" id="tip"></div>

<script>
const D = __DATA__;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const nf = (x, d = 0) => (x == null ? "—" : Number(x).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d }));
const sum = (a, k) => a.reduce((s, x) => s + (k ? (x[k] || 0) : (x || 0)), 0);
const tip = document.getElementById("tip");
const showTip = (h, e) => { tip.innerHTML = h; tip.classList.add("on");
  tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px";
  tip.style.top = (e.clientY - tip.offsetHeight - 10) + "px"; };
const hideTip = () => tip.classList.remove("on");

let idx = D.days.length - 1, sortKey = "weft", sortDir = -1;

const sel = document.getElementById("day");
sel.innerHTML = D.days.map((d, i) => `<option value="${i}">${d.day.replace(/\./g, "/")}</option>`).join("");
sel.value = idx;
sel.onchange = () => { idx = +sel.value; render(); };
document.getElementById("prev").onclick = () => { idx = Math.max(0, idx - 1); sel.value = idx; render(); };
document.getElementById("next").onclick = () => { idx = Math.min(D.days.length - 1, idx + 1); sel.value = idx; render(); };
document.querySelectorAll("#t thead th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  sortDir = (k === sortKey) ? -sortDir : -1;
  sortKey = k; render();
});

function render() {
  const d = D.days[idx];
  const looms = d.looms;
  const kg = sum(looms.filter(l => l.kg), "kg");
  const kg100 = sum(looms.filter(l => l.kg100), "kg100");
  const run = looms.length ? (sum(looms, "effT") / looms.length) : 0;

  const fs = v => v == null ? "нет" : nf(v, 1);
  const shiftsDone = d.shiftEff.filter(v => v != null).length;
  document.getElementById("tiles").innerHTML = [
    ["КПД за сутки", `${nf(run,1)}<small> %</small>`, `A ${fs(d.shiftEff[0])} · B ${fs(d.shiftEff[1])} · C ${fs(d.shiftEff[2])}`],
    ["Выработка", `${nf(kg)}<small> кг</small>`, kg100 ? `из ${nf(kg100)} кг при 100%` : "нет данных артикула"],
    ["Эффективность", kg100 ? `${nf(100*kg/kg100,1)}<small> %</small>` : "—", "факт к теоретической"],
    ["Обрывы утка", nf(sum(looms.map(l => sum(l.weft)))), "за сутки, все станки"],
    ["Ворс + грунт", nf(sum(looms.map(l => sum(l.pile) + sum(l.ground)))), "обрывы навоев"],
    ["Работало станков", `${d.worked}<small> / ${looms.length}</small>`, "хотя бы одна смена"],
  ].map(([l, v, n]) => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join("");

  const noArt = looms.filter(l => !l.hasArt).length;
  document.getElementById("note").textContent = noArt
    ? `Килограммы посчитаны по ${looms.length - noArt} станкам из ${looms.length}: у ${noArt} артикул отсутствует в справочнике заправочных данных.`
    : "Заправочные данные найдены по всем станкам.";

  trend();

  const key = l => ({ loom: l.loom, design: l.design, size: l.size || 0, gsm: l.gsm || 0, rpm: l.rpm,
    effA: l.eff[0], effB: l.eff[1], effC: l.eff[2], effT: l.effT, pile: sum(l.pile), weft: sum(l.weft),
    ground: sum(l.ground), other: sum(l.other), mpick: l.mpick, kg: l.kg || 0 }[sortKey]);
  const rows = [...looms].sort((a, b) => {
    const x = key(a), y = key(b);
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortDir;
  });
  document.querySelectorAll("#t thead th").forEach(th =>
    th.setAttribute("aria-sort", th.dataset.k === sortKey ? (sortDir < 0 ? "descending" : "ascending") : "none"));

  document.querySelector("#t tbody").innerHTML = rows.map(l => `
    <tr class="${l.hasArt ? "" : "warnrow"}">
      <td><strong>${l.loom}</strong></td><td>${l.design || "—"}</td>
      <td class="n">${l.size ? l.size + " см" : "—"}</td><td class="n">${nf(l.gsm)}</td><td class="n">${nf(l.rpm)}</td>
      <td class="n">${l.eff[0]}</td><td class="n">${l.eff[1]}</td><td class="n">${l.eff[2]}</td>
      <td class="n"><span class="bar${l.effT < 60 ? " low" : ""}" style="width:${Math.max(2, l.effT * 0.5)}px"></span>${nf(l.effT,1)}</td>
      <td class="n">${sum(l.pile)}</td><td class="n">${sum(l.weft)}</td><td class="n">${sum(l.ground)}</td><td class="n">${sum(l.other)}</td>
      <td class="n">${nf(l.mpick,2)}</td><td class="n">${nf(l.kg,1)}</td>
    </tr>`).join("");

  const grp = (name, f) => {
    const s = looms.filter(l => f(l.loom));
    if (!s.length) return "";
    return `<tr><td colspan="5">${name} · ${s.length} станков</td>
      <td class="n">${nf(sum(s.map(l => l.eff[0]))/s.length,1)}</td>
      <td class="n">${nf(sum(s.map(l => l.eff[1]))/s.length,1)}</td>
      <td class="n">${nf(sum(s.map(l => l.eff[2]))/s.length,1)}</td>
      <td class="n">${nf(sum(s,"effT")/s.length,1)}</td>
      <td class="n">${nf(sum(s.map(l => sum(l.pile))))}</td>
      <td class="n">${nf(sum(s.map(l => sum(l.weft))))}</td>
      <td class="n">${nf(sum(s.map(l => sum(l.ground))))}</td>
      <td class="n">${nf(sum(s.map(l => sum(l.other))))}</td>
      <td class="n">${nf(sum(s,"mpick"),2)}</td>
      <td class="n">${nf(sum(s.filter(l => l.kg),"kg"),1)}</td></tr>`;
  };
  document.querySelector("#t tfoot").innerHTML =
    grp("Весь цех", () => true) + grp("Махровые (D)", l => l[0] === "D") + grp("Жаккардовые (J)", l => l[0] === "J");
}

function trend() {
  const data = D.days.slice(-21);
  const W = 1000, H = 210, L = 36, R = 10, T = 10, B = 26;
  const x = i => L + i * (W - L - R) / Math.max(1, data.length - 1);
  const y = v => T + (1 - v / 100) * (H - T - B);
  const series = [0, 1, 2].map(s => ({ color: css(`--s${s + 1}`), pts: data.map(d => d.shiftEff[s]) }));
  const grid = [0, 50, 100].map(v =>
    `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="${css("--hair")}"/>
     <text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="${css("--muted")}">${v}</text>`).join("");
  const paths = series.map(s => `<path d="${s.pts.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("")}"
     fill="none" stroke="${s.color}" stroke-width="2"/>`).join("");
  const ticks = data.map((d, i) => i % Math.ceil(data.length / 7) === 0
    ? `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" font-size="10" fill="${css("--muted")}">${d.day.slice(5).replace(".", "/")}</text>` : "").join("");
  const cur = `<line x1="${x(data.findIndex(d => d.day === D.days[idx].day))}" x2="${x(data.findIndex(d => d.day === D.days[idx].day))}"
     y1="${T}" y2="${H - B}" stroke="${css("--rule")}" stroke-dasharray="0"/>`;
  document.getElementById("trend").innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="КПД по сменам за последние дни">${grid}${ticks}${data.some(d => d.day === D.days[idx].day) ? cur : ""}${paths}<g id="hit"></g></svg>`;
  const g = document.getElementById("hit");
  data.forEach((d, i) => {
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("x", x(i) - (W - L - R) / data.length / 2); r.setAttribute("y", T);
    r.setAttribute("width", (W - L - R) / data.length); r.setAttribute("height", H - T - B);
    r.setAttribute("fill", "transparent");
    r.onmousemove = e => showTip(`<b>${d.day}</b><br>A ${d.shiftEff[0]}% · B ${d.shiftEff[1]}% · C ${d.shiftEff[2]}%`, e);
    r.onmouseleave = hideTip;
    r.onclick = () => { idx = D.days.indexOf(d); sel.value = idx; render(); };
    g.appendChild(r);
  });
}

render();
</script>
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    build(ap.parse_args().days)
