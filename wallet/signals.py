# wallet/signals.py
"""
Señales para automatizar la creación y gestión de wallets.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
import logging

from .models import Wallet
from .constants import COUNTRY_CURRENCY_MAP

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_wallet(sender, instance, created, **kwargs):
    """
    SIG-01: Crear wallet automáticamente al crear usuario.
    """
    if not created:
        return
    
    try:
        # Determinar currency basado en país
        currency = 'XAF'
        if hasattr(instance, 'country'):
            currency = COUNTRY_CURRENCY_MAP.get(instance.country, 'XAF')
        
        # Crear wallet
        wallet = Wallet.objects.create(
            user=instance,
            currency=currency,
            is_active=True
        )
        
        logger.info(
            f"✅ SIG-01: Wallet creado automáticamente",
            extra={
                'user_id': instance.id,
                'email': instance.email,
                'currency': currency
            }
        )
        
    except Exception as e:
        logger.error(
            f"❌ SIG-01: Error creando wallet para {instance.email}: {str(e)}",
            exc_info=True
        )


@receiver(pre_save, sender=settings.AUTH_USER_MODEL)
def update_wallet_currency_on_country_change(sender, instance, **kwargs):
    """
    SIG-02: Actualizar currency si el usuario cambia de país.
    """
    if not instance.pk:
        return
    
    try:
        old_user = sender.objects.get(pk=instance.pk)
        
        if hasattr(old_user, 'country') and hasattr(instance, 'country'):
            if old_user.country != instance.country:
                new_currency = COUNTRY_CURRENCY_MAP.get(instance.country, 'XAF')
                
                try:
                    wallet = Wallet.objects.get(user=instance)
                    if wallet.currency != new_currency:
                        old_currency = wallet.currency
                        wallet.currency = new_currency
                        wallet.save(update_fields=['currency', 'updated_at'])
                        
                        logger.info(
                            f"🔄 SIG-02: Currency actualizada",
                            extra={
                                'user_id': instance.id,
                                'old_currency': old_currency,
                                'new_currency': new_currency,
                                'old_country': old_user.country,
                                'new_country': instance.country
                            }
                        )
                except Wallet.DoesNotExist:
                    pass
                    
    except sender.DoesNotExist:
        pass
    except Exception as e:
        logger.error(
            f"❌ SIG-02: Error actualizando currency: {str(e)}",
            exc_info=True
        )


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def handle_user_activation(sender, instance, **kwargs):
    """
    SIG-03: Sincronizar activación/desactivación de usuario con wallet.
    """
    if not instance.pk:
        return
    
    try:
        wallet = Wallet.objects.get(user=instance)
        
        # Si el estado no coincide, sincronizar
        if wallet.is_active != instance.is_active:
            wallet.is_active = instance.is_active
            wallet.save(update_fields=['is_active', 'updated_at'])
            
            action = "activado" if instance.is_active else "desactivado"
            logger.info(
                f"🔄 SIG-03: Wallet {action} por cambio de usuario",
                extra={
                    'user_id': instance.id,
                    'is_active': instance.is_active
                }
            )
            
    except Wallet.DoesNotExist:
        pass
    except Exception as e:
        logger.error(
            f"❌ SIG-03: Error sincronizando activación: {str(e)}",
            exc_info=True
        )


@receiver(post_save, sender='wallet.Transaction')
def log_transaction_created(sender, instance, created, **kwargs):
    """
    SIG-04: Log cada transacción para auditoría.
    """
    if created:
        logger.info(
            f"📊 SIG-04: Transacción creada",
            extra={
                'reference': instance.reference,
                'type': instance.transaction_type,
                'amount': float(instance.amount),
                'wallet_id': instance.wallet_id,
                'user_id': instance.wallet.user_id
            }
        )


@receiver(post_save, sender='wallet.Hold')
def log_hold_created(sender, instance, created, **kwargs):
    """
    SIG-05: Log cada hold creado.
    """
    if created:
        logger.info(
            f"📌 SIG-05: Hold creado",
            extra={
                'hold_id': instance.id,
                'artist_id': instance.artist_id,
                'amount': float(instance.amount),
                'release_date': instance.release_date.isoformat(),
                'transaction': instance.transaction.reference
            }
        )