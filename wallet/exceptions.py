# wallet/exceptions.py
"""
Excepciones personalizadas para el sistema wallet.
"""
from rest_framework.exceptions import APIException
from django.utils.translation import gettext_lazy as _
from .constants import ERROR_CODES


class WalletBaseException(APIException):
    """Excepción base del wallet"""
    status_code = 400
    default_detail = 'Error en el sistema wallet'
    default_code = 'wallet_error'
    
    def __init__(self, detail=None, code=None):
        self.detail = detail or self.default_detail
        self.code = code or self.default_code
        super().__init__(detail, code)


class InsufficientFundsError(WalletBaseException):
    """Saldo insuficiente"""
    status_code = 402
    default_detail = 'Saldo insuficiente'
    default_code = ERROR_CODES['INSUFFICIENT_FUNDS']


class InvalidAmountError(WalletBaseException):
    """Monto inválido"""
    status_code = 400
    default_detail = 'Monto inválido'
    default_code = ERROR_CODES['INVALID_AMOUNT']


class WalletNotFoundError(WalletBaseException):
    """Wallet no encontrada"""
    status_code = 404
    default_detail = 'Wallet no encontrada'
    default_code = ERROR_CODES['WALLET_NOT_FOUND']


class HoldNotFoundError(WalletBaseException):
    """Hold no encontrado"""
    status_code = 404
    default_detail = 'Retención no encontrada'
    default_code = ERROR_CODES['HOLD_NOT_FOUND']


class HoldAlreadyReleasedError(WalletBaseException):
    """Hold ya liberado"""
    status_code = 400
    default_detail = 'Esta retención ya fue liberada'
    default_code = ERROR_CODES['HOLD_ALREADY_RELEASED']


class HoldNotReleasableError(WalletBaseException):
    """Hold no puede liberarse aún"""
    status_code = 400
    default_detail = 'Esta retención no puede liberarse aún'
    default_code = ERROR_CODES['HOLD_NOT_RELEASABLE']


class PurchaseFailedError(WalletBaseException):
    """Error en compra"""
    status_code = 400
    default_detail = 'Error al procesar la compra'
    default_code = ERROR_CODES['PURCHASE_FAILED']


class UnauthorizedWalletActionError(WalletBaseException):
    """Acción no autorizada en wallet"""
    status_code = 403
    default_detail = 'No tienes permiso para realizar esta acción'
    default_code = ERROR_CODES['UNAUTHORIZED']


class LimitExceededError(WalletBaseException):
    """Límite excedido"""
    status_code = 429
    default_detail = 'Has excedido el límite permitido'
    default_code = ERROR_CODES['LIMIT_EXCEEDED']


class CurrencyMismatchError(WalletBaseException):
    """Moneda no coincide"""
    status_code = 400
    default_detail = 'La moneda de la transacción no coincide con la wallet'
    default_code = ERROR_CODES['CURRENCY_MISMATCH']