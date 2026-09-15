"""Загрузка технологических карт из 1С (CreateOrUpdateProductionOrderAPI) в базу.

Разбор общий с приложением (`_app/integration.py`): тот же код принимает заказы,
которые 1С присылает в API (/api/v1/production-orders) или которые сборщик
забирает по расписанию. Этот скрипт — для разовой загрузки из файла.

Из ответа 1С берём то, чего нет в Toyota FACT: размер, PPT (weftPerOneRow),
число панелей (numberLines), дизайн (productCode), плотность и пряжу по типам
с номерами лотов, а также привязку изделия к станкам (workCenters).

    python tech_cards.py --file "апи_dpa (4).txt"
    python tech_cards.py --url http://1c-server/api/production-orders --token "Basic ..."
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "_app"))

import integration   # noqa: E402
import storage       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="tech_cards.json", help="файл с ответом 1С")
    ap.add_argument("--url", help="адрес API 1С (если есть)")
    ap.add_argument("--token", help="значение заголовка Authorization")
    ap.add_argument("--no-orders", action="store_true", help="только техкарты, план не трогать")
    args = ap.parse_args()

    storage.prepare()
    if args.url:
        r = integration.pull_1c({"url": args.url, "token": args.token})
    else:
        path = args.file if os.path.isabs(args.file) else os.path.join(HERE, args.file)
        payload = json.load(io.open(path, encoding="utf-8"))
        r = integration.load_production_orders(payload, who="файл " + os.path.basename(path),
                                               make_orders=not args.no_orders)

    print(f"Загружено изделий: {r['cards']}, компонентов пряжи: {r['yarns']}, "
          f"привязок к станкам: {r['looms']}, связок кода ткани: {r['cloth_mapped']}")
    if r.get("plan"):
        print("В план:", r["plan"])
    if r["no_spec"]:
        print(f"\nБез спецификации в 1С ({len(r['no_spec'])}) — пряжа и лоты не заполнятся:")
        for c in r["no_spec"]:
            print(f"  {c}")


if __name__ == "__main__":
    main()
