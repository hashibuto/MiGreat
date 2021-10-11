FROM python:3.10.0-alpine3.14

RUN \
 apk add --no-cache \
  postgresql-libs \
  gcc \
  g++ \
  musl-dev \
  postgresql-dev

COPY . /app/lib/migreat
WORKDIR /app/lib/migreat
RUN ls -la

COPY ./migreat/example/test/requirements.txt /app/test/requirements.txt
WORKDIR /app/test
RUN pip install -r ./requirements.txt

COPY ./migreat/example/test /app/test

CMD [ "migreat",  "upgrade" ]
