# wallet/throttles.py - VERSIÓN PARA PRUEBAS (LÍMITES ALTOS)

from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class WalletOperationThrottle(UserRateThrottle):
    """
    Límite de operaciones por usuario
    """
    rate = '100/minute'  # ← AUMENTADO (antes 10/min)


class SensitiveOperationThrottle(UserRateThrottle):
    """
    Para operaciones sensibles (depósitos grandes, retiros, compras)
    """
    rate = '30/minute'  # ← AUMENTADO (antes 3/min)


class WithdrawalThrottle(UserRateThrottle):
    """
    Retiros - más restrictivo
    """
    rate = '10/hour'  # ← AUMENTADO (antes 2/hour)


class DepositThrottle(UserRateThrottle):
    """
    Depósitos - restrictivo para evitar spam
    """
    rate = '20/minute'  # ← AUMENTADO (antes 5/min)


class AnonymousWalletThrottle(AnonRateThrottle):
    """
    Límite para usuarios no autenticados
    """
    rate = '100/hour'  # ← AUMENTADO (antes 20/hour)