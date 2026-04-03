# wallet/monitoring/signals.py
"""
Señales para actualizar métricas automáticamente
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from ..models import Wallet, Transaction, Hold
from .metrics import TOTAL_BALANCE, PENDING_HOLDS_TOTAL


@receiver(post_save, sender=Transaction)
def update_balance_metrics(sender, instance, created, **kwargs):
    """Actualizar métricas de balance cuando hay transacciones"""
    from django.db.models import Sum
    
    total = Wallet.objects.aggregate(total=Sum('available_balance'))['total'] or 0
    TOTAL_BALANCE.labels(currency='XAF').set(float(total))


@receiver([post_save, post_delete], sender=Hold)
def update_holds_metrics(sender, instance, **kwargs):
    """Actualizar métricas de holds pendientes"""
    pending = Hold.objects.filter(is_released=False).count()
    PENDING_HOLDS_TOTAL.set(pending)