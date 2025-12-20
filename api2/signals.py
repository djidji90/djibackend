# api2/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()

@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    """
    Crear UserProfile automáticamente si el usuario es nuevo.
    Guardar UserProfile si ya existía.
    Evita errores si no existe.
    """
    if created:
        # Usuario nuevo: crear perfil
        UserProfile.objects.create(user=instance)
    else:
        # Usuario existente: intentar guardar perfil
        try:
            instance.profile.save()
        except UserProfile.DoesNotExist:
            # Si no existía perfil, crear uno
            UserProfile.objects.create(user=instance)
