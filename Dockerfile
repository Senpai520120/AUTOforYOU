FROM ubuntu:latest
LABEL authors="kirit"

ENTRYPOINT ["top", "-b"]