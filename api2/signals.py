from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()

@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """
    Garantiza que cada usuario tenga un UserProfile,
    y evita errores si aún no existe.
    """
    
    # Si el usuario fue creado, crear el perfil
    if created:
        UserProfile.objects.create(user=instance)
        return

    # Si el usuario ya existía, intentar obtener el perfil
    try:
        profile = instance.profile
    except UserProfile.DoesNotExist:
        # Crearlo si no existe
        profile = UserProfile.objects.create(user=instance)

    # Guardar perfil
    profile.save()
