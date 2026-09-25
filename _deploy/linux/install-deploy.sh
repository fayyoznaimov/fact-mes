#!/bin/sh
# Один раз: команда установки MES без пароля sudo.
#
#   sudo sh _deploy/linux/install-deploy.sh
#
# Кладёт fact-mes-deploy в /usr/local/sbin (владелец root, пользователь не
# изменит) и разрешает parisahome запускать без пароля только его.
# Убрать: sudo rm /etc/sudoers.d/fact-mes-deploy /usr/local/sbin/fact-mes-deploy
set -eu
[ "$(id -u)" = 0 ] || { echo "запустите через sudo"; exit 1; }
HERE=$(dirname "$(readlink -f "$0")")

install -o root -g root -m 0755 "$HERE/fact-mes-deploy" /usr/local/sbin/fact-mes-deploy

RULE=$(mktemp)
echo 'parisahome ALL=(root) NOPASSWD: /usr/local/sbin/fact-mes-deploy' > "$RULE"
visudo -cf "$RULE"
install -o root -g root -m 0440 "$RULE" /etc/sudoers.d/fact-mes-deploy
rm -f "$RULE"
echo "== готово: sudo fact-mes-deploy <коммит> | rollback — без пароля"
