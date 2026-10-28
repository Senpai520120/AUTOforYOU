# Сервис резервных копий (задача 7.4). Мажорная версия pg_dump совпадает с сервером: образ тот же, что у db
# в docker-compose.yml (при смене версии db менять и здесь, иначе pg_dump откажется работать).
FROM postgres:18.4-alpine

RUN apk add --no-cache aws-cli gnupg tzdata

COPY rotate.sh backup.sh loop.sh healthcheck.sh restore-inner.sh fetch-remote.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/rotate.sh /usr/local/bin/backup.sh /usr/local/bin/loop.sh \
        /usr/local/bin/healthcheck.sh /usr/local/bin/restore-inner.sh /usr/local/bin/fetch-remote.sh

# Базовый образ запускает сервер Postgres - здесь он не нужен.
ENTRYPOINT []
CMD ["/usr/local/bin/loop.sh"]
