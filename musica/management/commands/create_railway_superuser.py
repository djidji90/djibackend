# tu_app/management/commands/create_railway_superuser.py
import os
import time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import OperationalError, ProgrammingError

class Command(BaseCommand):
    help = 'Crea superusuario automáticamente en Railway al hacer deploy'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-retries',
            type=int,
            default=5,
            help='Número máximo de reintentos si la BD no está lista'
        )
        parser.add_argument(
            '--retry-delay',
            type=int,
            default=5,
            help='Segundos entre reintentos'
        )

    def handle(self, *args, **options):
        User = get_user_model()
        max_retries = options['max_retries']
        retry_delay = options['retry_delay']

        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        admin_password = os.environ.get('ADMIN_PASSWORD')

        if not admin_password:
            self.stdout.write(self.style.WARNING(
                '⚠️ ADMIN_PASSWORD no configurada. Saltando creación de superusuario.'
            ))
            return

        for attempt in range(max_retries):
            try:
                if not User.objects.filter(username=admin_username).exists():
                    try:
                        # Intento con campos estándar
                        User.objects.create_superuser(
                            username=admin_username,
                            email=admin_email,
                            password=admin_password
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f'✅ Superusuario "{admin_username}" creado exitosamente.'
                        ))
                    except TypeError:
                        # Si tu Custom User tiene campos adicionales, agrega aquí
                        User.objects.create_superuser(
                            username=admin_username,
                            email=admin_email,
                            password=admin_password,
                            # first_name=os.environ.get('ADMIN_FIRST_NAME', 'Admin'),
                            # last_name=os.environ.get('ADMIN_LAST_NAME', 'User'),
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f'✅ Superusuario Custom User "{admin_username}" creado exitosamente.'
                        ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'⚠️ Superusuario "{admin_username}" ya existe.'
                    ))
                break  # Salir si tuvo éxito

            except (OperationalError, ProgrammingError) as e:
                if attempt < max_retries - 1:
                    self.stdout.write(self.style.WARNING(
                        f'⚠️ BD no lista (intento {attempt+1}/{max_retries}). Reintentando en {retry_delay}s...'
                    ))
                    time.sleep(retry_delay)
                else:
                    self.stdout.write(self.style.ERROR(
                        f'❌ No se pudo crear superusuario después de {max_retries} intentos: {e}'
                    ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'❌ Error inesperado creando superusuario: {e}'
                ))
                break
