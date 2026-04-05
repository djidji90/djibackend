# wallet/views.py - SECCIÓN DE IMPORTS CORREGIDA

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django.shortcuts import get_object_or_404
from django.db.models import Q, Avg, Count
from django.utils import timezone
from django.core.cache import cache
from decimal import Decimal
import logging

from .models import Wallet, Transaction, Hold, DepositCode, Agent, PhysicalLocation
from .models import Office, OfficeStaff, OfficeWithdrawal, ArtistMuniAccount

from .services import WalletService, OfficeWithdrawalService

from .serializers import (
    # Core serializers
    WalletSerializer,
    WalletCreateSerializer,
    WalletBalanceSerializer,
    
    # Office withdrawal serializers
    OfficeWithdrawalSerializer,
    OfficeWithdrawalHistorySerializer,

    # Transaction serializers
    TransactionSerializer,
    DepositSerializer,
    PurchaseSerializer,
    RefundSerializer,

    # Hold serializers
    HoldSerializer,
    HoldReleaseSerializer,

    # Deposit code serializers
    DepositCodeSerializer,
    DepositCodeCreateSerializer,
    DepositCodeRedeemSerializer,

    # Response serializers
    WalletBalanceResponseSerializer,
    ArtistEarningsSerializer,
    TransactionListSerializer,

    # Admin serializers
    WalletAdminSerializer,
    TransactionAdminSerializer,

    # Agent serializers
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
    DepositThrottle
)
from .exceptions import WalletBaseException
from .utils import generate_qr_for_code, calculate_agent_commission
from django.contrib.auth import get_user_model

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
    ✅ Con cache de 60 segundos
    """
    permission_classes = [IsAuthenticated]

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

    def get_queryset(self):
        wallet = WalletService.get_user_wallet(self.request.user.id)
        return Transaction.objects.filter(wallet=wallet)


# wallet/views.py - PurchaseSongView CORREGIDO

# wallet/views.py - PurchaseSongView (VERSIÓN SIN THROTTLE)

# ============================================
# IMPORTS NECESARIOS
# ============================================
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.cache import cache
import logging

from .serializers import PurchaseSerializer
from .services import WalletService
from .exceptions import WalletBaseException
from .utils import _validate_content_type, _get_idempotency_key, _get_client_ip

logger = logging.getLogger(__name__)


# ============================================
# PURCHASE SONG VIEW (SIN THROTTLE)
# ============================================

class PurchaseSongView(APIView):
    """
    POST /api/wallet/songs/<int:song_id>/purchase/
    Comprar una canción.
    ✅ Con idempotencia
    ✅ THROTTLE DESHABILITADO PARA PRUEBAS
    ✅ Con auditoría (IP/UA)
    """
    permission_classes = [IsAuthenticated]
    
    def get_throttles(self):
        """
        🔥 THROTTLE DESHABILITADO COMPLETAMENTE PARA PRUEBAS
        """
        return []  # Sin throttle para todas las operaciones

    def get(self, request, song_id):
        """
        GET opcional - Verificar estado de compra de una canción
        Útil para frontend sin consumir throttle
        """
        try:
            from api2.models import Song
            from wallet.models import Transaction
            
            song = Song.objects.get(id=song_id)
            
            # Verificar si el usuario ya compró esta canción
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

    def post(self, request, song_id):
        # Validar Content-Type
        content_type_error = _validate_content_type(request)
        if content_type_error:
            return content_type_error

        serializer = PurchaseSerializer(
            data={'song_id': song_id, **request.data},
            context={'request': request}
        )

        if serializer.is_valid():
            # Generar clave de idempotencia
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

                # Invalidar cache de balance
                cache.delete(f"wallet_balance:{request.user.id}")

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
                    'path': request.path
                })
                return Response(
                    {'error': 'Error interno al procesar la compra'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# wallet/views.py - AÑADIR DESPUÉS DE AgentEarningsView (antes de LocationsListView)

class OfficeSearchArtistView(APIView):
    """
    Buscar artista por email o teléfono (para personal de oficina)
    GET /api/wallet/office/search/?q=...
    
    ✅ Busca por email, teléfono o username
    ✅ Retorna información del artista y su wallet
    ✅ Solo accesible por personal de oficina autenticado
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # ============================================
        # 1. VERIFICAR PERMISOS (solo personal de oficina)
        # ============================================
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
        
        # ============================================
        # 2. VALIDAR PARÁMETROS DE BÚSQUEDA
        # ============================================
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
        
        # ============================================
        # 3. BUSCAR ARTISTA
        # ============================================
        result = OfficeWithdrawalService.search_artist(query)
        
        # ============================================
        # 4. AÑADIR METADATOS DE OFICINA (para contexto)
        # ============================================
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
        
        # ============================================
        # 5. LOG DE BÚSQUEDA (para auditoría)
        # ============================================
        logger.info(
            f"Office search performed - "
            f"Staff: {request.user.id} ({staff.employee_id}), "
            f"Query: {query}, "
            f"Found: {result.get('found', False)}"
        )
        
        return Response(result)

