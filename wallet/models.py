# wallet/models.py - COMPLETO PARA PRODUCCIÓN
"""
Modelos del sistema wallet - VERSIÓN PRODUCCIÓN REAL
Diseñado para robustez, concurrencia y consistencia financiera.
"""
import secrets
import logging
from decimal import Decimal, InvalidOperation
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.db.models import F, Sum, Q, CheckConstraint

from .constants import (
    TRANSACTION_TYPES, TRANSACTION_STATUS, HOLD_REASONS,
    CURRENCIES, LIMITS, COMMISSIONS
)
from .validators import (
    validate_positive_amount, validate_currency, validate_min_deposit
)

logger = logging.getLogger(__name__)


class Wallet(models.Model):
    """
    Monedero principal del usuario.
    
    Los campos de balance son CACHÉ - la verdad está en Transaction.
    Siempre usar WalletService para modificar.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet',
        verbose_name='Usuario'
    )

    # Saldos (caché)
    available_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Saldo disponible',
        help_text='Saldo que puede gastar ahora'
    )

    pending_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Saldo pendiente',
        help_text='Saldo retenido (esperando liberación a artista)'
    )

    # Totales históricos (nunca decrecen)
    total_deposited = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Total depositado'
    )

    total_spent = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Total gastado'
    )

    total_withdrawn = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Total retirado (artistas)'
    )

    currency = models.CharField(
        max_length=3,
        choices=CURRENCIES,
        default='XAF',
        validators=[validate_currency],
        verbose_name='Moneda'
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Si está inactivo, no se pueden realizar transacciones'
    )

    custom_daily_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Límite diario personalizado'
    )

    # Versionado para optimistic locking (opcional)
    version = models.PositiveIntegerField(
        default=0,
        verbose_name='Versión',
        help_text='Para control de concurrencia'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación',
        db_index=True
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    class Meta:
        verbose_name = 'Monedero'
        verbose_name_plural = 'Monederos'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['available_balance']),
            models.Index(fields=['created_at']),
            models.Index(fields=['currency']),
        ]
        constraints = [
            CheckConstraint(
                check=models.Q(available_balance__gte=0),
                name='wallet_available_balance_non_negative'
            ),
            CheckConstraint(
                check=models.Q(pending_balance__gte=0),
                name='wallet_pending_balance_non_negative'
            ),
            CheckConstraint(
                check=models.Q(total_deposited__gte=0),
                name='wallet_total_deposited_non_negative'
            ),
            CheckConstraint(
                check=models.Q(total_spent__gte=0),
                name='wallet_total_spent_non_negative'
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.available_balance} {self.currency}"

    @property
    def total_balance(self):
        return self.available_balance + self.pending_balance

    @property
    def has_funds(self):
        return self.total_balance > 0

    @property
    def can_spend(self):
        return self.is_active and self.available_balance > 0

    @property
    def daily_limit(self):
        return self.custom_daily_limit or LIMITS['MAX_DAILY_PURCHASE']

    def can_afford(self, amount):
        try:
            return self.available_balance >= Decimal(str(amount))
        except (ValueError, TypeError, InvalidOperation):
            return False

    def get_balance_data(self):
        """Obtener datos crudos del balance (sin formateo)"""
        return {
            'available': self.available_balance,
            'pending': self.pending_balance,
            'total': self.total_balance,
            'currency': self.currency,
            'total_deposited': self.total_deposited,
            'total_spent': self.total_spent,
            'total_withdrawn': self.total_withdrawn,
        }

    def get_transactions(self, limit=50, transaction_type=None):
        qs = self.transactions.all()
        if transaction_type:
            qs = qs.filter(transaction_type=transaction_type)
        return qs.select_related('wallet')[:limit]

    def get_pending_holds(self):
        from .models import Hold
        return Hold.objects.filter(
            transaction__wallet=self,
            is_released=False
        ).select_related('artist')


class Transaction(models.Model):
    """
    Registro inmutable de TODAS las transacciones.
    Esta es la FUENTE DE VERDAD del sistema.
    """
    reference = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        verbose_name='Referencia',
        db_index=True
    )

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='Monedero'
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('-999999.00'))],
        db_index=True,
        verbose_name='Monto'
    )

    balance_before = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Saldo anterior'
    )

    balance_after = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Saldo posterior'
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
        verbose_name='Tipo',
        db_index=True
    )

    status = models.CharField(
        max_length=20,
        choices=TRANSACTION_STATUS,
        default='completed',
        verbose_name='Estado',
        db_index=True
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadatos',
        help_text='Estructura esperada: {"song_id": int, "artist_id": int, ...}'
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Descripción'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_transactions',
        verbose_name='Creado por'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación',
        db_index=True
    )

    class Meta:
        verbose_name = 'Transacción'
        verbose_name_plural = 'Transacciones'
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['reference']),
            models.Index(fields=['created_by']),
            models.Index(fields=['created_at']),  # Para consultas temporales
            models.Index(fields=['wallet', 'transaction_type', 'created_at']),
        ]
        constraints = [
            CheckConstraint(
                check=models.Q(balance_after=models.F('balance_before') + models.F('amount')),
                name='transaction_balance_consistency'
            ),
            CheckConstraint(
                check=models.Q(balance_after__gte=0),
                name='transaction_balance_non_negative'
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.reference} - {self.transaction_type} {sign}{self.amount}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"TX{secrets.token_hex(8).upper()}"
        
        if self.balance_after != self.balance_before + self.amount:
            raise ValueError(
                f"Inconsistencia contable: balance_after ({self.balance_after}) != "
                f"balance_before ({self.balance_before}) + amount ({self.amount})"
            )
        
        super().save(*args, **kwargs)

    @property
    def is_income(self):
        return self.amount > 0

    @property
    def is_expense(self):
        return self.amount < 0

    @property
    def absolute_amount(self):
        return abs(self.amount)

    @property
    def formatted_amount(self):
        sign = '+' if self.amount > 0 else '-'
        return f"{sign} {self.absolute_amount:,.0f} {self.wallet.currency}"


class Hold(models.Model):
    """Retención (escrow) de fondos para artistas."""
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name='hold',
        verbose_name='Transacción'
    )

    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='holds',
        verbose_name='Artista',
        db_index=True
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Monto retenido'
    )

    release_days = models.PositiveIntegerField(
        default=LIMITS['HOLD_DAYS'],
        verbose_name='Días para liberación'
    )

    release_date = models.DateTimeField(
        verbose_name='Fecha de liberación',
        db_index=True
    )

    is_released = models.BooleanField(
        default=False,
        verbose_name='¿Liberado?',
        db_index=True
    )

    released_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha liberación'
    )

    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='released_holds',
        verbose_name='Liberado por'
    )

    reason = models.CharField(
        max_length=50,
        choices=HOLD_REASONS,
        default='song_purchase',
        verbose_name='Motivo'
    )

    notes = models.TextField(
        max_length=500,
        blank=True,
        verbose_name='Notas'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación',
        db_index=True
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    class Meta:
        verbose_name = 'Retención'
        verbose_name_plural = 'Retenciones'
        indexes = [
            models.Index(fields=['artist', 'is_released']),
            models.Index(fields=['release_date', 'is_released']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            CheckConstraint(
                check=models.Q(amount__gt=0),
                name='hold_amount_positive'
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        status = "Liberado" if self.is_released else f"Retenido hasta {self.release_date.strftime('%d/%m/%Y')}"
        return f"{self.artist.email} - {self.amount} XAF - {status}"

    def save(self, *args, **kwargs):
        if not self.release_date:
            self.release_date = timezone.now() + timezone.timedelta(days=self.release_days)
        super().save(*args, **kwargs)

    @property
    def can_release(self):
        if self.is_released:
            return False
        return timezone.now() >= self.release_date

    @property
    def days_until_release(self):
        if self.is_released:
            return 0
        delta = self.release_date - timezone.now()
        return max(0, delta.days)

    @property
    def is_overdue(self):
        if self.is_released:
            return False
        return timezone.now() > self.release_date


class DepositCode(models.Model):
    """Códigos de recarga física."""
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Código',
        db_index=True
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[validate_positive_amount, validate_min_deposit],
        verbose_name='Monto'
    )

    currency = models.CharField(
        max_length=3,
        choices=CURRENCIES,
        default='XAF',
        verbose_name='Moneda'
    )

    is_used = models.BooleanField(
        default=False,
        verbose_name='¿Usado?',
        db_index=True
    )

    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_codes',
        verbose_name='Usado por'
    )

    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha uso'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_codes',
        verbose_name='Creado por'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )

    expires_at = models.DateTimeField(
        verbose_name='Fecha expiración'
    )

    notes = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Notas'
    )

    class Meta:
        verbose_name = 'Código de recarga'
        verbose_name_plural = 'Códigos de recarga'
        indexes = [
            models.Index(fields=['code', 'is_used']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        status = "Usado" if self.is_used else "Activo"
        return f"{self.code} - {self.amount} {self.currency} - {status}"

    @property
    def is_valid(self):
        return (not self.is_used and timezone.now() <= self.expires_at)

    def mark_as_used(self, user):
        """Marcar código como usado de forma ATÓMICA."""
        from django.db import transaction
        
        with transaction.atomic():
            code = DepositCode.objects.select_for_update().get(id=self.id)
            if code.is_used:
                raise ValueError("El código ya ha sido usado")
            
            code.is_used = True
            code.used_by = user
            code.used_at = timezone.now()
            code.save(update_fields=['is_used', 'used_by', 'used_at'])


class IdempotencyKey(models.Model):
    """Registro de idempotencia en BD - ROBUSTO"""
    key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name='Clave idempotente'
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='idempotency_keys'
    )
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.CASCADE,
        related_name='idempotency_record'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    
    class Meta:
        verbose_name = 'Registro de idempotencia'
        verbose_name_plural = 'Registros de idempotencia'
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['wallet', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.key} -> {self.transaction.reference}"


class AuditLog(models.Model):
    """Registro de auditoría - SIMPLE Y EFECTIVO"""
    
    ACTION_CHOICES = [
        ('DEPOSIT', 'Depósito'),
        ('PURCHASE', 'Compra'),
        ('RELEASE', 'Liberación'),
        ('WITHDRAWAL', 'Retiro'),
        ('REDEEM_CODE', 'Canje de código'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=50)  # 'wallet', 'transaction', 'hold'
    entity_id = models.IntegerField()
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True) 
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    class Meta:
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['action', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} - {self.user} - {self.created_at}"


class SuspiciousActivity(models.Model):
    """Registro de actividad sospechosa"""
    
    ACTIVITY_TYPES = [
        ('high_frequency', 'Alta frecuencia'),
        ('unusual_amount', 'Monto inusual'),
        ('rapid_withdrawal', 'Retiro rápido'),
        ('multiple_failed', 'Múltiples fallos'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='suspicious_activities'
    )
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='suspicious_activities'
    )
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    details = models.JSONField(default=dict)
    is_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_activities'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        verbose_name = 'Actividad sospechosa'
        verbose_name_plural = 'Actividades sospechosas'
        indexes = [
            models.Index(fields=['user', 'is_reviewed']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.activity_type} - {self.created_at}"


class PhysicalLocation(models.Model):
    """Ubicación física donde se pueden realizar recargas."""
    name = models.CharField(max_length=200, verbose_name='Nombre del local')
    address = models.TextField(verbose_name='Dirección')
    city = models.CharField(max_length=100, verbose_name='Ciudad')
    country = models.CharField(
        max_length=2, default='GQ',
        choices=[('GQ', 'Guinea Ecuatorial'), ('ES', 'España'), ('FR', 'Francia'), ('US', 'Estados Unidos')],
        verbose_name='País'
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name='Teléfono')
    email = models.EmailField(blank=True, verbose_name='Correo electrónico')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    opening_hours = models.JSONField(default=dict, blank=True)
    coordinates = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ubicación física'
        verbose_name_plural = 'Ubicaciones físicas'
        indexes = [
            models.Index(fields=['city', 'country']),
            models.Index(fields=['is_active']),
        ]
        ordering = ['city', 'name']

    def __str__(self):
        return f"{self.name} - {self.city}, {self.country}"


class Agent(models.Model):
    """Agente autorizado para realizar recargas físicas."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='agent_profile', verbose_name='Usuario'
    )
    location = models.ForeignKey(
        PhysicalLocation, on_delete=models.PROTECT,
        related_name='agents', verbose_name='Ubicación'
    )
    daily_deposit_limit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('1000000.00'),
        validators=[MinValueValidator(Decimal('0.00'))], verbose_name='Límite diario de depósitos'
    )
    max_deposit_per_transaction = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('500000.00'),
        validators=[MinValueValidator(Decimal('0.00'))], verbose_name='Máximo por transacción'
    )
    total_deposits_made = models.PositiveIntegerField(default=0)
    total_amount_deposited = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Agente'
        verbose_name_plural = 'Agentes'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['location', 'is_active']),
            models.Index(fields=['verified']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.location.name if self.location else 'Sin ubicación'}"

    def verify(self, verified_by=None):
        self.verified = True
        self.verified_at = timezone.now()
        if verified_by:
            self.notes += f"\nVerificado por {verified_by.username} en {timezone.now()}"
        self.save(update_fields=['verified', 'verified_at', 'notes', 'updated_at'])

    def get_daily_stats(self):
        from django.db.models import Sum
        from .models import Transaction

        today = timezone.now().date()
        daily_transactions = Transaction.objects.filter(
            created_by=self.user, transaction_type='deposit',
            created_at__date=today, status='completed'
        )
        daily_count = daily_transactions.count()
        daily_total = daily_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        return {
            'count': daily_count, 'total': float(daily_total),
            'limit': float(self.daily_deposit_limit),
            'remaining': float(self.daily_deposit_limit - daily_total),
            'limit_reached': daily_total >= self.daily_deposit_limit
        }

    def can_make_deposit(self, amount):
        if not self.is_active:
            return {'allowed': False, 'reason': 'Agente inactivo', 'code': 'AGENT_INACTIVE'}
        if not self.verified:
            return {'allowed': False, 'reason': 'Agente no verificado', 'code': 'AGENT_NOT_VERIFIED'}
        if amount > self.max_deposit_per_transaction:
            return {
                'allowed': False,
                'reason': f'Monto excede límite por transacción ({self.max_deposit_per_transaction:,.0f} XAF)',
                'code': 'TRANSACTION_LIMIT_EXCEEDED',
                'limit': float(self.max_deposit_per_transaction)
            }
        daily_stats = self.get_daily_stats()
        if daily_stats['total'] + amount > self.daily_deposit_limit:
            return {
                'allowed': False,
                'reason': f'Límite diario excedido. Restante: {daily_stats["remaining"]:,.0f} XAF',
                'code': 'DAILY_LIMIT_EXCEEDED',
                'remaining': daily_stats['remaining'],
                'limit': daily_stats['limit']
            }
        return {'allowed': True, 'reason': None, 'code': None}

