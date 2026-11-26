#!/usr/bin/env bash
# Анализ в локальном SonarQube (контейнер sonarqube, http://localhost:9000).
#   SONAR_TOKEN=squ_... bash scripts/sonar.sh
# Токен - пользовательский (My Account -> Security), только из окружения, в git не класть.
# Перед запуском (по желанию):
#   coverage run manage.py test && coverage xml -o coverage.xml     -> покрытие
#   bash scripts/mutation.sh <модуль> && python scripts/mutation_to_sonar.py .mutation/*.sqlite
#                                                                     -> выжившие мутанты как issues
# Сканер - docker-образ sonarsource/sonar-scanner-cli, сервер для него - host.docker.internal.
set -euo pipefail

: "${SONAR_TOKEN:?Задайте SONAR_TOKEN (пользовательский токен SonarQube)}"
host="${SONAR_HOST_URL:-http://host.docker.internal:9000}"

if ! curl -fs -m 5 "${host/host.docker.internal/localhost}/api/system/status" | grep -q '"UP"'; then
    echo "SonarQube не отвечает. Запустите: docker start sonarqube" >&2
    exit 2
fi

[ -f coverage.xml ] || echo "coverage.xml нет - анализ пойдёт без покрытия." >&2
[ -f .mutation/sonar-issues.json ] || { mkdir -p .mutation; echo '{"rules": [], "issues": []}' > .mutation/sonar-issues.json; }

# Git Bash на Windows: путь D:/... для docker -v и без автоконвертации MSYS.
src="$(pwd -W 2>/dev/null || pwd)"
MSYS_NO_PATHCONV=1 docker run --rm \
    -e SONAR_HOST_URL="$host" -e SONAR_TOKEN \
    -v "${src}:/usr/src" \
    sonarsource/sonar-scanner-cli
