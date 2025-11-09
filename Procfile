release: python manage.py createsuperuser --noinput --username=admin --email=admin@example.com
web: gunicorn backend.wsgi --bind 0.0.0.0:$PORT
