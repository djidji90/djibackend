# wallet/views.py
# ============================================
# VERSIÓN PRODUCCIÓN READY
# ============================================

# ============================================
# IMPORTS
# ============================================

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.core.cache import cache
from decimal import Decimal
import logging
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection

from .models import (
    Wallet, Transaction, Hold, DepositCode, Agent, PhysicalLocation,
    Office, OfficeStaff, OfficeWithdrawal, ArtistMuniAccount
)
from .services import WalletService, OfficeWithdrawalService
from .serializers import (
    WalletSerializer,
    WalletCreateSerializer,
    WalletBalanceSerializer,
    OfficeWithdrawalSerializer,
    OfficeWithdrawalHistorySerializer,
    TransactionSerializer,
    DepositSerializer,
    PurchaseSerializer,
    RefundSerializer,
    HoldSerializer,
    HoldReleaseSerializer,
    DepositCodeSerializer,
    DepositCodeCreateSerializer,
    DepositCodeRedeemSerializer,
    WalletBalanceResponseSerializer,
    ArtistEarningsSerializer,
    TransactionListSerializer,
    WalletAdminSerializer,
    TransactionAdminSerializer,
    AgentSerializer,
    AgentCreateSerializer,
    PhysicalLocationSerializer,
    AgentDepositSerializer,
    AgentGenerateCodeSerializer,
    AgentSearchUserSerializer,
    RedeemCodeSerializer,
    AgentEarningsSerializer,
)
from .permissions import (
    IsWalletOwner, IsArtist, IsAgent, IsAdminOrReadOnly,
    CanWithdrawFunds, IsAgentOrAdmin
)
from .pagination import WalletPagination, TransactionPagination
from .filters import TransactionFilter, HoldFilter, DepositCodeFilter
from .throttles import (
    WalletOperationThrottle,
    SensitiveOperationThrottle,
    WithdrawalThrottle,
    DepositThrottle,
    AnonymousWalletThrottle
)
from .exceptions import WalletBaseException
from .utils import generate_qr_for_code, calculate_agent_commission

logger = logging.getLogger(__name__)
User = get_user_model()


# ============================================
# UTILITY FUNCTIONS
# ============================================

def _get_client_ip(request):
    """Obtener IP real del cliente"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def _get_idempotency_key(request, prefix, *args):
    """Obtener o generar clave de idempotencia"""
    key = request.headers.get('X-Idempotency-Key')
    if not key:
        key = WalletService._generate_idempotency_key(prefix, *args)
    return key


def _validate_content_type(request):
    """Validar Content-Type"""
    if request.content_type != 'application/json':
        return Response(
            {'error': 'Content-Type must be application/json'},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
    return None


# ============================================
# CORE WALLET VIEWS
# ============================================

class WalletBalanceView(APIView):
    """
    GET /api/wallet/balance/
    Obtener balance del wallet del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request):
        cache_key = f"wallet_balance:{request.user.id}"
        balance_data = cache.get(cache_key)
        
        if not balance_data:
            wallet = WalletService.get_user_wallet(request.user.id)
            balance_data = wallet.get_balance_data()
            cache.set(cache_key, balance_data, timeout=60)
        
        language = request.GET.get('lang', 'es')
        serializer = WalletBalanceResponseSerializer(
            balance_data,
            context={'language': language}
        )
        return Response(serializer.data)


class TransactionHistoryView(generics.ListAPIView):
    """
    GET /api/wallet/transactions/
    Listar transacciones del usuario.
    """
    permission_classes = [IsAuthenticated, IsWalletOwner]
    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination
    filterset_class = TransactionFilter
    throttle_classes = [WalletOperationThrottle]

    def get_queryset(self):
        wallet = WalletService.get_user_wallet(self.request.user.id)
        return Transaction.objects.filter(wallet=wallet).select_related('wallet__user')


class TransactionDetailView(generics.RetrieveAPIView):
    """
    GET /api/wallet/transactions/<reference>/
    Detalle de una transacción específica.
    """
    permission_classes = [IsAuthenticated, IsWalletOwner]
    serializer_class = TransactionSerializer
    lookup_field = 'reference'
    throttle_classes = [WalletOperationThrottle]

    def get_queryset(self):
        wallet = WalletService.get_user_wallet(self.request.user.id)
        return Transaction.objects.filter(wallet=wallet)


