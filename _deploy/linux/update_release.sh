#!/bin/sh
# Установка нового выпуска MES на Linux из архива `git archive`.
#
#   sudo sh update_release.sh /tmp/fact-mes-<коммит>.tar.gz <коммит>
#
# 1. Копия баз до установки (миграции новых версий только добавляют таблицы,
#    но откат должен быть возможен).
# 2. Код — в /opt/fact-mes/releases/<коммит>; ссылки на данные берутся из
#    текущего выпуска как есть (shop.db, fact.db, config.json, run, logs, …).
# 3. Переключение ссылки current, перезапуск службы, проверка /api/health.
# Откат: sudo ln -sfn <прежний выпуск> /opt/fact-mes/current && sudo systemctl restart fact-mes
set -eu

TAR=${1:?архив выпуска}
COMMIT=${2:?коммит}
BASE=/opt/fact-mes
REL=$BASE/releases/$COMMIT
CUR=$(readlink -f "$BASE/current")

[ "$(id -u)" = 0 ] || { echo "запустите через sudo"; exit 1; }
[ -e "$REL" ] && { echo "выпуск $REL уже есть"; exit 1; }

echo "== копия баз"
systemctl start fact-mes-backup.service
ls -1dt /var/backups/fact-mes/* | head -1

echo "== код $COMMIT"
mkdir -p "$REL"
tar -xzf "$TAR" -C "$REL"
cd "$CUR"
find . -type l | while read -r link; do
    mkdir -p "$REL/$(dirname "$link")"
    ln -sfn "$(readlink "$link")" "$REL/$link"
done
chown -R root:root "$REL"
find "$REL" -type l -exec chown -h root:root {} +

echo "== переключение: было $CUR"
ln -sfn "$REL" "$BASE/current.new"
mv -Tf "$BASE/current.new" "$BASE/current"
systemctl restart fact-mes
sleep 6
systemctl --no-pager --lines=0 status fact-mes || true
# Файл — для systemd (значения без кавычек, с пробелами): как shell его не читаем.
env_val() { sed -n "s/^$1=//p" /etc/fact-mes/service.env | tail -1 | tr -d '"'; }
curl -fsS "http://$(env_val MES_HOST):$(env_val MES_PORT)/api/health" && echo && echo "== готово: $COMMIT (откат — на $CUR)"
