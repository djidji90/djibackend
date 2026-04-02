# notifications/management/commands/cleanup_notifications.py
"""
Comando para limpiar notificaciones antiguas.
Uso: python manage.py cleanup_notifications --days 90 --read-only
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Limpia notificaciones antiguas'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Eliminar notificaciones más antiguas que N días'
        )
        parser.add_argument(
            '--read-only',
            action='store_true',
            help='Eliminar solo notificaciones leídas'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular eliminación sin borrar'
        )
    
    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        
        queryset = Notification.objects.filter(created_at__lt=cutoff)
        
        if options['read_only']:
            queryset = queryset.filter(read=True)
            self.stdout.write(f"Eliminando notificaciones leídas anteriores a {options['days']} días")
        else:
            self.stdout.write(f"Eliminando todas las notificaciones anteriores a {options['days']} días")
        
        count = queryset.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("✅ No hay notificaciones para eliminar"))
            return
        
        self.stdout.write(f"📊 Se eliminarán {count} notificaciones")
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("⚠️ Modo dry-run - No se eliminaron notificaciones"))
            return
        
        queryset.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ {count} notificaciones eliminadas")
        )