class UserDepositView(APIView):
    """
    POST /api/wallet/deposit/
    Depósito para usuarios normales.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DepositThrottle]

    def post(self, request):
        return Response(
            {
                'error': 'use_redeem_endpoint',
                'message': 'Para recargar saldo, usa /api/wallet/redeem/ con un código de recarga',
                'redeem_endpoint': '/api/wallet/redeem/'
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class RedeemCodeView(APIView):
    """
    POST /api/wallet/redeem/
    Canjear un código de recarga.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveOperationThrottle]

    def post(self, request):
        content_type_error = _validate_content_type(request)
        if content_type_error:
            return content_type_error

        serializer = DepositCodeRedeemSerializer(
            data=request.data,
            context={'request': request}
        )

        if serializer.is_valid():
            idempotency_key = _get_idempotency_key(
                request, 'redeem', request.user.id, serializer.validated_data['code']
            )
            
            try:
                transaction = WalletService.redeem_code(
                    code=serializer.validated_data['code'],
                    user_id=request.user.id,
                    idempotency_key=idempotency_key,
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                cache.delete(f"wallet_balance:{request.user.id}")
                
                return Response({
                    'success': True,
                    'reference': transaction.reference,
                    'amount': float(transaction.amount),
                    'new_balance': float(transaction.wallet.available_balance),
                    'message': f"Código canjeado con éxito. Se añadieron {transaction.amount} {transaction.wallet.currency}"
                }, status=status.HTTP_200_OK)
                
            except WalletBaseException as e:
                return Response(
                    {'error': e.detail, 'code': e.code},
                    status=e.status_code
                )
            except Exception as e:
                logger.error(f"RedeemCodeView error: {e}", extra={
                    'user_id': request.user.id,
                    'code': serializer.validated_data.get('code', 'unknown'),
                })
                return Response(
                    {'error': 'Error interno al canjear el código'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# PURCHASE VIEWS
# ============================================

class PurchaseSongView(APIView):
    """
    POST /api/wallet/songs/<int:song_id>/purchase/
    Comprar una canción.
    ✅ Con throttle de producción (30/minute)
    ✅ Con idempotencia
    ✅ Con auditoría
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveOperationThrottle]

    def get(self, request, song_id):
        """Verificar estado de compra de una canción"""
        try:
            from api2.models import Song
            
            song = Song.objects.get(id=song_id)
            
            has_purchased = Transaction.objects.filter(
                wallet__user=request.user,
                transaction_type='purchase',
                metadata__song_id=song_id,
                status='completed'
            ).exists()
            
            return Response({
                'song_id': song_id,
                'title': song.title,
                'has_purchased': has_purchased,
                'price': float(song.price) if hasattr(song, 'price') else None,
                'is_purchasable': getattr(song, 'is_purchasable', True)
            })
            
        except Exception as e:
            logger.error(f"PurchaseSongView GET error: {e}")
            return Response(
                {'error': 'Error al verificar estado de compra'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @transaction.atomic
    def post(self, request, song_id):
        content_type_error = _validate_content_type(request)
        if content_type_error:
            return content_type_error

        serializer = PurchaseSerializer(
            data={'song_id': song_id, **request.data},
            context={'request': request}
        )

        if serializer.is_valid():
            idempotency_key = _get_idempotency_key(
                request, 'purchase', request.user.id, song_id
            )
            
            try:
                from api2.models import Song
                
                song = Song.objects.get(id=song_id)
                price = serializer.validated_data.get('price')
                
                if not price:
                    price = song.price if hasattr(song, 'price') else None

                if not price or price <= 0:
                    return Response(
                        {'error': 'Esta canción no tiene precio válido'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                transaction, hold = WalletService.purchase_song(
                    user_id=request.user.id,
                    song_id=song_id,
                    price=price,
                    idempotency_key=idempotency_key,
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )

                cache.delete(f"wallet_balance:{request.user.id}")

                # Log de auditoría para compliance
                logger.info(f"Purchase completed: user={request.user.id}, song={song_id}, amount={price}, reference={transaction.reference}")

                return Response({
                    'success': True,
                    'reference': transaction.reference,
                    'amount': float(transaction.absolute_amount),
                    'new_balance': float(transaction.wallet.available_balance),
                    'hold_id': hold.id if hold else None,
                    'message': f"Compra de '{song.title}' realizada con éxito"
                }, status=status.HTTP_200_OK)

            except WalletBaseException as e:
                return Response(
                    {'error': e.detail, 'code': e.code},
                    status=e.status_code
                )
            except Exception as e:
                logger.error(f"PurchaseSongView error: {e}", extra={
                    'user_id': request.user.id,
                    'song_id': song_id,
                })
                return Response(
                    {'error': 'Error interno al procesar la compra'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserPurchasesView(generics.ListAPIView):
    """
    GET /api/wallet/purchases/
    Ver compras realizadas por el usuario.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination
    throttle_classes = [WalletOperationThrottle]

    def get_queryset(self):
        wallet = WalletService.get_user_wallet(self.request.user.id)
        return Transaction.objects.filter(
            wallet=wallet,
            transaction_type='purchase'
        ).select_related('wallet__user')


# ============================================
# ARTIST VIEWS
# ============================================

class ArtistEarningsView(APIView):
    """
    GET /api/wallet/artist/earnings/
    Ver ganancias del artista autenticado.
    """
    permission_classes = [IsAuthenticated, IsArtist]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request):
        cache_key = f"artist_earnings:{request.user.id}"
        earnings = cache.get(cache_key)
        
        if not earnings:
            earnings = WalletService.get_artist_earnings(request.user.id)
            cache.set(cache_key, earnings, timeout=300)
        
        serializer = ArtistEarningsSerializer(earnings)
        return Response(serializer.data)


class ArtistHoldsView(generics.ListAPIView):
    """
    GET /api/wallet/artist/holds/
    Ver holds pendientes del artista.
    """
    permission_classes = [IsAuthenticated, IsArtist]
    serializer_class = HoldSerializer
    pagination_class = WalletPagination
    filterset_class = HoldFilter
    throttle_classes = [WalletOperationThrottle]

    def get_queryset(self):
        return Hold.objects.filter(
            artist=self.request.user
        ).select_related('artist', 'transaction__wallet__user').order_by('-created_at')


# ============================================
# ADMIN HOLDS VIEWS
# ============================================

class ReleaseHoldView(APIView):
    """
    POST /api/wallet/admin/holds/release/
    Liberar un hold (solo admin).
    """
    permission_classes = [IsAuthenticated, CanWithdrawFunds]
    throttle_classes = [SensitiveOperationThrottle]

    @transaction.atomic
    def post(self, request):
        content_type_error = _validate_content_type(request)
        if content_type_error:
            return content_type_error

        serializer = HoldReleaseSerializer(data=request.data)

        if serializer.is_valid():
            try:
                transaction = WalletService.release_hold(
                    hold_id=serializer.validated_data['hold_id'],
                    released_by_id=request.user.id,
                    ip_address=_get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                logger.info(f"Hold released: hold_id={serializer.validated_data['hold_id']}, by={request.user.id}")
                
                return Response({
                    'success': True,
                    'reference': transaction.reference,
                    'amount': float(transaction.amount),
                    'message': "Hold liberado con éxito"
                }, status=status.HTTP_200_OK)
                
            except WalletBaseException as e:
                return Response(
                    {'error': e.detail, 'code': e.code},
                    status=e.status_code
                )
            except Exception as e:
                logger.error(f"ReleaseHoldView error: {e}")
                return Response(
                    {'error': 'Error interno al liberar el hold'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# DEPOSIT CODE VIEWS
# ============================================

class DepositCodeListView(generics.ListCreateAPIView):
    """
    GET/POST /api/wallet/codes/
    Listar/Crear códigos de recarga (solo admin/agentes).
    """
    permission_classes = [IsAuthenticated, IsAgent]
    serializer_class = DepositCodeSerializer
    pagination_class = WalletPagination
    filterset_class = DepositCodeFilter
    throttle_classes = [WalletOperationThrottle]

    def get_queryset(self):
        return DepositCode.objects.all().select_related('created_by', 'used_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        logger.info(f"Deposit code created: by={self.request.user.id}")


class DepositCodeDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/wallet/codes/<pk>/
    Ver/Actualizar código (solo admin/agentes).
    """
    permission_classes = [IsAuthenticated, IsAgent]
    serializer_class = DepositCodeSerializer
    queryset = DepositCode.objects.all()
    lookup_field = 'pk'
    throttle_classes = [WalletOperationThrottle]


class CodeQRView(APIView):
    """
    GET /api/wallet/codes/<code>/qr/
    Obtener código QR para un código de recarga.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request, code):
        try:
            deposit_code = DepositCode.objects.get(code=code.upper())

            is_creator = request.user == deposit_code.created_by
            is_admin = request.user.is_staff

            if not (is_creator or is_admin):
                return Response(
                    {"error": "permission_denied", "message": "No tienes permiso para ver este código"},
                    status=status.HTTP_403_FORBIDDEN
                )

            qr_base64 = generate_qr_for_code(
                deposit_code.code,
                deposit_code.amount,
                deposit_code.currency
            )

            return Response({
                'code': deposit_code.code,
                'amount': float(deposit_code.amount),
                'currency': deposit_code.currency,
                'expires_at': deposit_code.expires_at.isoformat(),
                'is_used': deposit_code.is_used,
                'qr_image': qr_base64,
                'qr_data': f"DJIMUSIC://REDEEM?code={deposit_code.code}&amount={deposit_code.amount}&currency={deposit_code.currency}"
            })

        except DepositCode.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Código no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error generating QR for code {code}: {e}")
            return Response(
                {"error": "internal_error", "message": "Error generando código QR"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================
# AGENT SYSTEM VIEWS
# ============================================

class AgentDashboardView(APIView):
    """
    GET /api/wallet/agent/dashboard/
    Dashboard del agente.
    """
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request):
        try:
            agent = Agent.objects.select_related('user', 'location').get(user=request.user)

            if not agent.is_active:
                return Response(
                    {"error": "agent_inactive", "message": "Tu cuenta de agente está inactiva"},
                    status=status.HTTP_403_FORBIDDEN
                )

            daily_stats = agent.get_daily_stats()

            recent_deposits = Transaction.objects.filter(
                created_by=request.user,
                transaction_type='deposit',
                status='completed'
            ).select_related('wallet__user').order_by('-created_at')[:10]

            codes_today = DepositCode.objects.filter(
                created_by=request.user,
                created_at__date=timezone.now().date()
            ).count()

            return Response({
                'agent': AgentSerializer(agent).data,
                'daily_stats': {
                    'deposits_count': daily_stats['count'],
                    'deposits_total': daily_stats['total'],
                    'deposit_limit_remaining': daily_stats['remaining'],
                    'codes_generated_today': codes_today,
                    'limit_reached': daily_stats['limit_reached']
                },
                'recent_deposits': [
                    {
                        'reference': tx.reference,
                        'amount': float(tx.amount),
                        'user': tx.wallet.user.username,
                        'user_id': tx.wallet.user.id,
                        'user_email': tx.wallet.user.email,
                        'created_at': tx.created_at.isoformat()
                    }
                    for tx in recent_deposits
                ],
                'limits': {
                    'daily_limit': float(agent.daily_deposit_limit),
                    'per_transaction': float(agent.max_deposit_per_transaction),
                    'used_today': daily_stats['total'],
                    'remaining': daily_stats['remaining']
                }
            })

        except Agent.DoesNotExist:
            return Response(
                {"error": "not_agent", "message": "No tienes permisos de agente"},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error in AgentDashboardView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al cargar dashboard"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentDepositView(APIView):
    """
    POST /api/wallet/agent/deposit/
    Realizar una recarga como agente.
    """
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [DepositThrottle]

    @transaction.atomic
    def post(self, request):
        content_type_error = _validate_content_type(request)
        if content_type_error:
            return content_type_error

        try:
            agent = Agent.objects.get(user=request.user)

            if not agent.is_active:
                return Response(
                    {"error": "agent_inactive", "message": "Tu cuenta de agente está inactiva"},
                    status=status.HTTP_403_FORBIDDEN
                )

            serializer = AgentDepositSerializer(
                data=request.data,
                context={'agent': agent}
            )

            if serializer.is_valid():
                idempotency_key = _get_idempotency_key(
                    request, 'agent_deposit', request.user.id, 
                    serializer.validated_data.get('user_id'), 
                    serializer.validated_data.get('amount')
                )
                
                serializer.context['idempotency_key'] = idempotency_key
                serializer.context['ip_address'] = _get_client_ip(request)
                serializer.context['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
                
                result = serializer.save()
                
                cache.delete(f"wallet_balance:{serializer.validated_data['user_id']}")
                
                logger.info(f"Agent deposit: agent={request.user.id}, user={serializer.validated_data['user_id']}, amount={serializer.validated_data['amount']}")
                
                return Response(result, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Agent.DoesNotExist:
            return Response(
                {"error": "not_agent", "message": "No tienes permisos de agente"},
                status=status.HTTP_403_FORBIDDEN
            )
        except WalletBaseException as e:
            return Response(
                {'error': e.detail, 'code': e.code},
                status=e.status_code
            )
        except Exception as e:
            logger.error(f"Error in AgentDepositView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al procesar la recarga"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentGenerateCodeView(APIView):
    """
    POST /api/wallet/agent/generate-code/
    Generar códigos de recarga (agentes y admin).
    """
    permission_classes = [IsAuthenticated, IsAgentOrAdmin]
    throttle_classes = [SensitiveOperationThrottle]

    @transaction.atomic
    def post(self, request):
        content_type_error = _validate_content_type(request)
        if content_type_error:
            return content_type_error

        try:
            agent = Agent.objects.get(user=request.user)

            if not agent.is_active:
                return Response(
                    {"error": "agent_inactive", "message": "Tu cuenta de agente está inactiva"},
                    status=status.HTTP_403_FORBIDDEN
                )

            serializer = AgentGenerateCodeSerializer(
                data=request.data,
                context={'agent': agent}
            )

            if serializer.is_valid():
                idempotency_key = _get_idempotency_key(
                    request, 'generate_codes', request.user.id,
                    serializer.validated_data.get('amount'),
                    serializer.validated_data.get('quantity')
                )
                
                serializer.context['idempotency_key'] = idempotency_key
                result = serializer.save()
                
                logger.info(f"Codes generated: by={request.user.id}, quantity={serializer.validated_data.get('quantity')}, amount={serializer.validated_data.get('amount')}")
                
                return Response(result, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Agent.DoesNotExist:
            if request.user.is_staff:
                serializer = AgentGenerateCodeSerializer(data=request.data)
                if serializer.is_valid():
                    amount = serializer.validated_data['amount']
                    quantity = serializer.validated_data['quantity']
                    currency = serializer.validated_data['currency']
                    expires_days = serializer.validated_data['expires_days']

                    codes = []
                    for _ in range(quantity):
                        code = f"{currency}{secrets.token_hex(4).upper()}"
                        while DepositCode.objects.filter(code=code).exists():
                            code = f"{currency}{secrets.token_hex(4).upper()}"

                        deposit_code = DepositCode.objects.create(
                            code=code,
                            amount=amount,
                            currency=currency,
                            created_by=request.user,
                            expires_at=timezone.now() + timedelta(days=expires_days),
                            notes=f"Generado por admin {request.user.username}"
                        )
                        codes.append(deposit_code)

                    logger.info(f"Admin codes generated: by={request.user.id}, quantity={quantity}")
                    
                    return Response({
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
                        'count': len(codes)
                    }, status=status.HTTP_201_CREATED)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response(
                {"error": "not_agent", "message": "No tienes permisos para generar códigos"},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error in AgentGenerateCodeView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al generar códigos"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentSearchUserView(APIView):
    """
    GET /api/wallet/agent/search/?query=...
    Buscar usuarios para recarga (agentes).
    """
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request):
        try:
            agent = Agent.objects.get(user=request.user)

            if not agent.is_active:
                return Response(
                    {"error": "agent_inactive", "message": "Tu cuenta de agente está inactiva"},
                    status=status.HTTP_403_FORBIDDEN
                )

            serializer = AgentSearchUserSerializer(data=request.query_params)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            query = serializer.validated_data['query'].lower()
            
            cache_key = f"user_search:{hash(query)}"
            results = cache.get(cache_key)
            
            if not results:
                users = User.objects.filter(
                    Q(email__icontains=query) |
                    Q(username__icontains=query) |
                    Q(phone__icontains=query)
                ).exclude(id=request.user.id)[:20]

                results = []
                for user in users:
                    results.append({
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'full_name': user.get_full_name() or user.username,
                        'phone': getattr(user, 'phone', ''),
                        'wallet_balance': float(user.wallet.available_balance) if hasattr(user, 'wallet') else 0,
                        'is_verified': getattr(user, 'is_verified', False),
                        'avatar_url': None
                    })
                cache.set(cache_key, results, timeout=60)

            return Response({
                'query': query,
                'count': len(results),
                'results': results
            })

        except Agent.DoesNotExist:
            return Response(
                {"error": "not_agent", "message": "No tienes permisos de agente"},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error in AgentSearchUserView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al buscar usuarios"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentCodesView(APIView):
    """
    GET /api/wallet/agent/codes/
    Listar códigos generados por el agente.
    """
    permission_classes = [IsAuthenticated, IsAgentOrAdmin]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request):
        try:
            codes = DepositCode.objects.filter(created_by=request.user).order_by('-created_at')

            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 20)), 100)

            total = codes.count()
            start = (page - 1) * page_size
            end = start + page_size
            codes_page = codes[start:end]

            return Response({
                'codes': [
                    {
                        'code': c.code,
                        'amount': float(c.amount),
                        'currency': c.currency,
                        'is_used': c.is_used,
                        'used_by': c.used_by.username if c.used_by else None,
                        'used_at': c.used_at.isoformat() if c.used_at else None,
                        'expires_at': c.expires_at.isoformat(),
                        'created_at': c.created_at.isoformat(),
                        'qr_url': f"/api/wallet/codes/{c.code}/qr/"
                    }
                    for c in codes_page
                ],
                'pagination': {
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size
                }
            })

        except Exception as e:
            logger.error(f"Error in AgentCodesView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al listar códigos"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentEarningsView(APIView):
    """
    GET /api/wallet/agent/earnings/
    Ver ganancias/comisiones del agente.
    """
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request):
        cache_key = f"agent_earnings:{request.user.id}"
        earnings_data = cache.get(cache_key)
        
        if not earnings_data:
            try:
                agent = Agent.objects.get(user=request.user)

                today = timezone.now().date()
                week_start = today - timedelta(days=today.weekday())
                month_start = today.replace(day=1)

                deposits_today = Transaction.objects.filter(
                    created_by=request.user,
                    transaction_type='deposit',
                    created_at__date=today,
                    status='completed'
                )
                deposits_week = Transaction.objects.filter(
                    created_by=request.user,
                    transaction_type='deposit',
                    created_at__date__gte=week_start,
                    status='completed'
                )
                deposits_month = Transaction.objects.filter(
                    created_by=request.user,
                    transaction_type='deposit',
                    created_at__date__gte=month_start,
                    status='completed'
                )
                deposits_total = Transaction.objects.filter(
                    created_by=request.user,
                    transaction_type='deposit',
                    status='completed'
                )

                def calculate_commission(deposits):
                    total_amount = deposits.aggregate(total=Sum('amount'))['total'] or Decimal('0')
                    commission = calculate_agent_commission(total_amount)
                    return {
                        'amount': float(total_amount),
                        'commission': float(commission)
                    }

                recent_transactions = Transaction.objects.filter(
                    created_by=request.user,
                    transaction_type='deposit',
                    status='completed'
                ).select_related('wallet__user').order_by('-created_at')[:20]

                earnings_data = {
                    'today': calculate_commission(deposits_today),
                    'week': calculate_commission(deposits_week),
                    'month': calculate_commission(deposits_month),
                    'total': calculate_commission(deposits_total),
                    'recent_transactions': [
                        {
                            'reference': tx.reference,
                            'amount': float(tx.amount),
                            'commission': float(calculate_agent_commission(tx.amount)),
                            'user': tx.wallet.user.username,
                            'created_at': tx.created_at.isoformat()
                        }
                        for tx in recent_transactions
                    ]
                }
                
                cache.set(cache_key, earnings_data, timeout=300)

            except Agent.DoesNotExist:
                return Response(
                    {"error": "not_agent", "message": "No tienes permisos de agente"},
                    status=status.HTTP_403_FORBIDDEN
                )
            except Exception as e:
                logger.error(f"Error in AgentEarningsView: {e}")
                return Response(
                    {"error": "internal_error", "message": "Error al calcular ganancias"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(earnings_data)


class AgentCreateView(APIView):
    """
    POST /api/wallet/admin/agents/
    Crear un nuevo agente (solo admin).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveOperationThrottle]

    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "permission_denied", "message": "Solo administradores pueden crear agentes"},
                status=status.HTTP_403_FORBIDDEN
            )

        content_type_error = _validate_content_type(request)
        if content_type_error:
            return content_type_error

        serializer = AgentCreateSerializer(data=request.data)
        if serializer.is_valid():
            agent = serializer.save()
            cache.delete("agents_list")
            
            logger.info(f"Agent created: by={request.user.id}, agent={agent.user.id}")
            
            return Response(AgentSerializer(agent).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AgentsListView(APIView):
    """
    GET /api/wallet/admin/agents/
    Listar todos los agentes (solo admin).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [WalletOperationThrottle]

    def get(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "permission_denied", "message": "Solo administradores pueden ver agentes"},
                status=status.HTTP_403_FORBIDDEN
            )

        cache_key = "agents_list"
        agents_data = cache.get(cache_key)
        
        if not agents_data:
            agents = Agent.objects.select_related('user', 'location').all()
            serializer = AgentSerializer(agents, many=True)
            agents_data = serializer.data
            cache.set(cache_key, agents_data, timeout=300)
        
        return Response(agents_data)


# ============================================
# LOCATION VIEWS
# ============================================

class LocationsListView(APIView):
    """
    GET /api/wallet/locations/
    Listar ubicaciones físicas disponibles.
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    throttle_classes = [AnonymousWalletThrottle]

    def get(self, request):
        cache_key = "physical_locations_active"
        locations_data = cache.get(cache_key)
        
        if not locations_data:
            locations = PhysicalLocation.objects.filter(is_active=True)
            serializer = PhysicalLocationSerializer(locations, many=True)
            locations_data = serializer.data
            cache.set(cache_key, locations_data, timeout=3600)
        
        return Response(locations_data)


# ============================================
# OFFICE VIEWS
# ============================================

class OfficeSearchArtistView(APIView):
    """
    GET /api/wallet/office/search/?q=...
    Buscar artista por email o teléfono (para personal de oficina)
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [WalletOperationThrottle]
    
    def get(self, request):
        try:
            staff = OfficeStaff.objects.select_related('office').get(
                user=request.user, 
                is_active=True
            )
        except OfficeStaff.DoesNotExist:
            return Response(
                {
                    'error': 'unauthorized',
                    'message': 'No autorizado. Solo personal de oficina puede realizar búsquedas.'
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        query = request.GET.get('q', '').strip()
        
        if not query:
            return Response(
                {
                    'error': 'missing_query',
                    'message': 'Se requiere un término de búsqueda (email, teléfono o username)'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(query) < 3:
            return Response(
                {
                    'error': 'query_too_short',
                    'message': 'La búsqueda requiere al menos 3 caracteres'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = OfficeWithdrawalService.search_artist(query)
        
        if result.get('found'):
            result['office_info'] = {
                'id': staff.office.id,
                'name': staff.office.name,
                'city': staff.office.city,
                'address': staff.office.address,
                'phone': staff.office.phone
            }
            result['staff_info'] = {
                'id': staff.id,
                'name': staff.user.get_full_name() or staff.user.username,
                'employee_id': staff.employee_id
            }
        
        logger.info(
            f"Office search performed - Staff: {request.user.id}, Query: {query}, Found: {result.get('found', False)}"
        )
        
        return Response(result)


class OfficeProcessWithdrawalView(APIView):
    """
    POST /api/wallet/office/withdraw/
    Procesar retiro en oficina
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveOperationThrottle]
    
    @transaction.atomic
    def post(self, request):
        try:
            staff = OfficeStaff.objects.get(user=request.user, is_active=True)
        except OfficeStaff.DoesNotExist:
            return Response(
                {'error': 'No autorizado. Solo personal de oficina.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        idempotency_key = request.headers.get('X-Idempotency-Key')
        
        serializer = OfficeWithdrawalSerializer(data=request.data)
        if serializer.is_valid():
            try:
                withdrawal = OfficeWithdrawalService.process_withdrawal(
                    artist_id=serializer.validated_data['artist_id'],
                    amount=serializer.validated_data['amount'],
                    office_id=staff.office_id,
                    staff_id=staff.id,
                    withdrawal_method=serializer.validated_data['withdrawal_method'],
                    id_number_verified=serializer.validated_data['id_number'],
                    id_type=serializer.validated_data.get('id_type', 'dni'),
                    muni_phone=serializer.validated_data.get('muni_phone'),
                    notes=serializer.validated_data.get('notes'),
                    ip_address=_get_client_ip(request),
                    idempotency_key=idempotency_key
                )
                
                response_data = {
                    'success': True,
                    'reference': withdrawal.reference,
                    'amount': float(withdrawal.amount),
                    'fee': float(withdrawal.fee),
                    'net_amount': float(withdrawal.net_amount),
                    'method': withdrawal.get_withdrawal_method_display(),
                    'paid_at': withdrawal.paid_at.isoformat(),
                    'idempotency_key': withdrawal.idempotency_key,
                    'message': f'Retiro procesado exitosamente. El artista recibió {withdrawal.net_amount:,.0f} XAF'
                }
                
                if idempotency_key and withdrawal.idempotency_key == idempotency_key:
                    response_data['idempotent'] = True
                
                logger.info(f"Office withdrawal: staff={staff.id}, artist={serializer.validated_data['artist_id']}, amount={serializer.validated_data['amount']}")
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
            except WalletBaseException as e:
                return Response(
                    {'error': e.detail, 'code': e.code},
                    status=e.status_code
                )
            except Exception as e:
                logger.error(f"Office withdrawal error: {e}")
                return Response(
                    {'error': 'Error interno al procesar el retiro'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OfficeReverseWithdrawalView(APIView):
    """
    POST /api/wallet/admin/office/reverse/<withdrawal_id>/
    Reversar un retiro (solo admin)
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveOperationThrottle]
    
    @transaction.atomic
    def post(self, request, withdrawal_id):
        if not request.user.is_staff:
            return Response(
                {'error': 'Solo administradores pueden reversar retiros'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        reason = request.data.get('reason', 'Reversado por administrador')
        
        try:
            result = OfficeWithdrawalService.reverse_withdrawal(
                withdrawal_id=withdrawal_id,
                admin_id=request.user.id,
                reason=reason
            )
            
            logger.warning(f"Withdrawal reversed: withdrawal_id={withdrawal_id}, by={request.user.id}, reason={reason}")
            
            return Response(result)
        except Exception as e:
            logger.error(f"OfficeReverseWithdrawalView error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ============================================
# HEALTH CHECK VIEW
# ============================================

class WalletHealthCheckView(APIView):
    """
    GET /api/wallet/health/
    Health check para monitoreo del sistema.
    """
    permission_classes = []
    throttle_classes = []  # Sin throttle para health checks

    def get(self, request):
        health_status = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'environment': 'production',
            'checks': {
                'database': 'unknown',
                'cache': 'unknown'
            }
        }
        
        try:
            connection.ensure_connection()
            health_status['checks']['database'] = 'ok'
        except Exception as e:
            health_status['status'] = 'unhealthy'
            health_status['checks']['database'] = f'error: {str(e)}'
        
        try:
            cache.set('health_check', 'ok', timeout=5)
            if cache.get('health_check') == 'ok':
                health_status['checks']['cache'] = 'ok'
            else:
                health_status['checks']['cache'] = 'error'
        except Exception as e:
            health_status['status'] = 'degraded'
            health_status['checks']['cache'] = f'error: {str(e)}'
        
        status_code = status.HTTP_200_OK if health_status['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return Response(health_status, status=status_code)