# users/views.py
"""
Vistas para la gestión de usuarios con integración de wallet.
Incluye registro, login con geolocalización y campos de wallet.
"""
import logging
import requests
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from django.utils.timezone import now

from .models import CustomUser, UserVisit
from .serializers import RegisterSerializer, UserSerializer

logger = logging.getLogger(__name__)


# ============================================
# FUNCIONES UTILITARIAS
# ============================================

def get_client_ip(request):
    """
    Obtiene la IP real del cliente, considerando balanceadores de carga o proxies.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]  # Tomar la primera IP de la lista
    else:
        ip = request.META.get("REMOTE_ADDR", "127.0.0.1")
    return ip


def get_location_data(ip):
    """
    Obtiene la información de geolocalización de la IP usando la clave de API.
    """
    api_key = getattr(settings, "API_INFO_KEY", None)
    if not api_key:
        logger.warning("API_INFO_KEY no está configurada en settings.")
        return {}
    
    url = f"https://apiinfo.com/data?ip={ip}&key={api_key}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        logger.error(f"Timeout al obtener datos de geolocalización para IP {ip}")
    except requests.RequestException as e:
        logger.error(f"Error al obtener datos de geolocalización: {str(e)}")
    return {}


# ============================================
# VISTAS DE REGISTRO Y AUTENTICACIÓN
# ============================================

class RegisterView(generics.CreateAPIView):
    """
    Vista para registro de nuevos usuarios.
    Crea usuario, wallet automático (vía señal) y registra visita.
    """
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Crear usuario
                user = serializer.save()
                
                # Generar tokens JWT
                refresh = RefreshToken.for_user(user)
                
                # Obtener IP y datos de geolocalización
                ip = get_client_ip(request)
                location_data = get_location_data(ip) or {}
                
                # Guardar la visita en la base de datos
                if not UserVisit.objects.filter(user=user, ip=ip).exists():
                    UserVisit.objects.create(
                        user=user,
                        ip=ip,
                        ciudad=location_data.get("city", "Desconocido"),
                        region=location_data.get("region", "Desconocido"),
                        pais=location_data.get("country", "Desconocido"),
                        latitud=location_data.get("latitude"),
                        longitud=location_data.get("longitude"),
                        proveedor=location_data.get("isp", "Desconocido"),
                        user_agent=request.META.get("HTTP_USER_AGENT", "Desconocido"),
                        navegador=location_data.get("browser", "Desconocido"),
                        sistema_operativo=location_data.get("os", "Desconocido"),
                        es_recurrente=False,
                        url_referencia=request.META.get("HTTP_REFERER", "Desconocido"),
                        fecha_visita=now()
                    )

                # Construir respuesta con datos del usuario
                user_data = {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "city": user.city,
                    "neighborhood": user.neighborhood,
                    "phone": user.phone,
                    "country": user.country,
                    "is_verified": user.is_verified,
                    "can_withdraw": user.can_withdraw,
                    "default_currency": user.default_currency,
                }

                return Response(
                    {
                        "message": "Usuario registrado exitosamente.",
                        "user": user_data,
                        "tokens": {
                            "refresh": str(refresh),
                            "access": str(refresh.access_token),
                        },
                    },
                    status=status.HTTP_201_CREATED,
                )
                
            except Exception as e:
                logger.error(f"Error en registro de usuario: {str(e)}")
                return Response(
                    {"error": f"Error al registrar usuario: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
                
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer personalizado para login que incluye datos del usuario con campos de wallet.
    """
    def validate(self, attrs):
        # Validar credenciales y obtener tokens
        data = super().validate(attrs)
        request = self.context["request"]
        user = self.user
        
        # Obtener IP y datos de geolocalización
        ip = get_client_ip(request)
        location_data = get_location_data(ip) or {}
        
        # Verificar si es recurrente
        is_recurrent = UserVisit.objects.filter(user=user).exists()
        
        # Guardar la visita en la base de datos
        UserVisit.objects.create(
            user=user,
            ip=ip,
            ciudad=location_data.get("city", "Desconocido"),
            region=location_data.get("region", "Desconocido"),
            pais=location_data.get("country", "Desconocido"),
            latitud=location_data.get("latitude"),
            longitud=location_data.get("longitude"),
            proveedor=location_data.get("isp", "Desconocido"),
            user_agent=request.META.get("HTTP_USER_AGENT", "Desconocido"),
            navegador=location_data.get("browser", "Desconocido"),
            sistema_operativo=location_data.get("os", "Desconocido"),
            es_recurrente=is_recurrent,
            url_referencia=request.META.get("HTTP_REFERER", "Desconocido"),
            fecha_visita=now()
        )
        
        # Agregar datos del usuario a la respuesta (incluyendo campos de wallet)
        data['user'] = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'city': user.city,
            'neighborhood': user.neighborhood,
            'phone': user.phone,
            'country': user.country,
            'is_verified': user.is_verified,
            'can_withdraw': user.can_withdraw,
            'verified_at': user.verified_at.isoformat() if user.verified_at else None,
            'default_currency': user.default_currency,
        }
        
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Vista personalizada para login con datos de usuario extendidos.
    """
    serializer_class = CustomTokenObtainPairSerializer


# ============================================
# VISTAS DE PERFIL Y USUARIO
# ============================================

class UserProfileView(APIView):
    """
    Vista para obtener y actualizar el perfil del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Obtener perfil del usuario actual"""
        user = request.user
        serializer = UserSerializer(user, context={'request': request})
        
        # Obtener información adicional del wallet si existe
        try:
            from wallet.models import Wallet
            wallet = Wallet.objects.get(user=user)
            wallet_data = {
                'available_balance': float(wallet.available_balance),
                'pending_balance': float(wallet.pending_balance),
                'total_balance': float(wallet.total_balance),
                'currency': wallet.currency,
            }
        except:
            wallet_data = None
        
        response_data = serializer.data
        response_data['wallet'] = wallet_data
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def patch(self, request):
        """Actualizar parcialmente el perfil del usuario"""
        user = request.user
        allowed_fields = ['first_name', 'last_name', 'city', 'neighborhood', 'phone', 'country']
        
        updated = False
        for field in allowed_fields:
            if field in request.data:
                setattr(user, field, request.data[field])
                updated = True
        
        if updated:
            user.save(update_fields=allowed_fields)
        
        serializer = UserSerializer(user, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserDetailView(APIView):
    """
    Vista para obtener detalles de un usuario específico (público).
    """
    permission_classes = [AllowAny]
    
    def get(self, request, user_id):
        try:
            user = CustomUser.objects.get(id=user_id)
            serializer = UserSerializer(user, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "Usuario no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )


# ============================================
# VISTAS DE VISITAS
# ============================================

class RegisterUserVisit(APIView):
    """
    Registra la visita de un usuario con datos de geolocalización.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        ip = get_client_ip(request)
        location_data = get_location_data(ip) or {}

        visit = UserVisit.objects.create(
            user=user,
            ip=ip,
            ciudad=location_data.get("city", "Desconocido"),
            region=location_data.get("region", "Desconocido"),
            pais=location_data.get("country", "Desconocido"),
            latitud=location_data.get("latitude"),
            longitud=location_data.get("longitude"),
            proveedor=location_data.get("isp", "Desconocido"),
            user_agent=request.META.get("HTTP_USER_AGENT", "Desconocido"),
            navegador=location_data.get("browser", "Desconocido"),
            sistema_operativo=location_data.get("os", "Desconocido"),
            es_recurrente=UserVisit.objects.filter(user=user).exists() if user else False,
            url_referencia=request.META.get("HTTP_REFERER", "Desconocido"),
            fecha_visita=now()
        )

        return Response(
            {
                "message": "Visita registrada con éxito",
                "data": {
                    "ip": visit.ip,
                    "ciudad": visit.ciudad,
                    "pais": visit.pais
                }
            },
            status=status.HTTP_201_CREATED
        )


