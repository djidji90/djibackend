# wallet/validators.py - VERSIÓN CORREGIDA
"""
Validadores personalizados para el sistema wallet.
"""
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Sum
from .constants import LIMITS


def validate_positive_amount(value):
    """Validar que el monto sea positivo"""
    try:
        amount = Decimal(str(value))
        if amount <= Decimal('0'):
            raise ValidationError(
                _('El monto debe ser mayor a cero'),
                code='invalid_amount'
            )
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            _('Monto inválido'),
            code='invalid_amount'
        )


def validate_min_deposit(value):
    """Validar monto mínimo de depósito"""
    try:
        amount = Decimal(str(value))
        if amount < LIMITS['MIN_DEPOSIT']:
            raise ValidationError(
                _(f'El depósito mínimo es {LIMITS["MIN_DEPOSIT"]} XAF'),
                code='min_deposit'
            )
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            _('Monto inválido'),
            code='invalid_amount'
        )


def validate_max_balance(value, wallet_balance=None):
    """Validar que no se exceda el balance máximo"""
    try:
        amount = Decimal(str(value))
        if wallet_balance is None:
            # Solo validar el monto individual
            if amount > LIMITS['MAX_BALANCE']:
                raise ValidationError(
                    _(f'El monto excede el balance máximo de {LIMITS["MAX_BALANCE"]} XAF'),
                    code='max_balance'
                )
        else:
            total = Decimal(str(wallet_balance)) + amount
            if total > LIMITS['MAX_BALANCE']:
                raise ValidationError(
                    _(f'El balance máximo es {LIMITS["MAX_BALANCE"]} XAF'),
                    code='max_balance'
                )
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            _('Monto inválido'),
            code='invalid_amount'
        )


def validate_currency(value):
    """Validar código de moneda"""
    valid_currencies = ['XAF', 'EUR', 'USD']
    if value not in valid_currencies:
        raise ValidationError(
            _(f'Moneda no soportada. Debe ser: {", ".join(valid_currencies)}'),
            code='invalid_currency'
        )


def validate_wallet_status(wallet):
    """Validar que el wallet esté activo"""
    if not wallet.is_active:
        raise ValidationError(
            _('La wallet está desactivada'),
            code='inactive_wallet'
        )


# wallet/validators.py - CORREGIR LA FUNCIÓN validate_daily_limit

def validate_daily_limit(wallet, amount, transaction_type):
    """Validar límites diarios con ventana de 24h REAL"""
    from django.utils import timezone
    from django.db.models import Sum
    from .models import Transaction  # ✅ ESTA LÍNEA YA DEBE EXISTIR, PERO VERIFICA
    
    try:
        # Ventana de 24 horas REAL
        last_24h = timezone.now() - timezone.timedelta(hours=24)
        
        daily_total = Transaction.objects.filter(  # ✅ Transaction debe estar importado
            wallet=wallet,
            transaction_type=transaction_type,
            created_at__gte=last_24h,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        new_total = abs(daily_total) + abs(Decimal(str(amount)))

        limit_key = f'MAX_DAILY_{transaction_type.upper()}'
        limit = LIMITS.get(limit_key, Decimal('999999.00'))

        if new_total > limit:
            raise ValidationError(
                _(f'Límite diario excedido. Máximo: {limit} XAF'),
                code='daily_limit'
            )

    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            _('Monto inválido'),
            code='invalid_amount'
        )