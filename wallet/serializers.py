# wallet/serializers.py
"""
Serializers para el sistema wallet.
Manejo de entrada/salida de datos con validaciones.
"""
from rest_framework import serializers
from django.utils import timezone
from decimal import Decimal
import logging

from .models import Wallet, Transaction, Hold, DepositCode,Agent, PhysicalLocation, OfficeWithdrawal
from .constants import TRANSACTION_TYPES, TRANSACTION_STATUS, HOLD_REASONS, CURRENCIES
from .exceptions import InsufficientFundsError, InvalidAmountError
from .services import WalletService

logger = logging.getLogger(__name__)

# wallet/serializers.py - AL PRINCIPIO, CON LOS OTROS IMPORTS

from .constants import (
    TRANSACTION_TYPES, 
    TRANSACTION_STATUS, 
    HOLD_REASONS, 
    CURRENCIES, 
    WALLET_NAMES  # ✅ AÑADIR ESTA LÍNEA
)

# ==================== WALLET SERIALIZERS ====================

class WalletSerializer(serializers.ModelSerializer):
    """
    Serializer principal para Wallet.
    Incluye campos calculados y validaciones.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    total_balance = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        source='total_balance'
    )
    has_funds = serializers.BooleanField(read_only=True, source='has_funds')
    can_spend = serializers.BooleanField(read_only=True, source='can_spend')
    daily_limit = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        source='daily_limit'
    )
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'user', 'user_email', 'user_username',
            'available_balance', 'pending_balance', 'total_balance',
            'total_deposited', 'total_spent', 'total_withdrawn',
            'currency', 'is_active', 'custom_daily_limit', 'daily_limit',
            'has_funds', 'can_spend',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'user_email', 'user_username',
            'available_balance', 'pending_balance', 'total_balance',
            'total_deposited', 'total_spent', 'total_withdrawn',
            'created_at', 'updated_at'
        ]
    
    def validate_custom_daily_limit(self, value):
        """Validar límite diario personalizado"""
        from .constants import LIMITS
        
        if value is not None:
            if value <= Decimal('0'):
                raise serializers.ValidationError(
                    "El límite diario debe ser mayor a 0"
                )
            if value > LIMITS['MAX_DAILY_LIMIT']:
                raise serializers.ValidationError(
                    f"El límite diario no puede exceder {LIMITS['MAX_DAILY_LIMIT']}"
                )
        return value
    
    def validate_currency(self, value):
        """Validar moneda"""
        if value not in dict(CURRENCIES):
            raise serializers.ValidationError(f"Moneda {value} no soportada")
        return value


class WalletCreateSerializer(serializers.Serializer):
    """
    Serializer para crear wallet.
    """
    user_id = serializers.IntegerField(required=True)
    currency = serializers.ChoiceField(
        choices=CURRENCIES,
        default='XAF'
    )
    
    def validate_user_id(self, value):
        """Validar que el usuario existe"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f"Usuario con ID {value} no existe")
        
        return value
    
    def validate(self, data):
        """Validar que el usuario no tenga wallet"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.get(id=data['user_id'])
        if hasattr(user, 'wallet'):
            raise serializers.ValidationError(
                "Este usuario ya tiene un monedero"
            )
        
        return data


class WalletBalanceSerializer(serializers.Serializer):
    """
    Serializer para consulta de balance.
    """
    language = serializers.ChoiceField(
        choices=['es', 'en', 'fr'],
        default='es',
        required=False
    )


# ==================== TRANSACTION SERIALIZERS ====================

class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer para transacciones.
    """
    wallet_id = serializers.IntegerField(source='wallet.id', read_only=True)
    amount_abs = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        source='absolute_amount'
    )
    formatted_amount = serializers.CharField(read_only=True)
    transaction_type_display = serializers.CharField(
        source='get_transaction_type_display',
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    created_by_email = serializers.EmailField(
        source='created_by.email',
        read_only=True
    )
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'reference', 'wallet_id',
            'amount', 'amount_abs', 'formatted_amount',
            'balance_before', 'balance_after',
            'transaction_type', 'transaction_type_display',
            'status', 'status_display',
            'metadata', 'description',
            'created_by', 'created_by_email',
            'created_at'
        ]
        read_only_fields = '__all__'