# ============================================
# VISTAS DE VERIFICACIÓN (ADMIN)
# ============================================

class VerifyUserView(APIView):
    """
    Vista para que un administrador verifique a un usuario.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, user_id):
        # Solo administradores pueden verificar
        if not request.user.is_staff:
            return Response(
                {"error": "No tienes permisos para realizar esta acción"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            user = CustomUser.objects.get(id=user_id)
            user.verify()
            
            return Response({
                "message": f"Usuario {user.email} verificado exitosamente",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "is_verified": user.is_verified,
                    "can_withdraw": user.can_withdraw,
                    "verified_at": user.verified_at.isoformat() if user.verified_at else None
                }
            }, status=status.HTTP_200_OK)
            
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "Usuario no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )


class UnverifyUserView(APIView):
    """
    Vista para que un administrador quite la verificación de un usuario.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, user_id):
        if not request.user.is_staff:
            return Response(
                {"error": "No tienes permisos para realizar esta acción"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            user = CustomUser.objects.get(id=user_id)
            user.unverify()
            
            return Response({
                "message": f"Verificación removida para {user.email}",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "is_verified": user.is_verified,
                    "can_withdraw": user.can_withdraw
                }
            }, status=status.HTTP_200_OK)
            
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "Usuario no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )


# ============================================
# VISTAS PROTEGIDAS DE PRUEBA
# ============================================

class ProtectedView(APIView):
    """
    Vista de prueba para verificar autenticación.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "message": "¡Acceso permitido solo para usuarios autenticados!",
                "user": {
                    "id": request.user.id,
                    "username": request.user.username,
                    "email": request.user.email,
                    "country": request.user.country,
                    "default_currency": request.user.default_currency
                }
            },
            status=status.HTTP_200_OK
        )


# ============================================
# VISTA DE LOGOUT
# ============================================

class LogoutView(APIView):
    """
    Vista para cerrar sesión (invalidar refresh token).
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response(
                {"message": "Sesión cerrada exitosamente"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )