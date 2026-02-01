# api2/tests/conftest.py
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ddjiback.settings')

# Sobrescribir configuración de cache para tests
from django.conf import settings

settings.CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}