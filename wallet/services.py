# wallet/services.py - COMPLETO PARA PRODUCCIÓN
"""
Servicio centralizado para todas las operaciones del wallet.
✅ Concurrencia con select_for_update(nowait=True)
✅ Idempotencia con BD
✅ Validaciones completas
✅ Consistencia contable
✅ Auditoría
✅ Protección contra abusos
"""
from django.db import transaction as db_transaction
from django.db.models import F, Sum, Q
from django.utils import timezone
from django.core.cache import cache
from django.db.utils import OperationalError
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import hashlib
import json
import logging
from typing import Optional, Tuple, Dict, Any
from .models import Office, OfficeStaff, OfficeWithdrawal, ArtistMuniAccount
from django.db.models import Avg, Count 
from .models import Wallet, Transaction, Hold, DepositCode, IdempotencyKey, AuditLog, SuspiciousActivity
from .exceptions import (
    InsufficientFundsError, InvalidAmountError, WalletNotFoundError,
    HoldNotFoundError, HoldAlreadyReleasedError, HoldNotReleasableError,
    PurchaseFailedError, CurrencyMismatchError, LimitExceededError,
    DuplicateTransactionError, ConcurrentModificationError, InconsistentStateError,
    UnauthorizedWalletActionError

)
from .constants import COMMISSIONS, LIMITS, ERROR_CODES
from .validators import validate_positive_amount, validate_max_balance


logger = logging.getLogger(__name__)


