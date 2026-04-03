# wallet/management/commands/setup_monitoring.py
"""
Comando para configurar monitoreo
Uso: python manage.py setup_monitoring
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Configurar monitoreo para el sistema wallet'
    
    def handle(self, *args, **options):
        self.stdout.write("\n📊 Configurando monitoreo...")
        
        # Verificar configuración de Prometheus
        if 'django_prometheus' not in settings.INSTALLED_APPS:
            self.stdout.write(self.style.WARNING(
                "⚠️ django_prometheus no está instalado. Ejecuta: pip install django-prometheus"
            ))
        
        # Verificar Sentry
        sentry_dsn = os.environ.get('SENTRY_DSN')
        if sentry_dsn:
            self.stdout.write(self.style.SUCCESS("✅ Sentry configurado"))
        else:
            self.stdout.write(self.style.WARNING(
                "⚠️ Sentry no configurado. Agrega SENTRY_DSN a .env"
            ))
        
        # Crear directorio de logs
        logs_dir = os.path.join(settings.BASE_DIR, 'logs')
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            self.stdout.write(f"✅ Directorio de logs creado: {logs_dir}")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Monitoreo configurado"))
        self.stdout.write("\n📋 Comandos útiles:")
        self.stdout.write("   locust -f wallet/load_tests/locustfile.py  # Tests de carga")
        self.stdout.write("   python manage.py run_load_tests --url=http://localhost:8000 --users=100")
        self.stdout.write("   curl http://localhost:8000/metrics  # Ver métricas Prometheus")