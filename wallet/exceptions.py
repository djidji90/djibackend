# wallet/exceptions.py - VERSIÓN COMPLETA Y CORREGIDA
"""
Excepciones personalizadas para el sistema wallet.
VERSIÓN PRODUCCIÓN - Todas las excepciones necesarias.
"""
from .constants import ERROR_CODES


class WalletBaseException(Exception):
    """Excepción base del wallet"""
    status_code = 400
    default_detail = 'Error en el sistema wallet'
    default_code = 'wallet_error'
    
    def __init__(self, detail=None, code=None):
        self.detail = detail or self.default_detail
        self.code = code or self.default_code
        super().__init__(self.detail)


class InsufficientFundsError(WalletBaseException):
    """Saldo insuficiente"""
    status_code = 402
    default_detail = 'Saldo insuficiente'
    default_code = ERROR_CODES.get('INSUFFICIENT_FUNDS', 'ERR001')


class InvalidAmountError(WalletBaseException):
    """Monto inválido"""
    status_code = 400
    default_detail = 'Monto inválido'
    default_code = ERROR_CODES.get('INVALID_AMOUNT', 'ERR002')


class WalletNotFoundError(WalletBaseException):
    """Wallet no encontrada"""
    status_code = 404
    default_detail = 'Wallet no encontrada'
    default_code = ERROR_CODES.get('WALLET_NOT_FOUND', 'ERR003')


class HoldNotFoundError(WalletBaseException):
    """Hold no encontrado"""
    status_code = 404
    default_detail = 'Retención no encontrada'
    default_code = ERROR_CODES.get('HOLD_NOT_FOUND', 'ERR004')


class HoldAlreadyReleasedError(WalletBaseException):
    """Hold ya liberado"""
    status_code = 400
    default_detail = 'Esta retención ya fue liberada'
    default_code = ERROR_CODES.get('HOLD_ALREADY_RELEASED', 'ERR005')


class HoldNotReleasableError(WalletBaseException):
    """Hold no puede liberarse aún"""
    status_code = 400
    default_detail = 'Esta retención no puede liberarse aún'
    default_code = ERROR_CODES.get('HOLD_NOT_RELEASABLE', 'ERR006')


class PurchaseFailedError(WalletBaseException):
    """Error en compra"""
    status_code = 400
    default_detail = 'Error al procesar la compra'
    default_code = ERROR_CODES.get('PURCHASE_FAILED', 'ERR007')


class UnauthorizedWalletActionError(WalletBaseException):
    """Acción no autorizada en wallet"""
    status_code = 403
    default_detail = 'No tienes permiso para realizar esta acción'
    default_code = ERROR_CODES.get('UNAUTHORIZED', 'ERR008')


class LimitExceededError(WalletBaseException):
    """Límite excedido"""
    status_code = 429
    default_detail = 'Has excedido el límite permitido'
    default_code = ERROR_CODES.get('LIMIT_EXCEEDED', 'ERR009')


class CurrencyMismatchError(WalletBaseException):
    """Moneda no coincide"""
    status_code = 400
    default_detail = 'La moneda de la transacción no coincide con la wallet'
    default_code = ERROR_CODES.get('CURRENCY_MISMATCH', 'ERR010')


# ============================================================
# EXCEPCIONES ADICIONALES (FALTANTES)
# ============================================================

class DuplicateTransactionError(WalletBaseException):
    """Transacción duplicada (idempotencia)"""
    status_code = 409
    default_detail = 'Esta transacción ya fue procesada'
    default_code = 'duplicate_transaction'


class ConcurrentModificationError(WalletBaseException):
    """Error de concurrencia - recurso modificado simultáneamente"""
    status_code = 409
    default_detail = 'El recurso fue modificado concurrentemente. Reintente.'
    default_code = 'concurrent_modification'


class InconsistentStateError(WalletBaseException):
    """Estado inconsistente detectado"""
    status_code = 500
    default_detail = 'Estado inconsistente detectado en el sistema'
    default_code = 'inconsistent_state'