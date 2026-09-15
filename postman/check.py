"""Прогон коллекции Postman без Postman: те же запросы, тот же ключ из окружения.

    python check.py
"""
import json
import os
import re
import urllib.request as u

HERE = os.path.dirname(os.path.abspath(__file__))
C = json.load(open(os.path.join(HERE, "MES-1C.postman_collection.json"), encoding="utf-8"))
E = {v["key"]: v["value"] for v in json.load(open(os.path.join(
    HERE, "MES-local.postman_environment.json"), encoding="utf-8"))["values"]}
V = {**{v["key"]: v["value"] for v in C["variable"]}, **E}


def sub(s):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: V[m.group(1)], s)


for it in C["item"]:
    rq = it["request"]
    auth = rq.get("auth", C["auth"])
    h = {x["key"]: x["value"] for x in rq.get("header", [])}
    if auth["type"] == "bearer":
        h["Authorization"] = "Bearer " + sub(auth["bearer"][0]["value"])
    body = rq.get("body", {}).get("raw")
    req = u.Request(sub(rq["url"]["raw"]), body.encode("utf-8") if body else None, h,
                    method=rq["method"])
    try:
        r = u.urlopen(req, timeout=30)
        code, txt = r.status, r.read().decode()
    except u.HTTPError as e:
        code, txt = e.code, e.read().decode()
    j = json.loads(txt)
    print("%s: %s" % (it["name"], code))
    n = it["name"][0]
    if n == "2":
        print("   ", {k: j.get(k) for k in ("success", "cards", "yarns", "yarns_added", "looms",
                                            "message_id", "report_days", "error")})
        if j.get("success"):
            V["orderNumber"] = str(json.loads(body)["data"]["productionOrders"][0]["orderNumber"])
    elif n in "34":
        print("    найдено", j.get("count"), "| получено:", (j.get("received") or [])[:2])
        if j.get("count"):
            o = j["data"]["productionOrders"][0]
            print("    заказ", o.get("orderNumber"), "GSM", o.get("gsm"), "вес", o.get("weight"),
                  "компонентов", len(o["technologies"]["components"]))
    elif n in "56":
        print("   ", j)