class DepositSerializer(serializers.Serializer):
    """
    Serializer para depósitos.
    """
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01')
    )
    description = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True
    )
    metadata = serializers.JSONField(required=False, default=dict)
    
    def validate_amount(self, value):
        """Validar monto mínimo y máximo"""
        from .constants import LIMITS
        
        if value < LIMITS['MIN_DEPOSIT']:
            raise serializers.ValidationError(
                f"El monto mínimo de depósito es {LIMITS['MIN_DEPOSIT']} XAF"
            )
        
        if value > LIMITS['MAX_DEPOSIT']:
            raise serializers.ValidationError(
                f"El monto máximo de depósito es {LIMITS['MAX_DEPOSIT']} XAF"
            )
        
        return value


class PurchaseSerializer(serializers.Serializer):
    """
    Serializer para compra de canción.
    """
    song_id = serializers.IntegerField(required=True)
    price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True
    )
    
    def validate_song_id(self, value):
        """Validar que la canción existe y está disponible"""
        try:
            from api2.models import Song
            song = Song.objects.get(id=value)
            
            # Verificar que la canción no sea gratuita
            if hasattr(song, 'price') and song.price <= 0:
                raise serializers.ValidationError(
                    "Esta canción es gratuita, no requiere compra"
                )
            
            # Verificar que la canción está publicada
            if hasattr(song, 'is_published') and not song.is_published:
                raise serializers.ValidationError(
                    "Esta canción no está disponible para compra"
                )
            
        except Song.DoesNotExist:
            raise serializers.ValidationError(f"Canción con ID {value} no existe")
        
        return value
    
    def validate_price(self, value):
        """Validar precio mínimo"""
        from .constants import LIMITS
        
        if value is not None:
            if value < LIMITS['MIN_DEPOSIT']:
                raise serializers.ValidationError(
                    f"El precio mínimo es {LIMITS['MIN_DEPOSIT']} XAF"
                )
        
        return value


class RefundSerializer(serializers.Serializer):
    """
    Serializer para reembolsos.
    """
    transaction_reference = serializers.CharField(max_length=32)
    reason = serializers.CharField(max_length=500)
    
    def validate_transaction_reference(self, value):
        """Validar que la transacción existe y es reembolsable"""
        try:
            tx = Transaction.objects.get(reference=value)
            
            # Verificar que sea una compra
            if tx.transaction_type != 'purchase':
                raise serializers.ValidationError(
                    "Solo se pueden reembolsar transacciones de compra"
                )
            
            # Verificar que no esté ya reembolsada
            if Transaction.objects.filter(
                metadata__original_transaction=value,
                transaction_type='refund'
            ).exists():
                raise serializers.ValidationError(
                    "Esta transacción ya fue reembolsada"
                )
            
        except Transaction.DoesNotExist:
            raise serializers.ValidationError(
                f"Transacción con referencia {value} no existe"
            )
        
        return value


# ==================== HOLD SERIALIZERS ====================

class HoldSerializer(serializers.ModelSerializer):
    """
    Serializer para retenciones (escrow).
    """
    transaction_reference = serializers.CharField(
        source='transaction.reference',
        read_only=True
    )
    artist_email = serializers.EmailField(
        source='artist.email',
        read_only=True
    )
    artist_username = serializers.CharField(
        source='artist.username',
        read_only=True
    )
    can_release = serializers.BooleanField(read_only=True)
    days_until_release = serializers.IntegerField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    reason_display = serializers.CharField(
        source='get_reason_display',
        read_only=True
    )
    song_info = serializers.JSONField(read_only=True)
    formatted_amount = serializers.SerializerMethodField()
    
    class Meta:
        model = Hold
        fields = [
            'id', 'transaction', 'transaction_reference',
            'artist', 'artist_email', 'artist_username',
            'amount', 'formatted_amount',
            'release_days', 'release_date',
            'is_released', 'released_at', 'released_by',
            'reason', 'reason_display',
            'notes', 'can_release', 'days_until_release',
            'is_overdue', 'song_info',
            'created_at', 'updated_at'
        ]
        read_only_fields = '__all__'
    
    def get_formatted_amount(self, obj):
        """Formatear monto con moneda"""
        return f"{obj.amount:,.0f} XAF"


