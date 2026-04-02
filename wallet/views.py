# wallet/views.py
"""
Vistas para las APIs del wallet.
"""
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
import logging

from .models import Wallet, Transaction, Hold, DepositCode
from .services import WalletService
from .serializers import (
    # Core serializers
    WalletSerializer,
    WalletCreateSerializer,
    WalletBalanceSerializer,
    
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
    BalanceInfoSerializer,
    ArtistEarningsSerializer,
    TransactionListSerializer,
    
    # Admin serializers
    WalletAdminSerializer,
    TransactionAdminSerializer,
)
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from decimal import Decimal
from .permissions import IsWalletOwner, IsArtist, IsAgent, IsAdminOrReadOnly, CanWithdrawFunds
from .pagination import WalletPagination, TransactionPagination
from .filters import TransactionFilter, HoldFilter, DepositCodeFilter
logger = logging.getLogger(__name__)


class WalletBalanceView(APIView):
    """
    GET /api/wallet/balance/
    Obtener balance del wallet del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        wallet = WalletService.get_user_wallet(request.user.id)
        balance_info = wallet.get_balance_info(
            language=request.GET.get('lang', 'es')
        )
        serializer = WalletBalanceSerializer(balance_info)
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
    serializer_class = TransactionSerializer  # Using TransactionSerializer instead of TransactionDetailSerializer
    lookup_field = 'reference'
    
    def get_queryset(self):
        wallet = WalletService.get_user_wallet(self.request.user.id)
        return Transaction.objects.filter(wallet=wallet)


class PurchaseSongView(APIView):
    """
    POST /api/wallet/songs/<int:song_id>/purchase/
    Comprar una canción.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, song_id):
        serializer = PurchaseSerializer(
            data={'song_id': song_id, **request.data},
            context={'request': request}
        )
        
        if serializer.is_valid():
            # Get price from the song
            from api2.models import Song
            try:
                song = Song.objects.get(id=song_id)
                price = song.price if hasattr(song, 'price') else None
                
                if not price or price <= 0:
                    return Response(
                        {'error': 'Esta canción no tiene precio válido'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Realizar compra
                transaction, hold = WalletService.purchase_song(
                    user_id=request.user.id,
                    song_id=song_id,
                    price=price
                )
                
                return Response({
                    'success': True,
                    'reference': transaction.reference,
                    'amount': float(transaction.absolute_amount),
                    'new_balance': float(transaction.wallet.available_balance),
                    'hold_id': hold.id if hold else None,
                    'message': f"Compra de '{song.title}' realizada con éxito"
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DepositView(APIView):
    """
    POST /api/wallet/deposit/
    Realizar un depósito (recarga) - SOLO AGENTES.
    """
    permission_classes = [IsAuthenticated, IsAgent]
    
    def post(self, request):
        wallet = WalletService.get_user_wallet(request.user.id)
        
        serializer = DepositSerializer(
            data=request.data,
            context={'wallet_id': wallet.id, 'request': request}
        )
        
        if serializer.is_valid():
            transaction = WalletService.deposit(
                wallet_id=wallet.id,
                amount=serializer.validated_data['amount'],
                description=serializer.validated_data.get('description', ''),
                created_by_id=request.user.id,
                metadata=serializer.validated_data.get('metadata', {})
            )
            return Response({
                'reference': transaction.reference,
                'amount': float(transaction.amount),
                'new_balance': float(transaction.wallet.available_balance),
                'description': transaction.description
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RedeemCodeView(APIView):
    """
    POST /api/wallet/redeem/
    Canjear un código de recarga.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = DepositCodeRedeemSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                transaction = WalletService.redeem_code(
                    code=serializer.validated_data['code'],
                    user_id=request.user.id
                )
                return Response({
                    'success': True,
                    'reference': transaction.reference,
                    'amount': float(transaction.amount),
                    'new_balance': float(transaction.wallet.available_balance),
                    'message': f"Código canjeado con éxito. Se añadieron {transaction.amount} {transaction.wallet.currency}"
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ArtistEarningsView(APIView):
    """
    GET /api/wallet/artist/earnings/
    Ver ganancias del artista autenticado.
    """
    permission_classes = [IsAuthenticated, IsArtist]
    
    def get(self, request):
        earnings = WalletService.get_artist_earnings(request.user.id)
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
    """
    permission_classes = [IsAuthenticated, CanWithdrawFunds]
    
    def post(self, request):
        serializer = HoldReleaseSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                transaction = WalletService.release_hold(
                    hold_id=serializer.validated_data['hold_id'],
                    released_by_id=request.user.id
                )
                return Response({
                    'success': True,
                    'reference': transaction.reference,
                    'amount': float(transaction.amount),
                    'message': "Hold liberado con éxito"
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
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

# wallet/views.py - AGREGAR AL FINAL

# ============================================================================
# VISTAS PARA SISTEMA DE AGENTES
# ============================================================================

from .models import Agent, PhysicalLocation, DepositCode
from .serializers import (
    AgentSerializer, AgentCreateSerializer, PhysicalLocationSerializer,
    AgentDepositSerializer, AgentGenerateCodeSerializer,
    AgentSearchUserSerializer, AgentUserInfoSerializer,
    RedeemCodeSerializer, CodeQRSerializer, AgentEarningsSerializer
)
from .permissions import IsAgent, IsAgentOrAdmin
from .utils import generate_qr_for_code, calculate_agent_commission
from django.contrib.auth import get_user_model

User = get_user_model()


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
            
            # Estadísticas del día
            daily_stats = agent.get_daily_stats()
            
            # Últimas recargas
            from wallet.models import Transaction
            recent_deposits = Transaction.objects.filter(
                created_by=request.user,
                transaction_type='deposit',
                status='completed'
            ).select_related('wallet__user').order_by('-created_at')[:10]
            
            # Códigos generados hoy
            from django.utils import timezone
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
    Realizar una recarga como agente.
    POST /api/wallet/agent/deposit/
    """
    permission_classes = [IsAuthenticated, IsAgent]
    
    def post(self, request):
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
                result = serializer.save()
                return Response(result, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except Agent.DoesNotExist:
            return Response(
                {"error": "not_agent", "message": "No tienes permisos de agente"},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error in AgentDepositView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al procesar la recarga"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentGenerateCodeView(APIView):
    """
    Generar códigos de recarga (agentes y admin).
    POST /api/wallet/agent/generate-code/
    """
    permission_classes = [IsAuthenticated, IsAgentOrAdmin]
    
    def post(self, request):
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
            logger.error(f"Error in AgentGenerateCodeView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al generar códigos"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentSearchUserView(APIView):
    """
    Buscar usuarios para recarga (agentes).
    GET /api/wallet/agent/search/?query=...
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
            
            # Buscar usuarios por email, username o teléfono
            users = User.objects.filter(
                Q(email__icontains=query) |
                Q(username__icontains=query) |
                Q(phone__icontains=query)
            ).exclude(id=request.user.id)[:20]  # Máximo 20 resultados
            
            results = []
            for user in users:
                results.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'full_name': user.get_full_name() or user.username,
                    'phone': user.phone or '',
                    'wallet_balance': float(user.wallet.available_balance) if hasattr(user, 'wallet') else 0,
                    'is_verified': user.is_verified,
                    'avatar_url': None  # Podrías obtener de perfil si existe
                })
            
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
    Listar códigos generados por el agente.
    GET /api/wallet/agent/codes/
    """
    permission_classes = [IsAuthenticated, IsAgentOrAdmin]
    
    def get(self, request):
        try:
            if request.user.is_staff:
                codes = DepositCode.objects.filter(created_by=request.user).order_by('-created_at')
            else:
                agent = Agent.objects.get(user=request.user)
                codes = DepositCode.objects.filter(created_by=request.user).order_by('-created_at')
            
            # Paginación
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
            
        except Agent.DoesNotExist:
            return Response(
                {"error": "not_agent", "message": "No tienes permisos de agente"},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error in AgentCodesView: {e}")
            return Response(
                {"error": "internal_error", "message": "Error al listar códigos"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AgentEarningsView(APIView):
    """
    Ver ganancias/comisiones del agente.
    GET /api/wallet/agent/earnings/
    """
    permission_classes = [IsAuthenticated, IsAgent]
    
    def get(self, request):
        try:
            agent = Agent.objects.get(user=request.user)
            
            from django.utils import timezone
            from datetime import timedelta
            from django.db.models import Sum
            
            today = timezone.now().date()
            week_start = today - timedelta(days=today.weekday())
            month_start = today.replace(day=1)
            
            # Calcular comisiones (simplificado - cada recarga genera 3% comisión)
            # En producción, tendrías un modelo Commission separado
            
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
            
            return Response({
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
            })
            
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


class RedeemCodeView(APIView):
    """
    Canjear un código de recarga.
    POST /api/wallet/codes/redeem/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = RedeemCodeSerializer(
            data=request.data,
            context={'user': request.user}
        )
        
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LocationsListView(APIView):
    """
    Listar ubicaciones físicas disponibles.
    GET /api/wallet/locations/
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get(self, request):
        locations = PhysicalLocation.objects.filter(is_active=True)
        serializer = PhysicalLocationSerializer(locations, many=True)
        return Response(serializer.data)


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
        
        serializer = AgentCreateSerializer(data=request.data)
        if serializer.is_valid():
            agent = serializer.save()
            return Response(AgentSerializer(agent).data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AgentsListView(APIView):
    """
    Listar todos los agentes (solo admin).
    GET /api/wallet/admin/agents/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "permission_denied", "message": "Solo administradores pueden ver agentes"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        agents = Agent.objects.select_related('user', 'location').all()
        serializer = AgentSerializer(agents, many=True)
        return Response(serializer.data)