class UserDepositView(APIView):
    """
    POST /api/wallet/deposit/
    Depósito para usuarios normales.
    ✅ Los usuarios normales solo pueden usar códigos de recarga
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
    ✅ Con idempotencia
    ✅ Con throttling
    ✅ Con auditoría
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
                
                # Invalidar cache de balance
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
                    'path': request.path
                })
                return Response(
                    {'error': 'Error interno al canjear el código'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ArtistEarningsView(APIView):
    """
    GET /api/wallet/artist/earnings/
    Ver ganancias del artista autenticado.
    ✅ Con cache
    """
    permission_classes = [IsAuthenticated, IsArtist]

    def get(self, request):
        cache_key = f"artist_earnings:{request.user.id}"
        earnings = cache.get(cache_key)
        
        if not earnings:
            earnings = WalletService.get_artist_earnings(request.user.id)
            cache.set(cache_key, earnings, timeout=300)  # 5 minutos
        
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

    def get_queryset(self):
        return Hold.objects.filter(
            artist=self.request.user
        ).select_related('artist', 'transaction__wallet__user').order_by('-created_at')


class UserPurchasesView(generics.ListAPIView):
    """
    GET /api/wallet/purchases/
    Ver compras realizadas por el usuario.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination

    def get_queryset(self):
        wallet = WalletService.get_user_wallet(self.request.user.id)
        return Transaction.objects.filter(
            wallet=wallet,
            transaction_type='purchase'
        ).select_related('wallet__user')