class HoldReleaseSerializer(serializers.Serializer):
    """
    Serializer para liberar hold.
    """
    hold_id = serializers.IntegerField(required=True)
    
    def validate_hold_id(self, value):
        """Validar que el hold existe y es liberable"""
        try:
            hold = Hold.objects.get(id=value)
            
            if hold.is_released:
                raise serializers.ValidationError(
                    "Este hold ya fue liberado"
                )
            
            if not hold.can_release:
                raise serializers.ValidationError(
                    f"Este hold no está listo para liberar. "
                    f"Faltan {hold.days_until_release} días"
                )
            
        except Hold.DoesNotExist:
            raise serializers.ValidationError(f"Hold con ID {value} no existe")
        
        return value


# ==================== DEPOSIT CODE SERIALIZERS ====================

class DepositCodeSerializer(serializers.ModelSerializer):
    """
    Serializer para códigos de recarga.
    """
    created_by_email = serializers.EmailField(
        source='created_by.email',
        read_only=True
    )
    used_by_email = serializers.EmailField(
        source='used_by.email',
        read_only=True
    )
    is_valid = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = DepositCode
        fields = [
            'id', 'code', 'amount', 'currency',
            'is_used', 'used_by', 'used_by_email', 'used_at',
            'created_by', 'created_by_email', 'created_at',
            'expires_at', 'notes', 'is_valid'
        ]
        read_only_fields = ['id', 'code', 'used_at', 'created_at']
        extra_kwargs = {
            'created_by': {'read_only': True}
        }


class DepositCodeCreateSerializer(serializers.Serializer):
    """
    Serializer para crear códigos de recarga.
    """
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('0.01')
    )
    currency = serializers.ChoiceField(
        choices=CURRENCIES,
        default='XAF'
    )
    expires_days = serializers.IntegerField(
        min_value=1,
        max_value=365,
        default=90,
        help_text="Días hasta expiración (máximo 365)"
    )
    quantity = serializers.IntegerField(
        min_value=1,
        max_value=100,
        default=1,
        help_text="Cantidad de códigos a generar"
    )
    notes = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True
    )
    
    def validate_amount(self, value):
        """Validar monto mínimo y máximo"""
        from .constants import LIMITS
        
        if value < LIMITS['MIN_DEPOSIT']:
            raise serializers.ValidationError(
                f"El monto mínimo es {LIMITS['MIN_DEPOSIT']} XAF"
            )
        
        if value > LIMITS['MAX_DEPOSIT']:
            raise serializers.ValidationError(
                f"El monto máximo es {LIMITS['MAX_DEPOSIT']} XAF"
            )
        
        return value


class DepositCodeRedeemSerializer(serializers.Serializer):
    """
    Serializer para canjear código.
    """
    code = serializers.CharField(max_length=20)
    
    def validate_code(self, value):
        """Validar que el código existe y es válido"""
        value = value.upper().strip()
        
        try:
            deposit_code = DepositCode.objects.get(code=value)
            
            if not deposit_code.is_valid:
                if deposit_code.is_used:
                    raise serializers.ValidationError("Este código ya fue usado")
                if timezone.now() > deposit_code.expires_at:
                    raise serializers.ValidationError("Este código ha expirado")
                raise serializers.ValidationError("Código inválido")
            
        except DepositCode.DoesNotExist:
            raise serializers.ValidationError("Código inválido")
        
        return value


# ==================== BALANCE RESPONSE SERIALIZERS ====================

class BalanceInfoSerializer(serializers.Serializer):
    """
    Serializer para información de balance estructurada.
    """
    class BalanceDetailSerializer(serializers.Serializer):
        value = serializers.FloatField()
        formatted = serializers.CharField()
        name = serializers.CharField()
    
    available = BalanceDetailSerializer()
    pending = BalanceDetailSerializer()
    total = BalanceDetailSerializer()
    currency = serializers.CharField()
    total_deposited = serializers.FloatField()
    total_spent = serializers.FloatField()
    total_withdrawn = serializers.FloatField()


class ArtistEarningsSerializer(serializers.Serializer):
    """
    Serializer para ganancias de artista.
    """
    class UpcomingHoldSerializer(serializers.Serializer):
        amount = serializers.FloatField()
        release_date = serializers.CharField()
        days_left = serializers.IntegerField()
        song = serializers.JSONField(allow_null=True)
    
    pending = serializers.FloatField()
    released = serializers.FloatField()
    total = serializers.FloatField()
    upcoming = UpcomingHoldSerializer(many=True)


# ==================== TRANSACTION LIST SERIALIZER ====================

