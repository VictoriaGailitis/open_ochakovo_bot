#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py bootstrap_miniapp
python manage.py collectstatic --noinput
exec gunicorn backoffice.wsgi:application --bind 0.0.0.0:3001 --workers 3 --timeout 90 --access-logfile /dev/null
