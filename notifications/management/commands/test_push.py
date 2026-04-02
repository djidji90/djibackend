# notifications/management/commands/test_push.py
"""
Comando para probar notificaciones push.
Uso: python manage.py test_push --user=username --title="Test" --message="Hola"
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from notifications.services import NotificationService

User = get_user_model()


class Command(BaseCommand):
    help = 'Probar envío de notificaciones push'
    
    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, required=True, help='Username del usuario')
        parser.add_argument('--title', type=str, default='Test Push', help='Título')
        parser.add_argument('--message', type=str, default='Esta es una notificación de prueba', help='Mensaje')
        parser.add_argument('--type', type=str, default='system', help='Tipo de notificación')
    
    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options['user'])
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Usuario {options['user']} no encontrado"))
            return
        
        self.stdout.write(f"Enviando notificación a {user.email}")
        self.stdout.write(f"Título: {options['title']}")
        self.stdout.write(f"Mensaje: {options['message']}")
        
        notification = NotificationService.create_notification(
            user=user,
            notification_type=options['type'],
            title=options['title'],
            message=options['message'],
            metadata={'test': True, 'click_action': '/test'}
        )
        
        result = NotificationService.send_notification(notification, channels=['push', 'in_app'])
        
        self.stdout.write(f"Resultado: {result}")
        
        if result.get('push'):
            self.stdout.write(self.style.SUCCESS("✅ Push enviado correctamente"))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Push no enviado (sin dispositivos o error)"))