# wallet/models.py - AÑADIR AL FINAL DEL ARCHIVO

# wallet/models.py - VERSIÓN ÚNICA Y CORRECTA

class Office(models.Model):
    """
    Oficina física de DJI Music - CON CACHE DE TOTALES DIARIOS
    """
    name = models.CharField(max_length=200, verbose_name='Nombre de la oficina')
    address = models.TextField(verbose_name='Dirección completa')
    city = models.CharField(max_length=100, verbose_name='Ciudad')
    phone = models.CharField(max_length=20, verbose_name='Teléfono de contacto')
    email = models.EmailField(blank=True, verbose_name='Correo electrónico')
    manager_name = models.CharField(max_length=200, verbose_name='Nombre del responsable')
    is_active = models.BooleanField(default=True, verbose_name='Activa')
    
    daily_cash_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('2000000.00'),
        verbose_name='Límite diario de efectivo'
    )
    max_withdrawal_per_artist = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('500000.00'),
        verbose_name='Máximo por retiro por artista'
    )
    
    today_withdrawn_cached = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Total retirado hoy (cache)'
    )
    last_cache_date = models.DateField(null=True, blank=True, verbose_name='Última fecha de cache')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Oficina'
        verbose_name_plural = 'Oficinas'
        indexes = [
            models.Index(fields=['city', 'is_active']),
            models.Index(fields=['name']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.city}"
    
    def reset_daily_cache_if_needed(self):
        today = timezone.now().date()
        if self.last_cache_date != today:
            self.today_withdrawn_cached = Decimal('0.00')
            self.last_cache_date = today
            self.save(update_fields=['today_withdrawn_cached', 'last_cache_date'])
            return True
        return False
    
    @property
    def today_withdrawals_total(self):
        self.reset_daily_cache_if_needed()
        return self.today_withdrawn_cached
    
    @property
    def remaining_daily_limit(self):
        return self.daily_cash_limit - self.today_withdrawals_total


class OfficeStaff(models.Model):
    """Personal autorizado para operar en oficina"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='office_staff_profile'
    )
    office = models.ForeignKey(
        Office,  # ✅ Referencia directa (ya definido arriba)
        on_delete=models.PROTECT,
        related_name='staff_members'
    )
    employee_id = models.CharField(max_length=50, unique=True, verbose_name='ID de empleado')
    position = models.CharField(max_length=100, verbose_name='Cargo')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    daily_operation_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('1000000.00'),
        verbose_name='Límite diario de operaciones'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Personal de oficina'
        verbose_name_plural = 'Personal de oficinas'
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['office', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.office.name}"
    
    @property
    def today_operations_total(self):
        from django.db.models import Sum
        today = timezone.now().date()
        total = OfficeWithdrawal.objects.filter(
            processed_by=self,
            paid_at__date=today,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return total


class OfficeWithdrawal(models.Model):
    """Retiro procesado en oficina - CON IDEMPOTENCIA"""
    
    WITHDRAWAL_METHODS = [
        ('cash', 'Efectivo'),
        ('muni', 'Muni Dinero'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('processing', 'En proceso'),
        ('completed', 'Completado'),
        ('failed', 'Fallido'),
        ('cancelled', 'Cancelado'),
        ('reversed', 'Reversado'),
    ]
    
    reference = models.CharField(max_length=32, unique=True, editable=False)
    
    idempotency_key = models.CharField(
        max_length=64, unique=True, null=True, blank=True,
        db_index=True, verbose_name='Clave de idempotencia'
    )
    
    artist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_withdrawals',
        verbose_name='Artista'
    )
    wallet = models.ForeignKey(
        'Wallet',
        on_delete=models.PROTECT,
        related_name='office_withdrawals'
    )
    office = models.ForeignKey(
        Office,  # ✅ Referencia directa
        on_delete=models.PROTECT,
        related_name='withdrawals'
    )
    processed_by = models.ForeignKey(
        OfficeStaff,  # ✅ Referencia directa
        on_delete=models.PROTECT,
        related_name='processed_withdrawals'
    )
    
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Monto bruto')
    fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name='Comisión')
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Monto neto')
    
    withdrawal_method = models.CharField(max_length=10, choices=WITHDRAWAL_METHODS, verbose_name='Método')
    muni_phone = models.CharField(max_length=20, blank=True, verbose_name='Teléfono Muni (si aplica)')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    error_message = models.TextField(blank=True, verbose_name='Mensaje de error')
    retry_count = models.IntegerField(default=0, verbose_name='Intentos de reintento')
    
    id_number_verified = models.CharField(max_length=50, verbose_name='Número de identificación verificado')
    id_type_verified = models.CharField(max_length=20, default='dni', verbose_name='Tipo de identificación')
    
    requested_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    receipt_signed = models.BooleanField(default=False, verbose_name='Recibo firmado')
    notes = models.TextField(blank=True, verbose_name='Notas adicionales')
    
    class Meta:
        verbose_name = 'Retiro en oficina'
        verbose_name_plural = 'Retiros en oficina'
        indexes = [
            models.Index(fields=['artist', 'status']),
            models.Index(fields=['office', 'status']),
            models.Index(fields=['reference']),
            models.Index(fields=['paid_at']),
            models.Index(fields=['artist', 'paid_at']),
            models.Index(fields=['idempotency_key']),
            models.Index(fields=['status', 'requested_at']),
        ]
        ordering = ['-paid_at']
    
    def __str__(self):
        return f"{self.reference} - {self.artist.username} - {self.amount} XAF"
    
    def save(self, *args, **kwargs):
        if not self.reference:
            import secrets
            self.reference = f"OFF{secrets.token_hex(8).upper()}"
        super().save(*args, **kwargs)


class ArtistMuniAccount(models.Model):
    """Cuenta Muni Dinero del artista"""
    artist = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='muni_account'
    )
    phone_number = models.CharField(max_length=20, verbose_name='Número de teléfono Muni')
    is_default = models.BooleanField(default=True, verbose_name='Por defecto')
    is_verified = models.BooleanField(default=False, verbose_name='Verificado')
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Cuenta Muni Dinero'
        verbose_name_plural = 'Cuentas Muni Dinero'
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['artist', 'is_default']),
        ]
    
    def __str__(self):
        return f"{self.artist.username} - {self.phone_number}"