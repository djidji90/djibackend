# wallet/throttles.py - VERSIÓN COMPLETA
"""
Rate limiting para el sistema wallet
"""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class WalletOperationThrottle(UserRateThrottle):
    """
    Límite de operaciones por usuario
    10 operaciones por minuto es razonable
    """
    rate = '10/min'


class SensitiveOperationThrottle(UserRateThrottle):
    """
    Para operaciones sensibles (depósitos grandes, retiros)
    3 por minuto
    """
    rate = '3/min'


class WithdrawalThrottle(UserRateThrottle):
    """
    Retiros - más restrictivo
    2 por hora
    """
    rate = '2/hour'


class DepositThrottle(UserRateThrottle):
    """
    Depósitos - restrictivo para evitar spam
    5 por minuto
    """
    rate = '5/min'


class AnonymousWalletThrottle(AnonRateThrottle):
    """
    Límite para usuarios no autenticados
    (por ejemplo, consulta de precios)
    """
    rate = '20/hour'