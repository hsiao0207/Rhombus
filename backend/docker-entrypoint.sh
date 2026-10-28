#!/bin/sh
# Prepare the database, then hand over to the container command (gunicorn).
set -e

python manage.py migrate --noinput
# Table backing the shared cache used for rate limiting (no-op if it exists).
python manage.py createcachetable

exec "$@"