class TransactionListSerializer(serializers.Serializer):
    """
    Serializer para lista de transacciones con filtros.
    """
    limit = serializers.IntegerField(
        min_value=1,
        max_value=100,
        default=50,
        required=False
    )
    transaction_type = serializers.ChoiceField(
        choices=TRANSACTION_TYPES,
        required=False,
        allow_null=True
    )
    start_date = serializers.DateTimeField(required=False)
    end_date = serializers.DateTimeField(required=False)
    min_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True
    )
    max_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True
    )
    
    def validate(self, data):
        """Validar fechas y montos"""
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError(
                    "La fecha inicial debe ser anterior a la fecha final"
                )
        
        if data.get('min_amount') and data.get('max_amount'):
            if data['min_amount'] > data['max_amount']:
                raise serializers.ValidationError(
                    "El monto mínimo debe ser menor al monto máximo"
                )
        
        return data


# ==================== ADMIN SERIALIZERS ====================

class WalletAdminSerializer(serializers.ModelSerializer):
    """
    Serializer para administración de wallets.
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    total_balance = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
        source='total_balance'
    )
    
    class Meta:
        model = Wallet
        fields = [
            'id', 'user', 'user_email', 'user_username',
            'available_balance', 'pending_balance', 'total_balance',
            'total_deposited', 'total_spent', 'total_withdrawn',
            'currency', 'is_active', 'custom_daily_limit',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TransactionAdminSerializer(serializers.ModelSerializer):
    """
    Serializer para administración de transacciones.
    """
    wallet_user = serializers.EmailField(
        source='wallet.user.email',
        read_only=True
    )
    created_by_email = serializers.EmailField(
        source='created_by.email',
        read_only=True
    )
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'reference', 'wallet', 'wallet_user',
            'amount', 'balance_before', 'balance_after',
            'transaction_type', 'status',
            'metadata', 'description',
            'created_by', 'created_by_email',
            'created_at'
        ]
        read_only_fields = '__all__'

# wallet/serializers.py - AGREGAR AL FINAL

# ============================================================================
# SERIALIZERS PARA SISTEMA DE AGENTES
# ============================================================================

class PhysicalLocationSerializer(serializers.ModelSerializer):
    """Serializer para ubicaciones físicas"""
    
    class Meta:
        model = PhysicalLocation
        fields = [
            'id', 'name', 'address', 'city', 'country',
            'phone', 'email', 'is_active', 'opening_hours',
            'coordinates', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AgentSerializer(serializers.ModelSerializer):
    """Serializer para agentes"""
    user_email = serializers.SerializerMethodField()
    user_username = serializers.SerializerMethodField()
    user_full_name = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()
    location_city = serializers.SerializerMethodField()
    daily_stats = serializers.SerializerMethodField()
    
    class Meta:
        model = Agent
        fields = [
            'id', 'user', 'user_email', 'user_username', 'user_full_name',
            'location', 'location_name', 'location_city',
            'daily_deposit_limit', 'max_deposit_per_transaction',
            'total_deposits_made', 'total_amount_deposited',
            'is_active', 'verified', 'verified_at',
            'daily_stats', 'notes', 'created_at'
        ]
        read_only_fields = [
            'id', 'total_deposits_made', 'total_amount_deposited',
            'verified_at', 'created_at', 'updated_at'
        ]
    
    def get_user_email(self, obj):
        return obj.user.email
    
    def get_user_username(self, obj):
        return obj.user.username
    
    def get_user_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    
    def get_location_name(self, obj):
        return obj.location.name if obj.location else None
    
    def get_location_city(self, obj):
        return obj.location.city if obj.location else None
    
    def get_daily_stats(self, obj):
        return obj.get_daily_stats()


class AgentCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear agentes (solo admin)"""
    user_id = serializers.IntegerField(write_only=True)
    location_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Agent
        fields = [
            'user_id', 'location_id',
            'daily_deposit_limit', 'max_deposit_per_transaction',
            'is_active', 'notes'
        ]
    
    def validate_user_id(self, value):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=value)
            if hasattr(user, 'agent_profile'):
                raise serializers.ValidationError("Este usuario ya es agente")
            self.context['user'] = user
        except User.DoesNotExist:
            raise serializers.ValidationError("Usuario no encontrado")
        return value
    
    def validate_location_id(self, value):
        try:
            location = PhysicalLocation.objects.get(id=value)
            self.context['location'] = location
        except PhysicalLocation.DoesNotExist:
            raise serializers.ValidationError("Ubicación no encontrada")
        return value
    
    def create(self, validated_data):
        user = self.context['user']
        location = self.context['location']
        
        agent = Agent.objects.create(
            user=user,
            location=location,
            daily_deposit_limit=validated_data.get('daily_deposit_limit', Decimal('1000000.00')),
            max_deposit_per_transaction=validated_data.get('max_deposit_per_transaction', Decimal('500000.00')),
            is_active=validated_data.get('is_active', True),
            notes=validated_data.get('notes', '')
        )
        return agent


