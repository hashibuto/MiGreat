#!/bin/sh

migreat upgrade --verbose
echo "Waiting for the containers to stabilize"
sleep 5

export PGPASSWORD=$SVC_PASSWORD
psql \
  -d postgres \
  -U $SVC_USERNAME \
  -h postgres \
  -c "INSERT INTO svc1.shared (name) VALUES ('hello')"