class WalletService:
    """
    Servicio singleton para operaciones del wallet.
    ✅ Todos los métodos son atómicos y thread-safe.
    ✅ Idempotencia garantizada con BD.
    """

    @staticmethod
    def _generate_idempotency_key(prefix: str, *args, **kwargs) -> str:
        """Generar clave de idempotencia única."""
        data = f"{prefix}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    @staticmethod
    def _check_idempotency(key: str, wallet_id: int) -> Optional[Transaction]:
        """Verificar si ya existe una transacción con esta clave en BD."""
        try:
            idempotency_record = IdempotencyKey.objects.select_related('transaction').get(key=key, wallet_id=wallet_id)
            return idempotency_record.transaction
        except IdempotencyKey.DoesNotExist:
            return None

    @staticmethod
    def _check_cooldown(wallet: Wallet):
        """Evitar spam de operaciones"""
        last_tx = Transaction.objects.filter(
            wallet=wallet,
            status='completed'
        ).order_by('-created_at').first()
        
        if last_tx:
            seconds_since_last = (timezone.now() - last_tx.created_at).seconds
            if seconds_since_last < 5:  # 5 segundos de cooldown
                raise LimitExceededError(
                    f"Demasiadas operaciones seguidas. Espera {5 - seconds_since_last} segundos."
                )

    @staticmethod
    def _check_suspicious_activity(wallet: Wallet, user_id: int):
        """Detectar actividad inusual"""
        last_minute = timezone.now() - timezone.timedelta(minutes=1)
        
        tx_count = Transaction.objects.filter(
            wallet=wallet,
            created_at__gte=last_minute,
            status='completed'
        ).count()
        
        if tx_count > 5:  # Más de 5 transacciones por minuto
            SuspiciousActivity.objects.create(
                user_id=user_id,
                wallet=wallet,
                activity_type='high_frequency',
                details={
                    'transactions_last_minute': tx_count,
                    'timestamp': timezone.now().isoformat()
                }
            )
            logger.warning(f"⚠️ Actividad sospechosa detectada: usuario {user_id} - {tx_count} tx/min")

    # ==================== MÉTODOS PÚBLICOS ====================

    @staticmethod
    @db_transaction.atomic
    def deposit(
        wallet_id: int,
        amount: Decimal,
        description: str = "",
        created_by_id: Optional[int] = None,
        metadata: Optional[Dict] = None,
        idempotency_key: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Transaction:
        """
        DEP-01: Recarga de saldo (efectivo, código, transferencia)
        ✅ Con lock pesimista con nowait()
        ✅ Idempotencia garantizada con BD
        ✅ Cooldown entre operaciones
        """
        # 1. Validaciones FUERA del lock
        try:
            amount_decimal = WalletService._validate_amount(amount)
        except Exception as e:
            raise InvalidAmountError(str(e))

        if amount_decimal <= Decimal('0'):
            raise InvalidAmountError("El monto debe ser mayor a cero")

        # 2. Verificar idempotencia ANTES del lock
        if idempotency_key:
            existing_tx = WalletService._check_idempotency(idempotency_key, wallet_id)
            if existing_tx:
                logger.info(f"Idempotency hit: {idempotency_key}")
                return existing_tx

        # 3. Lock con nowait()
        try:
            wallet = Wallet.objects.select_for_update(nowait=True).get(id=wallet_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet {wallet_id} no encontrado")
        except OperationalError:
            raise ConcurrentModificationError("Sistema ocupado, reintente")

        # 4. Validaciones rápidas dentro del lock
        WalletService._validate_wallet(wallet)
        WalletService._check_cooldown(wallet)
        WalletService._check_daily_limit(wallet, amount_decimal, 'deposit')

        try:
            validate_max_balance(amount_decimal, wallet.available_balance)
        except Exception as e:
            raise LimitExceededError(str(e))

        # 5. Crear transacción
        expected_after = wallet.available_balance + amount_decimal

        tx = Transaction.objects.create(
            wallet=wallet,
            amount=amount_decimal,
            balance_before=wallet.available_balance,
            balance_after=expected_after,
            transaction_type='deposit',
            status='completed',
            metadata=metadata or {},
            description=description or f"Recarga de {amount_decimal} {wallet.currency}",
            created_by_id=created_by_id
        )

        # 6. Actualización atómica
        Wallet.objects.filter(id=wallet.id).update(
            available_balance=F('available_balance') + amount_decimal,
            total_deposited=F('total_deposited') + amount_decimal,
            version=F('version') + 1,
            updated_at=timezone.now()
        )

        # 7. Registrar idempotencia
        if idempotency_key:
            IdempotencyKey.objects.create(
                key=idempotency_key,
                wallet=wallet,
                transaction=tx
            )

        # 8. Audit log
        AuditLog.objects.create(
            user_id=created_by_id,
            action='DEPOSIT',
            entity_type='wallet',
            entity_id=wallet.id,
            before={'balance': float(wallet.available_balance)},
            after={'balance': float(wallet.available_balance + amount_decimal)},
            ip_address=ip_address,
            user_agent=user_agent
        )

        # 9. Detectar actividad sospechosa
        if created_by_id:
            WalletService._check_suspicious_activity(wallet, created_by_id)

        wallet.refresh_from_db()
        logger.info(f"✅ DEP-01: Depósito exitoso - ref:{tx.reference}")
        return tx

    @staticmethod
    @db_transaction.atomic
    def purchase_song(
        user_id: int,
        song_id: int,
        price: Optional[Decimal] = None,
        idempotency_key: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Transaction, Hold]:
        """
        PUR-01: Compra de canción
        ✅ Con lock pesimista con nowait()
        ✅ Validación de saldo antes de operar
        ✅ Idempotencia con BD
        """
        # 1. Obtener wallet
        wallet = WalletService.get_user_wallet(user_id)
        
        # 2. Verificar idempotencia ANTES del lock
        if idempotency_key:
            existing_tx = WalletService._check_idempotency(idempotency_key, wallet.id)
            if existing_tx:
                logger.info(f"Idempotency hit: {idempotency_key}")
                try:
                    hold = Hold.objects.get(transaction=existing_tx)
                    return existing_tx, hold
                except Hold.DoesNotExist:
                    return existing_tx, None

        # 3. Obtener canción (fuera del lock de wallet)
        try:
            from api2.models import Song
            song = Song.objects.get(id=song_id)
        except Exception as e:
            raise PurchaseFailedError(f"Canción no encontrada: {str(e)}")

        # 4. Determinar precio
        if price is None:
            if not hasattr(song, 'price') or song.price <= 0:
                raise PurchaseFailedError("Canción sin precio o gratuita")
            price = song.price

        try:
            price_decimal = Decimal(str(price))
        except (InvalidOperation, TypeError):
            raise InvalidAmountError("Precio inválido")

        if price_decimal < LIMITS['MIN_DEPOSIT']:
            raise InvalidAmountError(f"Precio mínimo: {LIMITS['MIN_DEPOSIT']} XAF")

        # 5. Lock con nowait()
        try:
            wallet = Wallet.objects.select_for_update(nowait=True).get(id=wallet.id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet no encontrado para usuario {user_id}")
        except OperationalError:
            raise ConcurrentModificationError("Sistema ocupado, reintente")

        WalletService._validate_wallet(wallet)
        WalletService._check_cooldown(wallet)

        # 6. Validar fondos
        if not wallet.can_afford(price_decimal):
            raise InsufficientFundsError(
                f"Saldo insuficiente. Necesitas {price_decimal} {wallet.currency}, "
                f"tienes {wallet.available_balance} {wallet.currency}"
            )

        WalletService._check_daily_limit(wallet, price_decimal, 'purchase')

        # 7. Calcular comisiones
        artist_share = (price_decimal * COMMISSIONS['ARTIST']).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        platform_share = price_decimal - artist_share

        artist = song.uploaded_by
        if not artist:
            raise PurchaseFailedError("La canción no tiene artista asociado")

        # 8. Crear transacción
        expected_after = wallet.available_balance - price_decimal

        tx = Transaction.objects.create(
            wallet=wallet,
            amount=-price_decimal,
            balance_before=wallet.available_balance,
            balance_after=expected_after,
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

        # 9. Crear hold
        hold = None
        if artist and artist_share > 0:
            hold = Hold.objects.create(
                transaction=tx,
                artist=artist,
                amount=artist_share,
                reason='song_purchase',
                notes=f"Compra de canción: {song.title}"
            )

        # 10. Actualizar wallet
        update_fields = {
            'available_balance': F('available_balance') - price_decimal,
            'total_spent': F('total_spent') + price_decimal,
            'version': F('version') + 1,
            'updated_at': timezone.now()
        }
        if artist:
            update_fields['pending_balance'] = F('pending_balance') + artist_share

        Wallet.objects.filter(id=wallet.id).update(**update_fields)

        # 11. Registrar idempotencia
        if idempotency_key:
            IdempotencyKey.objects.create(
                key=idempotency_key,
                wallet=wallet,
                transaction=tx
            )

        # 12. Audit log
        AuditLog.objects.create(
            user_id=user_id,
            action='PURCHASE',
            entity_type='wallet',
            entity_id=wallet.id,
            before={'balance': float(wallet.available_balance)},
            after={'balance': float(wallet.available_balance - price_decimal)},
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={'song_id': song_id, 'price': float(price_decimal)}
        )

        # 13. Detectar actividad sospechosa
        WalletService._check_suspicious_activity(wallet, user_id)

        wallet.refresh_from_db()
        logger.info(f"✅ PUR-01: Compra exitosa - ref:{tx.reference}")
        return tx, hold

    @staticmethod
    @db_transaction.atomic
    def release_hold(
        hold_id: int,
        released_by_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Transaction:
        """REL-01: Liberar hold a artista - CON VALIDACIÓN DE pending_balance"""
        # Lock con nowait()
        try:
            hold = Hold.objects.select_for_update(nowait=True).get(id=hold_id)
        except Hold.DoesNotExist:
            raise HoldNotFoundError(f"Hold {hold_id} no encontrado")
        except OperationalError:
            raise ConcurrentModificationError("Sistema ocupado, reintente")

        if hold.is_released:
            raise HoldAlreadyReleasedError("Este hold ya fue liberado")

        if not hold.can_release:
            days_left = hold.days_until_release
            raise HoldNotReleasableError(
                f"Hold no liberable aún. Faltan {days_left} días"
            )

        # Obtener wallet del artista con lock
        try:
            artist_wallet = Wallet.objects.select_for_update(nowait=True).get(user=hold.artist)
        except Wallet.DoesNotExist:
            artist_wallet = Wallet.objects.create(user=hold.artist, currency='XAF')
            logger.info(f"Wallet creado automáticamente para artista {hold.artist.id}")
        except OperationalError:
            raise ConcurrentModificationError("Sistema ocupado, reintente")

        WalletService._validate_wallet(artist_wallet)

        # Obtener wallet original con lock
        original_wallet = hold.transaction.wallet
        try:
            original_wallet = Wallet.objects.select_for_update(nowait=True).get(id=original_wallet.id)
        except OperationalError:
            raise ConcurrentModificationError("Sistema ocupado, reintente")

        # ✅ VALIDAR pending_balance ANTES de decrementar
        if original_wallet.pending_balance < hold.amount:
            raise InconsistentStateError(
                f"Inconsistencia: pending_balance ({original_wallet.pending_balance}) "
                f"< hold.amount ({hold.amount})"
            )

        # Crear transacción para el artista
        expected_after = artist_wallet.available_balance + hold.amount

        tx = Transaction.objects.create(
            wallet=artist_wallet,
            amount=hold.amount,
            balance_before=artist_wallet.available_balance,
            balance_after=expected_after,
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

        # Actualizar wallet del artista
        Wallet.objects.filter(id=artist_wallet.id).update(
            available_balance=F('available_balance') + hold.amount,
            total_withdrawn=F('total_withdrawn') + hold.amount,
            version=F('version') + 1,
            updated_at=timezone.now()
        )

        # Actualizar wallet original con validación en BD
        updated = Wallet.objects.filter(
            id=original_wallet.id,
            pending_balance__gte=hold.amount  # ✅ GARANTÍA en BD
        ).update(
            pending_balance=F('pending_balance') - hold.amount,
            updated_at=timezone.now()
        )

        if updated == 0:
            raise InconsistentStateError(
                "No se pudo actualizar pending_balance - inconsistencia detectada"
            )

        # Marcar hold como liberado
        hold.is_released = True
        hold.released_at = timezone.now()
        hold.released_by_id = released_by_id
        hold.save(update_fields=['is_released', 'released_at', 'released_by', 'updated_at'])

        # Audit log
        AuditLog.objects.create(
            user_id=released_by_id,
            action='RELEASE',
            entity_type='hold',
            entity_id=hold_id,
            before={'is_released': False, 'pending_balance': float(original_wallet.pending_balance)},
            after={'is_released': True, 'pending_balance': float(original_wallet.pending_balance - hold.amount)},
            ip_address=ip_address,
            user_agent=user_agent
        )

        artist_wallet.refresh_from_db()
        original_wallet.refresh_from_db()

        logger.info(f"✅ REL-01: Hold liberado - hold:{hold_id}")
        return tx

    @staticmethod
    @db_transaction.atomic
    def redeem_code(
        code: str,
        user_id: int,
        idempotency_key: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Transaction:
        """RED-01: Canjear código de recarga - ✅ Con lock pesimista"""
        wallet = WalletService.get_user_wallet(user_id)
        
        if idempotency_key:
            existing_tx = WalletService._check_idempotency(idempotency_key, wallet.id)
            if existing_tx:
                return existing_tx

        # Lock con nowait()
        try:
            deposit_code = DepositCode.objects.select_for_update(nowait=True).get(
                code=code.upper().strip()
            )
        except DepositCode.DoesNotExist:
            raise PurchaseFailedError("Código inválido")
        except OperationalError:
            raise ConcurrentModificationError("Sistema ocupado, reintente")

        if not deposit_code.is_valid:
            if deposit_code.is_used:
                raise PurchaseFailedError("Este código ya fue usado")
            if timezone.now() > deposit_code.expires_at:
                raise PurchaseFailedError("Este código ha expirado")
            raise PurchaseFailedError("Código inválido")

        tx = WalletService.deposit(
            wallet_id=wallet.id,
            amount=deposit_code.amount,
            description=f"Canje de código {deposit_code.code}",
            created_by_id=user_id,
            metadata={'code': deposit_code.code, 'code_id': deposit_code.id},
            idempotency_key=idempotency_key,
            ip_address=ip_address,
            user_agent=user_agent
        )

        deposit_code.mark_as_used(user_id)

        return tx

    @staticmethod
    @db_transaction.atomic
    def withdraw(
        wallet_id: int,
        amount: Decimal,
        description: str = "",
        created_by_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Transaction:
        """
        WDR-01: Retiro de saldo (solo para artistas verificados)
        ✅ Validación completa
        ✅ Con lock pesimista con nowait()
        """
        try:
            amount_decimal = WalletService._validate_amount(amount)
        except Exception as e:
            raise InvalidAmountError(str(e))

        if amount_decimal <= Decimal('0'):
            raise InvalidAmountError("El monto debe ser mayor a cero")

        # Lock con nowait()
        try:
            wallet = Wallet.objects.select_for_update(nowait=True).get(id=wallet_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet {wallet_id} no encontrado")
        except OperationalError:
            raise ConcurrentModificationError("Sistema ocupado, reintente")

        WalletService._validate_wallet(wallet)
        WalletService._check_cooldown(wallet)

        if not wallet.can_afford(amount_decimal):
            raise InsufficientFundsError(
                f"Saldo insuficiente. Necesitas {amount_decimal} {wallet.currency}, "
                f"tienes {wallet.available_balance} {wallet.currency}"
            )

        expected_after = wallet.available_balance - amount_decimal

        tx = Transaction.objects.create(
            wallet=wallet,
            amount=-amount_decimal,
            balance_before=wallet.available_balance,
            balance_after=expected_after,
            transaction_type='withdrawal',
            status='completed',
            description=description or f"Retiro de {amount_decimal} {wallet.currency}",
            created_by_id=created_by_id
        )

        Wallet.objects.filter(id=wallet.id).update(
            available_balance=F('available_balance') - amount_decimal,
            total_withdrawn=F('total_withdrawn') + amount_decimal,
            version=F('version') + 1,
            updated_at=timezone.now()
        )

        AuditLog.objects.create(
            user_id=created_by_id,
            action='WITHDRAWAL',
            entity_type='wallet',
            entity_id=wallet.id,
            before={'balance': float(wallet.available_balance)},
            after={'balance': float(wallet.available_balance - amount_decimal)},
            ip_address=ip_address,
            user_agent=user_agent
        )

        wallet.refresh_from_db()
        logger.info(f"✅ WDR-01: Retiro exitoso - ref:{tx.reference}")
        return tx

    # ==================== MÉTODOS DE CONSULTA ====================

    @staticmethod
    def get_balance(wallet_id: int, language: str = 'es') -> Dict[str, Any]:
        """CON-01: Obtener información de balance (datos crudos)"""
        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet {wallet_id} no encontrado")
        return wallet.get_balance_data()

    @staticmethod
    def get_transactions(
        wallet_id: int,
        limit: int = 50,
        transaction_type: Optional[str] = None
    ):
        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            raise WalletNotFoundError(f"Wallet {wallet_id} no encontrado")
        return wallet.get_transactions(limit, transaction_type)

    @staticmethod
    def get_artist_earnings(artist_id: int) -> Dict[str, Any]:
        from django.db.models import Sum
        
        total_held = Hold.objects.filter(
            artist_id=artist_id, is_released=False
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        total_released = Hold.objects.filter(
            artist_id=artist_id, is_released=True
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        upcoming_holds = Hold.objects.filter(
            artist_id=artist_id, is_released=False,
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
                    'song': None
                }
                for h in upcoming_holds[:10]
            ]
        }

    @staticmethod
    def get_user_wallet(user_id: int) -> Wallet:
        try:
            return Wallet.objects.get(user_id=user_id)
        except Wallet.DoesNotExist:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(id=user_id)
                currency = 'XAF'
                if hasattr(user, 'country'):
                    from .constants import COUNTRY_CURRENCY_MAP
                    currency = COUNTRY_CURRENCY_MAP.get(user.country, 'XAF')
                wallet = Wallet.objects.create(user=user, currency=currency)
                logger.info(f"Wallet creado automáticamente para usuario {user_id}")
                return wallet
            except User.DoesNotExist:
                raise WalletNotFoundError(f"Usuario {user_id} no encontrado")

    # ==================== MÉTODOS PRIVADOS ====================

    @staticmethod
    def _validate_amount(amount) -> Decimal:
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
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def _validate_wallet(wallet: Wallet):
        if not wallet.is_active:
            raise UnauthorizedWalletActionError("La wallet está desactivada")

    @staticmethod
    def _check_daily_limit(wallet: Wallet, amount: Decimal, tx_type: str):
        """Verificar límite diario con ventana de 24h REAL y CACHE"""
        
        cache_key = f"daily_limit:{wallet.id}:{tx_type}"
        last_24h = timezone.now() - timezone.timedelta(hours=24)
        
        # Intentar obtener del cache
        daily_total = cache.get(cache_key)
        
        if daily_total is None:
            # Calcular y cachear por 5 minutos
            daily_total = Transaction.objects.filter(
                wallet=wallet,
                transaction_type=tx_type,
                created_at__gte=last_24h,
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            cache.set(cache_key, float(daily_total), timeout=300)  # 5 minutos
        
        amount_abs = abs(amount)
        current_total = abs(Decimal(str(daily_total)))
        
        if current_total + amount_abs > wallet.daily_limit:
            raise LimitExceededError(
                f"Límite diario excedido. Usado en últimas 24h: {current_total} {wallet.currency}. "
                f"Límite: {wallet.daily_limit} {wallet.currency}"
            )
        
# wallet/services.py - REEMPLAZAR OfficeWithdrawalService COMPLETO

class OfficeWithdrawalService:
    """Servicio para gestión de retiros en oficina - VERSIÓN PRODUCCIÓN"""
    
    @staticmethod
    def _generate_idempotency_key(artist_id: int, amount: Decimal, office_id: int) -> str:
        """Generar clave de idempotencia única"""
        import hashlib
        data = f"{artist_id}:{amount}:{office_id}:{timezone.now().timestamp()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    @staticmethod
    def search_artist(search_term: str) -> dict:
        """
        Buscar artista por email o teléfono
        SOLO para personal de oficina autenticado
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        search_term = search_term.strip().lower()
        
        # Buscar por email o teléfono
        artist = User.objects.filter(
            Q(email__iexact=search_term) |
            Q(phone__iexact=search_term) |
            Q(username__iexact=search_term)
        ).first()
        
        if not artist:
            return {
                'found': False,
                'message': 'Artista no encontrado. Verifique el email o teléfono.'
            }
        
        # Obtener wallet
        try:
            wallet = Wallet.objects.get(user=artist)
        except Wallet.DoesNotExist:
            return {
                'found': False,
                'message': 'El artista no tiene wallet configurado.'
            }
        
        # Obtener cuenta Muni si existe
        muni_account = None
        try:
            muni = ArtistMuniAccount.objects.get(artist=artist)
            muni_account = {
                'phone': muni.phone_number,
                'is_verified': muni.is_verified
            }
        except ArtistMuniAccount.DoesNotExist:
            pass
        
        return {
            'found': True,
            'artist': {
                'id': artist.id,
                'name': artist.get_full_name() or artist.username,
                'email': artist.email,
                'phone': getattr(artist, 'phone', 'No registrado'),
            },
            'wallet': {
                'balance': float(wallet.available_balance),
                'currency': wallet.currency,
                'total_earned': float(wallet.total_deposited),
                'total_withdrawn': float(wallet.total_withdrawn),
            },
            'muni_account': muni_account,
            'recent_withdrawals': [
                {
                    'reference': w.reference,
                    'amount': float(w.amount),
                    'method': w.get_withdrawal_method_display(),
                    'date': w.paid_at.isoformat() if w.paid_at else None,
                    'office': w.office.name
                }
                for w in OfficeWithdrawal.objects.filter(
                    artist=artist, 
                    status='completed'
                ).order_by('-paid_at')[:5]
            ]
        }
    
    @staticmethod
    def get_withdrawal_fee(amount: Decimal, method: str) -> Decimal:
        """Calcular comisión según método de retiro"""
        if method == 'cash':
            fee_percentage = Decimal('0.005')  # 0.5%
        elif method == 'muni':
            fee_percentage = Decimal('0.003')  # 0.3%
        else:
            fee_percentage = Decimal('0.01')
        
        fee = (amount * fee_percentage).quantize(Decimal('0.01'))
        return fee
    
    @staticmethod
    @db_transaction.atomic
    def process_withdrawal(
        artist_id: int,
        amount: Decimal,
        office_id: int,
        staff_id: int,
        withdrawal_method: str,
        id_number_verified: str,
        id_type: str = 'dni',
        muni_phone: str = None,
        notes: str = None,
        ip_address: str = None,
        idempotency_key: str = None
    ) -> OfficeWithdrawal:
        """
        Procesar retiro completo en oficina
        ✅ Con lock pesimista select_for_update()
        ✅ Con idempotencia
        ✅ Validación DENTRO de la transacción
        ✅ Cache de totales diarios
        """
        
        # ============================================================
        # 1. IDEMPOTENCIA - Verificar si ya se procesó
        # ============================================================
        if idempotency_key:
            existing = OfficeWithdrawal.objects.filter(
                idempotency_key=idempotency_key
            ).select_related('artist', 'office').first()
            
            if existing:
                logger.info(f"Idempotency hit: {idempotency_key} -> {existing.reference}")
                return existing
        
        # ============================================================
        # 2. LOCK PESIMISTA EN WALLET - DENTRO de la transacción
        # ============================================================
        try:
            wallet = Wallet.objects.select_for_update(nowait=True).get(user_id=artist_id)
        except Wallet.DoesNotExist:
            raise ValueError('Artista no tiene wallet configurado')
        except OperationalError:
            raise ConcurrentModificationError('Sistema ocupado. Reintente en unos segundos.')
        
        # ============================================================
        # 3. VALIDACIONES (TODAS dentro del lock)
        # ============================================================
        
        # Validar monto
        if amount <= 0:
            raise InvalidAmountError('El monto debe ser mayor a cero')
        
        if amount < Decimal('1000'):
            raise InvalidAmountError('El monto mínimo de retiro es 1,000 XAF')
        
        # Validar saldo
        if wallet.available_balance < amount:
            raise InsufficientFundsError(
                f'Saldo insuficiente. Disponible: {wallet.available_balance:,.0f} XAF'
            )
        
        # Validar oficina
        try:
            office = Office.objects.select_for_update().get(id=office_id, is_active=True)
        except Office.DoesNotExist:
            raise ValueError('Oficina no válida')
        
        # Resetear cache diario si es necesario
        office.reset_daily_cache_if_needed()
        
        # Validar límite por retiro
        if amount > office.max_withdrawal_per_artist:
            raise LimitExceededError(
                f'Máximo por retiro: {office.max_withdrawal_per_artist:,.0f} XAF'
            )
        
        # Validar límite diario de oficina (usando cache)
        if office.today_withdrawn_cached + amount > office.daily_cash_limit:
            remaining = office.daily_cash_limit - office.today_withdrawn_cached
            raise LimitExceededError(
                f'Límite diario de oficina alcanzado. Restante hoy: {remaining:,.0f} XAF'
            )
        
        # Validar límite diario del artista
        today = timezone.now().date()
        artist_today_withdrawals = OfficeWithdrawal.objects.filter(
            artist_id=artist_id,
            paid_at__date=today,
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        max_daily_artist = Decimal('500000.00')
        if artist_today_withdrawals + amount > max_daily_artist:
            remaining = max_daily_artist - artist_today_withdrawals
            raise LimitExceededError(
                f'Límite diario del artista alcanzado. Puede retirar hasta {remaining:,.0f} XAF hoy'
            )
        
        # Validar personal de oficina
        try:
            staff = OfficeStaff.objects.select_for_update().get(
                id=staff_id,
                office_id=office_id,
                is_active=True
            )
        except OfficeStaff.DoesNotExist:
            raise ValueError('Personal de oficina no autorizado')
        
        # Validar límite diario del empleado
        if staff.today_operations_total + amount > staff.daily_operation_limit:
            raise LimitExceededError('Límite diario del empleado alcanzado')
        
        # Validar método de pago
        if withdrawal_method == 'muni':
            if not muni_phone:
                raise ValueError('Para retiro por Muni Dinero debe proporcionar número de teléfono')
        
        # ============================================================
        # 4. CALCULAR COMISIÓN
        # ============================================================
        fee = OfficeWithdrawalService.get_withdrawal_fee(amount, withdrawal_method)
        net_amount = amount - fee
        
        # ============================================================
        # 5. REGISTRAR SALDOS ANTES (para auditoría)
        # ============================================================
        balance_before = wallet.available_balance
        
        # ============================================================
        # 6. ACTUALIZAR WALLET (usando F para atomicidad)
        # ============================================================
        Wallet.objects.filter(id=wallet.id).update(
            available_balance=F('available_balance') - amount,
            total_withdrawn=F('total_withdrawn') + amount,
            updated_at=timezone.now()
        )
        
        # Refrescar para auditoría correcta
        wallet.refresh_from_db()
        
        # ============================================================
        # 7. ACTUALIZAR CACHE DE OFICINA
        # ============================================================
        Office.objects.filter(id=office.id).update(
            today_withdrawn_cached=F('today_withdrawn_cached') + amount,
            updated_at=timezone.now()
        )
        
        # ============================================================
        # 8. CREAR REGISTRO DE RETIRO
        # ============================================================
        # Generar idempotency key si no vino
        if not idempotency_key:
            idempotency_key = OfficeWithdrawalService._generate_idempotency_key(
                artist_id, amount, office_id
            )
        
        withdrawal = OfficeWithdrawal.objects.create(
            artist_id=artist_id,
            wallet=wallet,
            office=office,
            processed_by=staff,
            amount=amount,
            fee=fee,
            net_amount=net_amount,
            withdrawal_method=withdrawal_method,
            muni_phone=muni_phone or '',
            status='completed',  # En oficina es inmediato
            id_number_verified=id_number_verified,
            id_type_verified=id_type,
            receipt_signed=True,
            notes=notes or '',
            paid_at=timezone.now(),
            idempotency_key=idempotency_key
        )
        
        # ============================================================
        # 9. ACTUALIZAR ÚLTIMA ACTIVIDAD DEL EMPLEADO
        # ============================================================
        OfficeStaff.objects.filter(id=staff.id).update(last_activity_at=timezone.now())
        
        # ============================================================
        # 10. AUDIT LOG (con valores correctos)
        # ============================================================
        AuditLog.objects.create(
            user_id=artist_id,
            action='OFFICE_WITHDRAWAL',
            entity_type='office_withdrawal',
            entity_id=withdrawal.id,
            before={'available_balance': float(balance_before)},
            after={'available_balance': float(wallet.available_balance)},
            ip_address=ip_address or 'OFFICE_SYSTEM',
            user_agent='OFFICE_DASHBOARD',
            metadata={
                'office': office.name,
                'staff': staff.user.username,
                'amount': float(amount),
                'fee': float(fee),
                'method': withdrawal_method,
                'idempotency_key': idempotency_key[:16] + '...',
                'id_verified': id_number_verified[-4:]
            }
        )
        
        # ============================================================
        # 11. ACTUALIZAR CUENTA MUNI SI CORRESPONDE
        # ============================================================
        if withdrawal_method == 'muni' and muni_phone:
            ArtistMuniAccount.objects.update_or_create(
                artist_id=artist_id,
                defaults={
                    'phone_number': muni_phone,
                    'is_default': True
                }
            )
        
        logger.info(
            f"🏦 Retiro en oficina: {withdrawal.reference} - {amount} XAF - {office.name}",
            extra={
                'withdrawal_id': withdrawal.id,
                'artist_id': artist_id,
                'office_id': office_id,
                'staff_id': staff_id,
                'method': withdrawal_method
            }
        )
        
        return withdrawal
    
    @staticmethod
    def get_office_dashboard_stats(office_id: int, staff_id: int = None) -> dict:
        """Estadísticas del dashboard de oficina - usando cache"""
        today = timezone.now().date()
        
        # Usar el método cacheado de la oficina
        office = Office.objects.get(id=office_id)
        office.reset_daily_cache_if_needed()
        
        # Estadísticas del día (usando valores cacheados cuando sea posible)
        today_withdrawals = OfficeWithdrawal.objects.filter(
            office_id=office_id,
            paid_at__date=today,
            status='completed'
        )
        
        cash_withdrawals = today_withdrawals.filter(withdrawal_method='cash')
        muni_withdrawals = today_withdrawals.filter(withdrawal_method='muni')
        
        # Top artistas del día
        top_artists = today_withdrawals.values(
            'artist__username', 'artist__email'
        ).annotate(
            total=Sum('amount')
        ).order_by('-total')[:10]
        
        # Actividad por empleado
        staff_activity = OfficeWithdrawal.objects.filter(
            office_id=office_id,
            paid_at__date=today,
            status='completed'
        ).values(
            'processed_by__user__username'
        ).annotate(
            count=Count('id'),
            total=Sum('amount')
        ).order_by('-total')
        
        return {
            'office': {
                'name': office.name,
                'address': office.address,
                'phone': office.phone,
                'daily_limit': float(office.daily_cash_limit),
                'used_today': float(office.today_withdrawn_cached),
                'remaining': float(office.remaining_daily_limit)
            },
            'today_stats': {
                'total_withdrawals': today_withdrawals.count(),
                'total_amount': float(today_withdrawals.aggregate(total=Sum('amount'))['total'] or 0),
                'cash_count': cash_withdrawals.count(),
                'cash_amount': float(cash_withdrawals.aggregate(total=Sum('amount'))['total'] or 0),
                'muni_count': muni_withdrawals.count(),
                'muni_amount': float(muni_withdrawals.aggregate(total=Sum('amount'))['total'] or 0),
                'average_amount': float(today_withdrawals.aggregate(avg=Avg('amount'))['avg'] or 0)
            },
            'top_artists': [
                {
                    'username': item['artist__username'],
                    'email': item['artist__email'],
                    'total': float(item['total'])
                }
                for item in top_artists
            ],
            'staff_activity': [
                {
                    'staff_name': item['processed_by__user__username'],
                    'count': item['count'],
                    'total': float(item['total'])
                }
                for item in staff_activity
            ]
        }
    
    @staticmethod
    def reverse_withdrawal(withdrawal_id: int, admin_id: int, reason: str) -> dict:
        """
        Reversar un retiro (en caso de error)
        Devuelve los fondos al artista
        """
        with db_transaction.atomic():
            try:
                withdrawal = OfficeWithdrawal.objects.select_for_update().get(id=withdrawal_id)
            except OfficeWithdrawal.DoesNotExist:
                raise ValueError('Retiro no encontrado')
            
            if withdrawal.status != 'completed':
                raise ValueError(f'Solo se pueden reversar retiros completados. Estado actual: {withdrawal.status}')
            
            # Obtener wallet con lock
            wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
            
            # Devolver fondos
            Wallet.objects.filter(id=wallet.id).update(
                available_balance=F('available_balance') + withdrawal.amount,
                total_withdrawn=F('total_withdrawn') - withdrawal.amount,
                updated_at=timezone.now()
            )
            
            # Actualizar estado
            withdrawal.status = 'reversed'
            withdrawal.notes = f"{withdrawal.notes}\nREVERSADO: {reason} por admin {admin_id}"
            withdrawal.save()
            
            # Auditoría
            AuditLog.objects.create(
                user_id=admin_id,
                action='WITHDRAWAL_REVERSED',
                entity_type='office_withdrawal',
                entity_id=withdrawal.id,
                before={'status': 'completed'},
                after={'status': 'reversed'},
                metadata={'reason': reason, 'amount': float(withdrawal.amount)}
            )
            
            # Actualizar cache de oficina (restar del total diario)
            office = Office.objects.get(id=withdrawal.office_id)
            office.reset_daily_cache_if_needed()
            Office.objects.filter(id=office.id).update(
                today_withdrawn_cached=F('today_withdrawn_cached') - withdrawal.amount
            )
            
            logger.warning(f"🔄 Retiro reversado: {withdrawal.reference} - Razón: {reason}")
            
            return {
                'success': True,
                'withdrawal_id': withdrawal.id,
                'reference': withdrawal.reference,
                'amount_reversed': float(withdrawal.amount),
                'reason': reason
            }