class AgentDepositSerializer(serializers.Serializer):
    """
    Serializer para que un agente realice una recarga.
    POST /api/wallet/agent/deposit/
    """
    user_id = serializers.IntegerField(help_text="ID del usuario a recargar")
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=100,
        help_text="Monto a recargar (mínimo 100 XAF)"
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Notas opcionales"
    )
    
    def validate_user_id(self, value):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=value)
            self.context['target_user'] = user
        except User.DoesNotExist:
            raise serializers.ValidationError("Usuario no encontrado")
        return value
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser positivo")
        if value < 100:
            raise serializers.ValidationError("El monto mínimo es 100 XAF")
        return value
    
    def validate(self, data):
        agent = self.context['agent']
        amount = data['amount']
        
        # Verificar límite por transacción
        if amount > agent.max_deposit_per_transaction:
            raise serializers.ValidationError(
                f"Monto excede el límite por transacción. "
                f"Máximo: {agent.max_deposit_per_transaction:,.0f} XAF"
            )
        
        # Verificar límite diario
        can_deposit, error_msg = agent.can_make_deposit(amount)
        if not can_deposit:
            raise serializers.ValidationError(error_msg)
        
        return data
    
    def create(self, validated_data):
        agent = self.context['agent']
        target_user = self.context['target_user']
        amount = validated_data['amount']
        notes = validated_data.get('notes', '')
        
        from wallet.services import WalletService
        
        # Realizar depósito
        transaction = WalletService.deposit(
            wallet_id=target_user.wallet.id,
            amount=amount,
            description=f"Recarga por agente {agent.user.username}: {notes}" if notes else f"Recarga por agente {agent.user.username}",
            created_by_id=agent.user.id,
            metadata={
                'agent_id': agent.id,
                'agent_name': agent.user.username,
                'location': agent.location.name if agent.location else None,
                'notes': notes,
                'transaction_type': 'agent_deposit'
            }
        )
        
        # Actualizar estadísticas del agente
        agent.total_deposits_made += 1
        agent.total_amount_deposited += amount
        agent.save(update_fields=['total_deposits_made', 'total_amount_deposited', 'updated_at'])
        
        return {
            'success': True,
            'transaction_reference': transaction.reference,
            'amount': float(amount),
            'user': {
                'id': target_user.id,
                'username': target_user.username,
                'email': target_user.email,
                'wallet_balance': float(target_user.wallet.available_balance)
            },
            'agent': {
                'id': agent.id,
                'username': agent.user.username,
                'daily_stats': agent.get_daily_stats()
            },
            'timestamp': transaction.created_at.isoformat()
        }


class AgentGenerateCodeSerializer(serializers.Serializer):
    """
    Serializer para generar códigos de recarga.
    POST /api/wallet/agent/generate-code/
    """
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=100,
        max_value=500000,
        help_text="Monto del código (mínimo 100, máximo 500,000 XAF)"
    )
    quantity = serializers.IntegerField(
        default=1,
        min_value=1,
        max_value=100,
        help_text="Cantidad de códigos a generar"
    )
    currency = serializers.ChoiceField(
        choices=[('XAF', 'XAF'), ('EUR', 'EUR'), ('USD', 'USD')],
        default='XAF',
        help_text="Moneda del código"
    )
    expires_days = serializers.IntegerField(
        default=30,
        min_value=1,
        max_value=365,
        help_text="Días hasta expiración"
    )
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser positivo")
        return value
    
    def create(self, validated_data):
        agent = self.context['agent']
        amount = validated_data['amount']
        quantity = validated_data['quantity']
        currency = validated_data['currency']
        expires_days = validated_data['expires_days']
        
        from wallet.models import DepositCode
        import secrets
        from django.utils import timezone
        
        codes = []
        for i in range(quantity):
            code = f"{currency}{secrets.token_hex(4).upper()}"
            while DepositCode.objects.filter(code=code).exists():
                code = f"{currency}{secrets.token_hex(4).upper()}"
            
            deposit_code = DepositCode.objects.create(
                code=code,
                amount=amount,
                currency=currency,
                created_by=agent.user,
                expires_at=timezone.now() + timezone.timedelta(days=expires_days),
                notes=f"Generado por agente {agent.user.username}"
            )
            codes.append(deposit_code)
        
        return {
            'success': True,
            'codes': [
                {
                    'code': c.code,
                    'amount': float(c.amount),
                    'currency': c.currency,
                    'expires_at': c.expires_at.isoformat(),
                    'qr_url': f"/api/wallet/codes/{c.code}/qr/"
                }
                for c in codes
            ],
            'count': len(codes),
            'generated_by': {
                'id': agent.id,
                'username': agent.user.username
            }
        }


