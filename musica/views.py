import logging
import requests
from rest_framework.permissions import AllowAny
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from django.utils.timezone import now
from .models import UserVisit
from .serializers import RegisterSerializer

logger = logging.getLogger(__name__)

def get_client_ip(request):
    """Obtiene la IP real del cliente, considerando balanceadores de carga o proxies."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]  # Tomar la primera IP de la lista
    else:
        ip = request.META.get("REMOTE_ADDR", "127.0.0.1")
    return ip

def get_location_data(ip):
    """Obtiene la información de geolocalización de la IP usando la clave de API."""
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

class RegisterView(generics.CreateAPIView):
    
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny] 
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            try:
                user = serializer.save()
                refresh = RefreshToken.for_user(user)
                
                # Obtener la IP y datos de geolocalización
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

                return Response(
                    {
                        "message": "Usuario registrado exitosamente.",
                        "data": serializer.data,
                        "tokens": {
                            "refresh": str(refresh),
                            "access": str(refresh.access_token),
                        },
                    },
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                return Response(
                    {"error": f"Error al registrar usuario: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        request = self.context["request"]
        user = self.user
        
        # Obtener la IP y datos de geolocalización
        ip = get_client_ip(request)
        location_data = get_location_data(ip) or {}
        
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
            es_recurrente=UserVisit.objects.filter(user=user).exists(),
            url_referencia=request.META.get("HTTP_REFERER", "Desconocido"),
            fecha_visita=now()
        )
        
        return data

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class ProtectedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"message": "¡Acceso permitido solo para usuarios autenticados!"}, status=status.HTTP_200_OK)

class RegisterUserVisit(APIView):
    """Registra la visita de un usuario con datos de geolocalización."""
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

        return Response({"message": "Visita registrada con éxito", "data": {"ip": visit.ip, "ciudad": visit.ciudad, "pais": visit.pais}}, status=status.HTTP_201_CREATED)
