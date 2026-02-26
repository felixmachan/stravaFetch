#!/usr/bin/env bash
set -e
python manage.py migrate
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='admin@local').exists() or User.objects.create_superuser('admin@local','admin@local','admin')"
python manage.py runserver 0.0.0.0:8000
