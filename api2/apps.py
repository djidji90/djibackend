# api2/apps.py
from django.apps import AppConfig

class Api2Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api2'

    def ready(self):
        import api2.signals  # Registrar señales