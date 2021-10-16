FROM python:3.10.0-alpine3.14

RUN \
 apk add --no-cache \
  postgresql-libs \
  gcc \
  g++ \
  musl-dev \
  postgresql-dev \
  postgresql-client

COPY . /app/lib/migreat
WORKDIR /app/lib/migreat

COPY ./migreat/example/svc2/requirements.txt /app/svc/requirements.txt
WORKDIR /app/svc
RUN pip install -r ./requirements.txt

COPY ./migreat/example/svc2 /app/svc

CMD [ "./start.sh" ]
