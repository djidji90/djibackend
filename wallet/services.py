# wallet/services.py
"""
Servicio centralizado para todas las operaciones del wallet.
TODAS las modificaciones de saldo deben pasar por aquí.
Garantiza consistencia transaccional y auditoría.
"""
from django.db import transaction as db_transaction
from django.db.models import F, Sum, Q  # ✅ CORREGIDO: Sum agregado
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import logging
from typing import Optional, Tuple, Dict, Any

from .models import Wallet, Transaction, Hold, DepositCode
from .exceptions import (
    InsufficientFundsError, InvalidAmountError, WalletNotFoundError,
    HoldNotFoundError, HoldAlreadyReleasedError, HoldNotReleasableError,
    PurchaseFailedError, CurrencyMismatchError, LimitExceededError
)
from .constants import COMMISSIONS, LIMITS, ERROR_CODES
from .validators import validate_positive_amount, validate_max_balance

logger = logging.getLogger(__name__)


class WalletService:
    """
    Servicio singleton para operaciones del wallet.
    Todos los métodos son atómicos y thread-safe.
    """
    
    # ==================== MÉTODOS PÚBLICOS ====================
    
    @staticmethod
    @db_transaction.atomic
    def deposit(
        wallet_id: int,
        amount: Decimal,
        description: str = "",
        created_by_id: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> Transaction:
        """
        DEP-01: Recarga de saldo (efectivo, código, transferencia)
        
        Args:
            wallet_id: ID del wallet
            amount: Monto positivo a depositar
            description: Descripción amigable
            created_by_id: ID del usuario que realiza la operación
            metadata: Metadatos adicionales
        
        Returns:
            Transaction: Transacción creada
        
        Raises:
            WalletNotFoundError: Wallet no existe
            InvalidAmountError: Monto inválido
            LimitExceededError: Límite excedido
        """
        # 1. Validaciones iniciales
        try:
            amount_decimal = WalletService._validate_amount(amount)
        except Exception as e:
            raise InvalidAmountError(str(e))
        
        if amount_decimal <= Decimal('0'):
            raise InvalidAmountError("El monto debe ser mayor a cero")
        
        # 2. Obtener wallet con lock
        try:
            wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet {wallet_id} no encontrado")
        
        # 3. Validar wallet
        WalletService._validate_wallet(wallet)
        
        # 4. Validar límites
        WalletService._check_daily_limit(wallet, amount_decimal, 'deposit')
        
        # 5. Validar balance máximo
        try:
            validate_max_balance(amount_decimal, wallet.available_balance)
        except Exception as e:
            raise LimitExceededError(str(e))
        
        # 6. Crear transacción
        tx = Transaction.objects.create(
            wallet=wallet,
            amount=amount_decimal,
            balance_before=wallet.available_balance,
            balance_after=wallet.available_balance + amount_decimal,
            transaction_type='deposit',
            status='completed',
            metadata=metadata or {},
            description=description or f"Recarga de {amount_decimal} {wallet.currency}",
            created_by_id=created_by_id
        )
        
        # 7. Actualizar wallet (ATÓMICO)
        Wallet.objects.filter(id=wallet.id).update(
            available_balance=F('available_balance') + amount_decimal,
            total_deposited=F('total_deposited') + amount_decimal,
            updated_at=timezone.now()
        )
        
        # 8. Refrescar y log
        wallet.refresh_from_db()
        logger.info(
            f"✅ DEP-01: Depósito exitoso",
            extra={
                'reference': tx.reference,
                'wallet_id': wallet_id,
                'amount': float(amount_decimal),
                'currency': wallet.currency,
                'new_balance': float(wallet.available_balance)
            }
        )
        
        return tx
    
    @staticmethod
    @db_transaction.atomic
    def purchase_song(
        user_id: int,
        song_id: int,
        price: Optional[Decimal] = None
    ) -> Tuple[Transaction, Hold]:
        """
        PUR-01: Compra de canción
        
        Args:
            user_id: ID del usuario comprador
            song_id: ID de la canción
            price: Precio (opcional, si no se proporciona, se obtiene de la canción)
        
        Returns:
            Tuple (Transaction, Hold)
        
        Raises:
            InsufficientFundsError: Saldo insuficiente
            PurchaseFailedError: Error en compra
        """
        # 1. Obtener canción (✅ IMPORTACIÓN CORREGIDA)
        try:
            from api2.models import Song
            song = Song.objects.select_for_update().get(id=song_id)
        except Exception as e:
            raise PurchaseFailedError(f"Canción no encontrada: {str(e)}")
        
        # 2. Determinar precio
        if price is None:
            if not hasattr(song, 'price') or song.price <= 0:
                raise PurchaseFailedError("Canción sin precio o gratuita")
            price = song.price
        
        try:
            price_decimal = Decimal(str(price))
        except (InvalidOperation, TypeError):
            raise InvalidAmountError("Precio inválido")
        
        # 3. Validar precio mínimo
        if price_decimal < LIMITS['MIN_DEPOSIT']:
            raise InvalidAmountError(f"Precio mínimo: {LIMITS['MIN_DEPOSIT']} XAF")
        
        # 4. Obtener wallet del usuario
        try:
            wallet = Wallet.objects.select_for_update().get(user_id=user_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet no encontrado para usuario {user_id}")
        
        # 5. Validar wallet
        WalletService._validate_wallet(wallet)
        
        # 6. Validar fondos
        if not wallet.can_afford(price_decimal):
            raise InsufficientFundsError(
                f"Saldo insuficiente. Necesitas {price_decimal} {wallet.currency}, "
                f"tienes {wallet.available_balance} {wallet.currency}"
            )
        
        # 7. Validar límite diario
        WalletService._check_daily_limit(wallet, price_decimal, 'purchase')
        
        # 8. Calcular comisiones
        artist_share = (price_decimal * COMMISSIONS['ARTIST']).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        platform_share = price_decimal - artist_share
        
        # 9. Obtener artista (quien subió la canción)
        artist = song.uploaded_by
        if not artist:
            logger.warning(f"Canción {song_id} sin artista asignado")
            raise PurchaseFailedError("La canción no tiene artista asociado")
        
        # 10. Crear transacción de compra
        tx = Transaction.objects.create(
            wallet=wallet,
            amount=-price_decimal,
            balance_before=wallet.available_balance,
            balance_after=wallet.available_balance - price_decimal,
            transaction_type='purchase',
            status='completed',
            metadata={
                'song_id': song_id,
                'song_title': song.title,
                'artist_id': artist.id,
                'artist_name': artist.username,
                'price': float(price_decimal),
                'currency': wallet.currency,
                'artist_share': float(artist_share),
                'platform_share': float(platform_share),
            },
            description=f"Compra: {song.title}",
            created_by_id=user_id
        )
        
        # 11. Crear hold para artista
        hold = None
        if artist and artist_share > 0:
            hold = Hold.objects.create(
                transaction=tx,
                artist=artist,
                amount=artist_share,
                reason='song_purchase',
                notes=f"Compra de canción: {song.title}"
            )
        
        # 12. Registrar comisión
        if platform_share > 0:
            Transaction.objects.create(
                wallet=wallet,
                amount=Decimal('0'),
                balance_before=wallet.available_balance - price_decimal,
                balance_after=wallet.available_balance - price_decimal,
                transaction_type='fee',
                status='completed',
                metadata={
                    'song_id': song_id,
                    'amount': float(platform_share),
                    'original_transaction': tx.reference
                },
                description=f"Comisión: {song.title}",
                created_by_id=user_id
            )
        
        # 13. Actualizar wallet
        update_fields = {
            'available_balance': F('available_balance') - price_decimal,
            'total_spent': F('total_spent') + price_decimal,
            'updated_at': timezone.now()
        }
        
        if artist:
            update_fields['pending_balance'] = F('pending_balance') + artist_share
        
        Wallet.objects.filter(id=wallet.id).update(**update_fields)
        
        # 14. Actualizar estadísticas de canción
        try:
            if hasattr(song, 'sales_count'):
                song.sales_count = F('sales_count') + 1
            if hasattr(song, 'total_revenue'):
                song.total_revenue = F('total_revenue') + price_decimal
            song.save()
        except Exception as e:
            logger.error(f"Error actualizando estadísticas de canción {song_id}: {str(e)}")
        
        # 15. Log y retorno
        wallet.refresh_from_db()
        logger.info(
            f"✅ PUR-01: Compra exitosa",
            extra={
                'reference': tx.reference,
                'user_id': user_id,
                'song_id': song_id,
                'amount': float(price_decimal),
                'artist_share': float(artist_share),
                'new_balance': float(wallet.available_balance)
            }
        )
        
        return tx, hold
    
    @staticmethod
    @db_transaction.atomic
    def release_hold(
        hold_id: int,
        released_by_id: Optional[int] = None
    ) -> Transaction:
        """
        REL-01: Liberar hold a artista
        
        Args:
            hold_id: ID del hold
            released_by_id: ID del usuario que libera (admin)
        
        Returns:
            Transaction: Transacción de liberación
        
        Raises:
            HoldNotFoundError: Hold no existe
            HoldAlreadyReleasedError: Ya liberado
            HoldNotReleasableError: No se puede liberar aún
        """
        # 1. Obtener hold con lock
        try:
            hold = Hold.objects.select_for_update().get(id=hold_id)
        except Hold.DoesNotExist:
            raise HoldNotFoundError(f"Hold {hold_id} no encontrado")
        
        # 2. Validar estado
        if hold.is_released:
            raise HoldAlreadyReleasedError("Este hold ya fue liberado")
        
        if not hold.can_release:
            days_left = hold.days_until_release
            raise HoldNotReleasableError(
                f"Hold no liberable aún. Faltan {days_left} días "
                f"(liberación: {hold.release_date.strftime('%d/%m/%Y')})"
            )
        
        # 3. Obtener wallet del artista
        try:
            artist_wallet = Wallet.objects.select_for_update().get(user=hold.artist)
        except Wallet.DoesNotExist:
            # Crear wallet si no existe
            artist_wallet = Wallet.objects.create(
                user=hold.artist,
                currency='XAF'
            )
            logger.info(f"Wallet creado automáticamente para artista {hold.artist.id}")
        
        # 4. Validar wallet del artista
        WalletService._validate_wallet(artist_wallet)
        
        # 5. Crear transacción de liberación
        tx = Transaction.objects.create(
            wallet=artist_wallet,
            amount=hold.amount,
            balance_before=artist_wallet.available_balance,
            balance_after=artist_wallet.available_balance + hold.amount,
            transaction_type='release',
            status='completed',
            metadata={
                'hold_id': hold_id,
                'original_transaction': hold.transaction.reference,
                'song_id': hold.transaction.metadata.get('song_id'),
                'reason': hold.reason,
            },
            description=f"Liberación por {hold.get_reason_display()}",
            created_by_id=released_by_id
        )
        
        # 6. Actualizar wallet del artista
        Wallet.objects.filter(id=artist_wallet.id).update(
            available_balance=F('available_balance') + hold.amount,
            total_withdrawn=F('total_withdrawn') + hold.amount,
            updated_at=timezone.now()
        )
        
        # 7. Actualizar wallet original (quitar pending)
        original_wallet = hold.transaction.wallet
        Wallet.objects.filter(id=original_wallet.id).update(
            pending_balance=F('pending_balance') - hold.amount,
            updated_at=timezone.now()
        )
        
        # 8. Marcar hold como liberado
        hold.is_released = True
        hold.released_at = timezone.now()
        hold.released_by_id = released_by_id
        hold.save(update_fields=['is_released', 'released_at', 'released_by', 'updated_at'])
        
        # 9. Refrescar
        artist_wallet.refresh_from_db()
        original_wallet.refresh_from_db()
        
        logger.info(
            f"✅ REL-01: Hold liberado",
            extra={
                'hold_id': hold_id,
                'artist_id': hold.artist.id,
                'amount': float(hold.amount),
                'transaction': tx.reference
            }
        )
        
        return tx
    
    @staticmethod
    @db_transaction.atomic
    def redeem_code(
        code: str,
        user_id: int
    ) -> Transaction:
        """
        RED-01: Canjear código de recarga
        
        Args:
            code: Código a canjear
            user_id: ID del usuario que canjea
        
        Returns:
            Transaction: Transacción de depósito
        """
        # 1. Buscar código
        try:
            deposit_code = DepositCode.objects.select_for_update().get(
                code=code.upper().strip()
            )
        except DepositCode.DoesNotExist:
            raise PurchaseFailedError("Código inválido")
        
        # 2. Validar código
        if not deposit_code.is_valid:
            if deposit_code.is_used:
                raise PurchaseFailedError("Este código ya fue usado")
            if timezone.now() > deposit_code.expires_at:
                raise PurchaseFailedError("Este código ha expirado")
            raise PurchaseFailedError("Código inválido")
        
        # 3. Realizar depósito
        tx = WalletService.deposit(
            wallet_id=Wallet.objects.get(user_id=user_id).id,
            amount=deposit_code.amount,
            description=f"Canje de código {deposit_code.code}",
            created_by_id=user_id,
            metadata={'code': deposit_code.code, 'code_id': deposit_code.id}
        )
        
        # 4. Marcar código como usado
        deposit_code.mark_as_used(user_id)
        
        return tx
    
    @staticmethod
    @db_transaction.atomic
    def refund_purchase(
        purchase_transaction_reference: str,
        reason: str,
        refunded_by_id: Optional[int] = None
    ) -> Transaction:
        """
        REF-01: Reembolsar una compra
        
        Args:
            purchase_transaction_reference: Referencia de la transacción original
            reason: Motivo del reembolso
            refunded_by_id: ID del usuario que reembolsa (admin)
        
        Returns:
            Transaction: Transacción de reembolso
        """
        # 1. Buscar transacción original
        try:
            original_tx = Transaction.objects.select_for_update().get(
                reference=purchase_transaction_reference
            )
        except Transaction.DoesNotExist:
            raise PurchaseFailedError("Transacción no encontrada")
        
        # 2. Validar que sea una compra
        if original_tx.transaction_type != 'purchase':
            raise PurchaseFailedError("Solo se pueden reembolsar compras")
        
        # 3. Verificar que no haya sido reembolsada
        if Transaction.objects.filter(
            metadata__original_transaction=original_tx.reference,
            transaction_type='refund'
        ).exists():
            raise PurchaseFailedError("Esta compra ya fue reembolsada")
        
        # 4. Obtener wallet con lock
        wallet = Wallet.objects.select_for_update().get(id=original_tx.wallet.id)
        
        # 5. Crear transacción de reembolso
        refund_tx = Transaction.objects.create(
            wallet=wallet,
            amount=abs(original_tx.amount),
            balance_before=wallet.available_balance,
            balance_after=wallet.available_balance + abs(original_tx.amount),
            transaction_type='refund',
            status='completed',
            metadata={
                'original_transaction': original_tx.reference,
                'reason': reason,
                'song_id': original_tx.metadata.get('song_id')
            },
            description=f"Reembolso: {reason}",
            created_by_id=refunded_by_id
        )
        
        # 6. Actualizar wallet
        Wallet.objects.filter(id=wallet.id).update(
            available_balance=F('available_balance') + abs(original_tx.amount),
            total_spent=F('total_spent') - abs(original_tx.amount),
            updated_at=timezone.now()
        )
        
        # 7. Marcar hold como liberado si existe
        try:
            hold = Hold.objects.get(transaction=original_tx)
            if not hold.is_released:
                hold.is_released = True
                hold.released_at = timezone.now()
                hold.notes = f"Reembolsado: {reason}"
                hold.save()
                
                Wallet.objects.filter(id=wallet.id).update(
                    pending_balance=F('pending_balance') - hold.amount
                )
        except Hold.DoesNotExist:
            pass
        
        logger.info(
            f"✅ REF-01: Reembolso exitoso",
            extra={
                'original_tx': original_tx.reference,
                'refund_tx': refund_tx.reference,
                'amount': float(abs(original_tx.amount))
            }
        )
        
        return refund_tx
    
    # ==================== MÉTODOS DE CONSULTA ====================
    
    @staticmethod
    def get_balance(wallet_id: int, language: str = 'es') -> Dict[str, Any]:
        """CON-01: Obtener información de balance"""
        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet {wallet_id} no encontrado")
        
        return wallet.get_balance_info(language)
    
    @staticmethod
    def get_transactions(
        wallet_id: int,
        limit: int = 50,
        transaction_type: Optional[str] = None
    ):
        """CON-02: Obtener transacciones"""
        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet {wallet_id} no encontrado")
        
        return wallet.get_transactions(limit, transaction_type)
    
    @staticmethod
    def get_artist_earnings(artist_id: int) -> Dict[str, Any]:
        """
        CON-03: Obtener ganancias de artista
        """
        # ✅ Sum ya está importado al inicio del archivo
        from django.db.models import Sum
        
        # Totales
        total_held = Hold.objects.filter(
            artist_id=artist_id,
            is_released=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        total_released = Hold.objects.filter(
            artist_id=artist_id,
            is_released=True
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Próximos a liberar
        upcoming_holds = Hold.objects.filter(
            artist_id=artist_id,
            is_released=False,
            release_date__lte=timezone.now() + timezone.timedelta(days=7)
        ).order_by('release_date')
        
        return {
            'pending': float(total_held),
            'released': float(total_released),
            'total': float(total_held + total_released),
            'upcoming': [
                {
                    'amount': float(h.amount),
                    'release_date': h.release_date.isoformat(),
                    'days_left': h.days_until_release,
                    'song': h.song_info
                }
                for h in upcoming_holds[:10]
            ]
        }
    
    @staticmethod
    def get_user_wallet(user_id: int) -> Wallet:
        """CON-04: Obtener wallet de usuario (crear si no existe)"""
        try:
            return Wallet.objects.get(user_id=user_id)
        except Wallet.DoesNotExist:
            # Crear wallet automáticamente
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            try:
                user = User.objects.get(id=user_id)
                currency = 'XAF'
                if hasattr(user, 'country'):
                    from .constants import COUNTRY_CURRENCY_MAP
                    currency = COUNTRY_CURRENCY_MAP.get(user.country, 'XAF')
                
                wallet = Wallet.objects.create(
                    user=user,
                    currency=currency
                )
                logger.info(f"Wallet creado automáticamente para usuario {user_id}")
                return wallet
            except User.DoesNotExist:
                raise WalletNotFoundError(f"Usuario {user_id} no encontrado")
    
    # ==================== MÉTODOS PRIVADOS ====================
    
    @staticmethod
    def _validate_amount(amount) -> Decimal:
        """Validar y convertir amount a Decimal"""
        if isinstance(amount, (int, float)):
            result = Decimal(str(amount))
        elif isinstance(amount, Decimal):
            result = amount
        elif isinstance(amount, str):
            try:
                result = Decimal(amount.replace(',', '.'))
            except:
                raise InvalidAmountError(f"Monto inválido: {amount}")
        else:
            raise InvalidAmountError(f"Tipo de monto inválido: {type(amount)}")
        
        result = result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        return result
    
    @staticmethod
    def _validate_wallet(wallet: Wallet):
        """Validar que el wallet esté activo"""
        if not wallet.is_active:
            from .exceptions import UnauthorizedWalletActionError
            raise UnauthorizedWalletActionError("La wallet está desactivada")
    
    @staticmethod
    def _check_daily_limit(wallet: Wallet, amount: Decimal, tx_type: str):
        """Verificar límite diario"""
        from django.db.models import Sum
        
        today = timezone.now().date()
        
        daily_total = Transaction.objects.filter(
            wallet=wallet,
            transaction_type=tx_type,
            created_at__date=today,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        amount_abs = abs(amount)
        current_total = abs(daily_total)
        
        if current_total + amount_abs > wallet.daily_limit:
            raise LimitExceededError(
                f"Límite diario excedido. "
                f"Usado hoy: {current_total} {wallet.currency}, "
                f"Límite: {wallet.daily_limit} {wallet.currency}"
            )
    
    @staticmethod
    def _check_currency_match(wallet: Wallet, amount_currency: str):
        """Verificar que las monedas coincidan"""
        if wallet.currency != amount_currency:
            raise CurrencyMismatchError(
                f"Moneda del wallet ({wallet.currency}) "
                f"no coincide con transacción ({amount_currency})"
            )