class ReleaseHoldView(APIView):
    """
    POST /api/wallet/admin/holds/release/
    Liberar un hold (solo admin).
    ✅ Con throttling
    ✅ Con auditoría completa
    """
    permission_classes = [IsAuthenticated, CanWithdrawFunds]
    throttle_classes = [SensitiveOperationThrottle]

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
                logger.error(f"ReleaseHoldView error: {e}", extra={
                    'user_id': request.user.id,
                    'hold_id': serializer.validated_data.get('hold_id'),
                    'path': request.path
                })
                return Response(
                    {'error': 'Error interno al liberar el hold'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DepositCodeListView(generics.ListCreateAPIView):
    """
    GET/POST /api/wallet/codes/
    Listar/Crear códigos de recarga (solo admin/agentes).
    """
    permission_classes = [IsAuthenticated, IsAgent]
    serializer_class = DepositCodeSerializer
    pagination_class = WalletPagination
    filterset_class = DepositCodeFilter

    def get_queryset(self):
        return DepositCode.objects.all().select_related('created_by', 'used_by')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DepositCodeDetailView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT /api/wallet/codes/<pk>/
    Ver/Actualizar código (solo admin/agentes).
    """
    permission_classes = [IsAuthenticated, IsAgent]
    serializer_class = DepositCodeSerializer
    queryset = DepositCode.objects.all()
    lookup_field = 'pk'


class CodeQRView(APIView):
    """
    Obtener código QR para un código de recarga.
    GET /api/wallet/codes/<code>/qr/
    """
    permission_classes = [IsAuthenticated]

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
    Dashboard del agente.
    GET /api/wallet/agent/dashboard/
    """
    permission_classes = [IsAuthenticated, IsAgent]

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
            logger.error(f"Error in AgentDashboardView: {e}", extra={
                'user_id': request.user.id,
                'path': request.path
            })
            return Response(
                {"error": "internal_error", "message": "Error al cargar dashboard"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentDepositView(APIView):
    """
    Realizar una recarga como agente.
    POST /api/wallet/agent/deposit/
    ✅ Con idempotencia
    ✅ Con throttling
    ✅ Con auditoría
    """
    permission_classes = [IsAuthenticated, IsAgent]
    throttle_classes = [DepositThrottle]

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
                # Generar idempotency key
                idempotency_key = _get_idempotency_key(
                    request, 'agent_deposit', request.user.id, 
                    serializer.validated_data.get('user_id'), 
                    serializer.validated_data.get('amount')
                )
                
                # Añadir idempotency key al contexto
                serializer.context['idempotency_key'] = idempotency_key
                serializer.context['ip_address'] = _get_client_ip(request)
                serializer.context['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
                
                result = serializer.save()
                
                # Invalidar cache de balance del usuario
                cache.delete(f"wallet_balance:{serializer.validated_data['user_id']}")
                
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
            logger.error(f"Error in AgentDepositView: {e}", extra={
                'user_id': request.user.id,
                'path': request.path,
                'data': request.data
            })
            return Response(
                {"error": "internal_error", "message": "Error al procesar la recarga"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentGenerateCodeView(APIView):
    """
    Generar códigos de recarga (agentes y admin).
    POST /api/wallet/agent/generate-code/
    ✅ Con idempotencia
    ✅ Con throttling
    """
    permission_classes = [IsAuthenticated, IsAgentOrAdmin]
    throttle_classes = [SensitiveOperationThrottle]

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
                # Generar idempotency key
                idempotency_key = _get_idempotency_key(
                    request, 'generate_codes', request.user.id,
                    serializer.validated_data.get('amount'),
                    serializer.validated_data.get('quantity')
                )
                
                serializer.context['idempotency_key'] = idempotency_key
                result = serializer.save()
                return Response(result, status=status.HTTP_201_CREATED)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Agent.DoesNotExist:
            # Admin puede generar códigos sin ser agente
            if request.user.is_staff:
                serializer = AgentGenerateCodeSerializer(data=request.data)
                if serializer.is_valid():
                    amount = serializer.validated_data['amount']
                    quantity = serializer.validated_data['quantity']
                    currency = serializer.validated_data['currency']
                    expires_days = serializer.validated_data['expires_days']

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
                            created_by=request.user,
                            expires_at=timezone.now() + timezone.timedelta(days=expires_days),
                            notes=f"Generado por admin {request.user.username}"
                        )
                        codes.append(deposit_code)

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
            logger.error(f"Error in AgentGenerateCodeView: {e}", extra={
                'user_id': request.user.id,
                'path': request.path
            })
            return Response(
                {"error": "internal_error", "message": "Error al generar códigos"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentSearchUserView(APIView):
    """
    Buscar usuarios para recarga (agentes).
    GET /api/wallet/agent/search/?query=...
    ✅ Con cache para búsquedas frecuentes
    """
    permission_classes = [IsAuthenticated, IsAgent]

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
            
            # Cache para búsquedas frecuentes
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
                cache.set(cache_key, results, timeout=60)  # 1 minuto

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
            logger.error(f"Error in AgentSearchUserView: {e}", extra={
                'user_id': request.user.id,
                'query': request.GET.get('query', ''),
                'path': request.path
            })
            return Response(
                {"error": "internal_error", "message": "Error al buscar usuarios"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentCodesView(APIView):
    """
    Listar códigos generados por el agente.
    GET /api/wallet/agent/codes/
    """
    permission_classes = [IsAuthenticated, IsAgentOrAdmin]

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
            logger.error(f"Error in AgentCodesView: {e}", extra={
                'user_id': request.user.id,
                'path': request.path
            })
            return Response(
                {"error": "internal_error", "message": "Error al listar códigos"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentEarningsView(APIView):
    """
    Ver ganancias/comisiones del agente.
    GET /api/wallet/agent/earnings/
    ✅ Con cache
    """
    permission_classes = [IsAuthenticated, IsAgent]

    def get(self, request):
        cache_key = f"agent_earnings:{request.user.id}"
        earnings_data = cache.get(cache_key)
        
        if not earnings_data:
            try:
                agent = Agent.objects.get(user=request.user)

                from datetime import timedelta
                from django.db.models import Sum

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
                
                cache.set(cache_key, earnings_data, timeout=300)  # 5 minutos

            except Agent.DoesNotExist:
                return Response(
                    {"error": "not_agent", "message": "No tienes permisos de agente"},
                    status=status.HTTP_403_FORBIDDEN
                )
            except Exception as e:
                logger.error(f"Error in AgentEarningsView: {e}", extra={
                    'user_id': request.user.id,
                    'path': request.path
                })
                return Response(
                    {"error": "internal_error", "message": "Error al calcular ganancias"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response(earnings_data)


class LocationsListView(APIView):
    """
    Listar ubicaciones físicas disponibles.
    GET /api/wallet/locations/
    ✅ Con cache
    """
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        cache_key = "physical_locations_active"
        locations_data = cache.get(cache_key)
        
        if not locations_data:
            locations = PhysicalLocation.objects.filter(is_active=True)
            serializer = PhysicalLocationSerializer(locations, many=True)
            locations_data = serializer.data
            cache.set(cache_key, locations_data, timeout=3600)  # 1 hora
        
        return Response(locations_data)


class AgentCreateView(APIView):
    """
    Crear un nuevo agente (solo admin).
    POST /api/wallet/admin/agents/
    """
    permission_classes = [IsAuthenticated]

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
            
            # Invalidar cache de agentes
            cache.delete("agents_list")
            
            return Response(AgentSerializer(agent).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AgentsListView(APIView):
    """
    Listar todos los agentes (solo admin).
    GET /api/wallet/admin/agents/
    ✅ Con cache
    """
    permission_classes = [IsAuthenticated]

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
            cache.set(cache_key, agents_data, timeout=300)  # 5 minutos
        
        return Response(agents_data)


# ============================================
# HEALTH CHECK VIEW (para monitoreo)
# ============================================

class WalletHealthCheckView(APIView):
    """
    GET /api/wallet/health/
    Health check para monitoreo del sistema.
    Sin autenticación para permitir monitoreo externo.
    """
    permission_classes = []
    
    def get(self, request):
        from django.db import connection
        from datetime import datetime
        
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'checks': {
                'database': 'unknown',
                'cache': 'unknown'
            }
        }
        
        # Check database
        try:
            connection.ensure_connection()
            health_status['checks']['database'] = 'ok'
        except Exception as e:
            health_status['status'] = 'unhealthy'
            health_status['checks']['database'] = f'error: {str(e)}'
        
        # Check cache
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

# wallet/views.py - ACTUALIZAR OfficeProcessWithdrawalView

class OfficeProcessWithdrawalView(APIView):
    """
    Procesar retiro en oficina
    POST /api/wallet/office/withdraw/
    ✅ Con idempotencia (X-Idempotency-Key header)
    ✅ Con rate limiting
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveOperationThrottle]
    
    def post(self, request):
        # Verificar personal
        try:
            staff = OfficeStaff.objects.get(user=request.user, is_active=True)
        except OfficeStaff.DoesNotExist:
            return Response(
                {'error': 'No autorizado. Solo personal de oficina.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # ✅ Obtener o generar idempotency key del header
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
                
                # ✅ Devolver el idempotency key para que el cliente lo use
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
                
                # Si fue una respuesta de idempotencia, añadir header
                if idempotency_key and withdrawal.idempotency_key == idempotency_key:
                    response_data['idempotent'] = True
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
            except WalletBaseException as e:
                return Response(
                    {'error': e.detail, 'code': e.code},
                    status=e.status_code
                )
            except Exception as e:
                logger.error(f"Office withdrawal error: {e}", extra={
                    'staff_id': staff.id,
                    'artist_id': request.data.get('artist_id'),
                    'amount': request.data.get('amount')
                })
                return Response(
                    {'error': 'Error interno al procesar el retiro'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OfficeReverseWithdrawalView(APIView):
    """
    Reversar un retiro (solo admin)
    POST /api/wallet/admin/office/reverse/<withdrawal_id>/
    """
    permission_classes = [IsAuthenticated]
    
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
            return Response(result)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)