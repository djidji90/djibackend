# wallet/models.py
"""
Modelos del sistema wallet.
Diseñado para producción: índices, validaciones, métodos útiles.
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid
from decimal import Decimal, InvalidOperation
from django.db.models import F, Sum, Q

from .constants import (
    TRANSACTION_TYPES, TRANSACTION_STATUS, HOLD_REASONS,
    CURRENCIES, LIMITS, COMMISSIONS, SONG_CATEGORY_CHOICES
)
from .validators import (
    validate_positive_amount, validate_currency, validate_min_deposit
)


class Wallet(models.Model):
    """
    Monedero principal del usuario.
    
    Los campos de balance son CACHÉ - la verdad está en Transaction.
    Siempre usar WalletService para modificar.
    """
    # Relación 1:1 con usuario
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
    
    # Configuración
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
    
    # Límites personalizados (si no, usa los globales)
    custom_daily_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Límite diario personalizado'
    )
    
    # Metadata
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
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.available_balance} {self.currency}"
    
    # --- PROPIEDADES ÚTILES ---
    
    @property
    def total_balance(self):
        """Saldo total (disponible + pendiente)"""
        return self.available_balance + self.pending_balance
    
    @property
    def has_funds(self):
        """¿Tiene algún saldo?"""
        return self.total_balance > 0
    
    @property
    def can_spend(self):
        """¿Puede gastar?"""
        return self.is_active and self.available_balance > 0
    
    @property
    def daily_limit(self):
        """Límite diario (personalizado o global)"""
        return self.custom_daily_limit or LIMITS['MAX_DAILY_PURCHASE']
    
    # --- MÉTODOS DE VALIDACIÓN ---
    
    def can_afford(self, amount):
        """Verificar si puede pagar un monto"""
        try:
            return self.available_balance >= Decimal(str(amount))
        except (ValueError, TypeError, InvalidOperation):
            return False
    
    def validate_transaction(self, amount, transaction_type):
        """Validar si una transacción es posible"""
        from .validators import validate_wallet_status, validate_daily_limit
        
        validate_wallet_status(self)
        validate_positive_amount(amount)
        
        if transaction_type == 'purchase':
            if not self.can_afford(amount):
                from .exceptions import InsufficientFundsError
                raise InsufficientFundsError(
                    f"Saldo insuficiente. Necesitas {amount} {self.currency}, "
                    f"tienes {self.available_balance} {self.currency}"
                )
        
        # Validar límite diario
        validate_daily_limit(self, amount, transaction_type)
        
        return True
    
    # --- MÉTODOS DE CONSULTA ---
    
    def get_balance_info(self, language='es'):
        """Información estructurada del saldo con nombres emocionales"""
        from .constants import WALLET_NAMES
        
        names = WALLET_NAMES.get(language, WALLET_NAMES['es'])
        
        return {
            'available': {
                'value': float(self.available_balance),
                'formatted': f"{self.available_balance:,.0f} {self.currency}",
                'name': names['available']
            },
            'pending': {
                'value': float(self.pending_balance),
                'formatted': f"{self.pending_balance:,.0f} {self.currency}",
                'name': names['pending']
            },
            'total': {
                'value': float(self.total_balance),
                'formatted': f"{self.total_balance:,.0f} {self.currency}",
                'name': names['balance']
            },
            'currency': self.currency,
            'total_deposited': float(self.total_deposited),
            'total_spent': float(self.total_spent),
            'total_withdrawn': float(self.total_withdrawn),
        }
    
    def get_transactions(self, limit=50, transaction_type=None):
        """Obtener últimas transacciones"""
        qs = self.transactions.all()
        if transaction_type:
            qs = qs.filter(transaction_type=transaction_type)
        return qs.select_related('wallet')[:limit]
    
    def get_pending_holds(self):
        """Obtener retenciones pendientes"""
        from .models import Hold
        return Hold.objects.filter(
            transaction__wallet=self,
            is_released=False
        ).select_related('artist')


class Transaction(models.Model):
    """
    Registro inmutable de TODAS las transacciones.
    Esta es la FUENTE DE VERDAD del sistema.
    NUNCA se modifica, solo se crean transacciones de compensación.
    """
    # Identificador único (para tracking externo)
    reference = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        verbose_name='Referencia',
        db_index=True
    )
    
    # Wallet relacionado
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name='Monedero'
    )
    
    # Monto (positivo = ingreso, negativo = egreso)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('-999999.00'))],
        verbose_name='Monto'
    )
    
    # Balances antes/después (para auditoría)
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
    
    # Tipo y estado
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
    
    # Metadata flexible (JSON)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Metadatos',
        help_text='Información adicional: song_id, artist_id, etc.'
    )
    
    # Descripción amigable
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Descripción'
    )
    
    # Auditoría
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
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        sign = '+' if self.amount >= 0 else ''
        return f"{self.reference} - {self.transaction_type} {sign}{self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"TX{uuid.uuid4().hex[:12].upper()}"
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
    
    def get_song_info(self):
        if self.metadata and 'song_id' in self.metadata:
            try:
                from api2.models import Song
                song = Song.objects.get(id=self.metadata['song_id'])
                return {
                    'id': song.id,
                    'title': song.title,
                    'artist': song.artist
                }
            except:
                pass
        return None


class Hold(models.Model):
    """
    Retención (escrow) de fondos para artistas.
    Los fondos se liberan después de N días o manualmente.
    """
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
    
    @property
    def song_info(self):
        return self.transaction.get_song_info()
    
    def release(self, released_by=None):
        from .services import WalletService
        return WalletService.release_hold(self.id, released_by)


class DepositCode(models.Model):
    """
    Códigos de recarga física.
    Se venden en sedes y se canjean en la app.
    """
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
        self.is_used = True
        self.used_by = user
        self.used_at = timezone.now()
        self.save(update_fields=['is_used', 'used_by', 'used_at'])


# ============================================================================
# MODELOS PARA SISTEMA DE RECARGAS FÍSICAS
# ============================================================================

class PhysicalLocation(models.Model):
    """
    Ubicación física donde se pueden realizar recargas.
    """
    name = models.CharField(
        max_length=200,
        verbose_name='Nombre del local'
    )
    address = models.TextField(
        verbose_name='Dirección'
    )
    city = models.CharField(
        max_length=100,
        verbose_name='Ciudad'
    )
    country = models.CharField(
        max_length=2,
        default='GQ',
        choices=[
            ('GQ', 'Guinea Ecuatorial'),
            ('ES', 'España'),
            ('FR', 'Francia'),
            ('US', 'Estados Unidos'),
        ],
        verbose_name='País'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Teléfono'
    )
    email = models.EmailField(
        blank=True,
        verbose_name='Correo electrónico'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo'
    )
    opening_hours = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Horario de atención',
        help_text='Ej: {"monday": "9:00-18:00", "tuesday": "9:00-18:00"}'
    )
    coordinates = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Coordenadas',
        help_text='Ej: {"lat": 3.7523, "lng": 8.7737}'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )
    
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
    """
    Agente autorizado para realizar recargas físicas.
    Cada agente está asociado a un usuario y una ubicación.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_profile',
        verbose_name='Usuario'
    )
    
    location = models.ForeignKey(
        PhysicalLocation,
        on_delete=models.PROTECT,
        related_name='agents',
        verbose_name='Ubicación'
    )
    
    # Límites operativos
    daily_deposit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('1000000.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Límite diario de depósitos'
    )
    
    max_deposit_per_transaction = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('500000.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Máximo por transacción'
    )
    
    # Estadísticas
    total_deposits_made = models.PositiveIntegerField(
        default=0,
        verbose_name='Total de depósitos realizados'
    )
    
    total_amount_deposited = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Monto total depositado'
    )
    
    # Estado
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Si está inactivo, no puede realizar recargas'
    )
    
    verified = models.BooleanField(
        default=False,
        verbose_name='Verificado',
        help_text='Agente verificado por administración'
    )
    
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de verificación'
    )
    
    # Notas
    notes = models.TextField(
        blank=True,
        verbose_name='Notas'
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha creación'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )
    
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
        """Verificar agente"""
        self.verified = True
        self.verified_at = timezone.now()
        if verified_by:
            self.notes += f"\nVerificado por {verified_by.username} en {timezone.now()}"
        self.save(update_fields=['verified', 'verified_at', 'notes', 'updated_at'])
    
    def get_daily_stats(self):
        """Obtener estadísticas del día actual"""
        from django.db.models import Sum
        from .models import Transaction
        
        today = timezone.now().date()
        daily_transactions = Transaction.objects.filter(
            created_by=self.user,
            transaction_type='deposit',
            created_at__date=today,
            status='completed'
        )
        
        daily_count = daily_transactions.count()
        daily_total = daily_transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        return {
            'count': daily_count,
            'total': float(daily_total),
            'limit': float(self.daily_deposit_limit),
            'remaining': float(self.daily_deposit_limit - daily_total),
            'limit_reached': daily_total >= self.daily_deposit_limit
        }
    
    def can_make_deposit(self, amount):
        """Verificar si puede realizar un depósito de este monto"""
        if not self.is_active:
            return False, "Agente inactivo"
        
        if not self.verified:
            return False, "Agente no verificado"
        
        if amount > self.max_deposit_per_transaction:
            return False, f"Monto excede límite por transacción ({self.max_deposit_per_transaction} XAF)"
        
        daily_stats = self.get_daily_stats()
        if daily_stats['total'] + amount > self.daily_deposit_limit:
            return False, f"Límite diario excedido. Restante: {daily_stats['remaining']} XAF"
        
        return True, None