class AgentSearchUserSerializer(serializers.Serializer):
    """Serializer para búsqueda de usuarios por agente"""
    query = serializers.CharField(max_length=100, help_text="Email, username o teléfono")
    
    def validate_query(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("La búsqueda requiere al menos 2 caracteres")
        return value.strip()


class AgentUserInfoSerializer(serializers.Serializer):
    """Información de usuario para agente (sin datos sensibles)"""
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.CharField()
    full_name = serializers.CharField()
    phone = serializers.CharField(allow_blank=True)
    wallet_balance = serializers.FloatField()
    is_verified = serializers.BooleanField()
    avatar_url = serializers.CharField(allow_null=True)


class RedeemCodeSerializer(serializers.Serializer):
    """
    Serializer para canjear un código de recarga.
    POST /api/wallet/codes/redeem/
    """
    code = serializers.CharField(max_length=50, help_text="Código de recarga")
    
    def validate_code(self, value):
        from wallet.models import DepositCode
        
        code = value.strip().upper()
        try:
            deposit_code = DepositCode.objects.get(code=code)
            self.context['deposit_code'] = deposit_code
        except DepositCode.DoesNotExist:
            raise serializers.ValidationError("Código inválido")
        
        if deposit_code.is_used:
            raise serializers.ValidationError("Este código ya fue usado")
        
        if timezone.now() > deposit_code.expires_at:
            raise serializers.ValidationError("Este código ha expirado")
        
        return code
    
    def create(self, validated_data):
        user = self.context['user']
        deposit_code = self.context['deposit_code']
        
        from wallet.services import WalletService
        
        transaction = WalletService.deposit(
            wallet_id=user.wallet.id,
            amount=deposit_code.amount,
            description=f"Canje de código {deposit_code.code}",
            created_by_id=user.id,
            metadata={
                'code': deposit_code.code,
                'code_id': deposit_code.id,
                'transaction_type': 'code_redeem'
            }
        )
        
        deposit_code.mark_as_used(user)
        
        return {
            'success': True,
            'transaction_reference': transaction.reference,
            'amount': float(deposit_code.amount),
            'currency': deposit_code.currency,
            'new_balance': float(user.wallet.available_balance),
            'timestamp': transaction.created_at.isoformat()
        }


class CodeQRSerializer(serializers.Serializer):
    """Serializer para respuesta de código QR"""
    code = serializers.CharField()
    qr_image = serializers.CharField(help_text="Base64 encoded QR image")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    expires_at = serializers.DateTimeField()
    is_used = serializers.BooleanField()
    qr_data = serializers.CharField()


class AgentEarningsSerializer(serializers.Serializer):
    """Serializer para ganancias de agente"""
    today = serializers.DictField()
    week = serializers.DictField()
    month = serializers.DictField()
    total = serializers.DictField()
    recent_transactions = serializers.ListField()

# wallet/serializers.py - AÑADIR ESTE SERIALIZER (al principio o al final)

class WalletBalanceResponseSerializer(serializers.Serializer):
    """
    Serializer para respuesta de balance con formateo.
    El formateo se hace AQUÍ, no en el modelo.
    """
    available = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending = serializers.DecimalField(max_digits=14, decimal_places=2)
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
    total_deposited = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_withdrawn = serializers.DecimalField(max_digits=14, decimal_places=2)
    
    def to_representation(self, instance):
        """
        Convertir datos del modelo a respuesta formateada.
        """
        language = self.context.get('language', 'es')
        names = WALLET_NAMES.get(language, WALLET_NAMES['es'])
        
        # Si instance es un dict (datos crudos)
        if isinstance(instance, dict):
            available = instance.get('available', Decimal('0'))
            pending = instance.get('pending', Decimal('0'))
            total = instance.get('total', Decimal('0'))
            currency = instance.get('currency', 'XAF')
            total_deposited = instance.get('total_deposited', Decimal('0'))
            total_spent = instance.get('total_spent', Decimal('0'))
            total_withdrawn = instance.get('total_withdrawn', Decimal('0'))
        else:
            # Si instance es un objeto Wallet
            available = instance.available_balance
            pending = instance.pending_balance
            total = instance.total_balance
            currency = instance.currency
            total_deposited = instance.total_deposited
            total_spent = instance.total_spent
            total_withdrawn = instance.total_withdrawn
        
        def _format_value(value, currency):
            """Formatear valor como moneda"""
            if value is None:
                return f"0 {currency}"
            try:
                val = float(value)
                if val == int(val):
                    return f"{int(val):,} {currency}"
                return f"{val:,.2f} {currency}"
            except:
                return f"{value} {currency}"
        
        return {
            'available': {
                'value': available,
                'formatted': _format_value(available, currency),
                'name': names.get('available', 'Disponible')
            },
            'pending': {
                'value': pending,
                'formatted': _format_value(pending, currency),
                'name': names.get('pending', 'Pendiente')
            },
            'total': {
                'value': total,
                'formatted': _format_value(total, currency),
                'name': names.get('balance', 'Balance Total')
            },
            'currency': currency,
            'total_deposited': total_deposited,
            'total_spent': total_spent,
            'total_withdrawn': total_withdrawn,
        }

# wallet/serializers.py - AÑADIR AL FINAL

# ============================================================================
# SERIALIZERS PARA SISTEMA DE RETIROS EN OFICINA
# ============================================================================

class OfficeWithdrawalSerializer(serializers.Serializer):
    """
    Serializer para procesar retiro en oficina
    POST /api/wallet/office/withdraw/
    """
    artist_id = serializers.IntegerField(help_text="ID del artista")
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal('1000'),
        help_text="Monto a retirar (mínimo 1,000 XAF)"
    )
    withdrawal_method = serializers.ChoiceField(
        choices=[('cash', 'Efectivo'), ('muni', 'Muni Dinero')],
        help_text="Método de retiro"
    )
    id_number = serializers.CharField(
        max_length=50,
        help_text="Número de identificación (DNI, pasaporte, etc.)"
    )
    id_type = serializers.ChoiceField(
        choices=[('dni', 'DNI/Cédula'), ('passport', 'Pasaporte')],
        default='dni',
        required=False,
        help_text="Tipo de identificación"
    )
    muni_phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text="Número de teléfono Muni (requerido si método es muni)"
    )
    notes = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Notas adicionales"
    )
    
    def validate_amount(self, value):
        """Validar monto mínimo"""
        if value < Decimal('1000'):
            raise serializers.ValidationError("El monto mínimo de retiro es 1,000 XAF")
        
        from .constants import LIMITS
        if value > Decimal('500000'):
            raise serializers.ValidationError("El monto máximo de retiro es 500,000 XAF")
        
        return value
    
    def validate(self, data):
        """Validar método de pago"""
        if data.get('withdrawal_method') == 'muni' and not data.get('muni_phone'):
            raise serializers.ValidationError({
                'muni_phone': 'Para retiro por Muni Dinero debe proporcionar el número de teléfono'
            })
        return data


class OfficeWithdrawalHistorySerializer(serializers.ModelSerializer):
    """
    Serializer para historial de retiros en oficina
    """
    artist_name = serializers.CharField(source='artist.get_full_name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    staff_name = serializers.CharField(source='processed_by.user.username', read_only=True)
    method_display = serializers.CharField(source='get_withdrawal_method_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = OfficeWithdrawal  # Este modelo debe existir
        fields = [
            'reference', 'amount', 'fee', 'net_amount', 
            'method_display', 'withdrawal_method',
            'status', 'status_display',
            'paid_at', 'requested_at',
            'office_name', 'staff_name', 'artist_name',
            'notes'
        ]


class OfficeDashboardStatsSerializer(serializers.Serializer):
    """
    Serializer para estadísticas del dashboard de oficina
    """
    office = serializers.DictField()
    today_stats = serializers.DictField()
    top_artists = serializers.ListField()
    staff_activity = serializers.ListField()
    recent_withdrawals = serializers.ListField(required=False)