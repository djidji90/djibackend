# musica/views_api.py
"""
Vistas API para consumo del frontend (JSON).
Endpoints públicos para listar y obtener detalles de artistas.
"""
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from .models import CustomUser
from .serializers import PublicArtistSerializer
from .serializers import ArtistProfileSerializer

class StandardResultsPagination(PageNumberPagination):
    """Paginación estándar para listados."""
    page_size = 24
    page_size_query_param = 'page_size'
    
    max_page_size = 100


class PublicArtistListView(generics.ListAPIView):
    """
    Endpoint JSON: Lista de artistas públicos.
    URL: /musica/api/artistas/
    
    Filtros automáticos:
    - Solo artistas activos y públicos
    - Verificados primero
    - Paginación: 24 por página
    """
    permission_classes = [AllowAny]
    serializer_class = PublicArtistSerializer
    pagination_class = StandardResultsPagination
    
    def get_queryset(self):
        return CustomUser.objects.filter(
            is_active=True,
            is_public=True
        ).order_by('-is_verified', '-date_joined')


class PublicArtistDetailView(generics.RetrieveAPIView):
    """
    Endpoint JSON: Detalle de un artista por slug.
    URL: /musica/api/artistas/<slug>/
    
    Solo devuelve artistas activos y públicos.
    """
    permission_classes = [AllowAny]
    serializer_class = PublicArtistSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'
    
    def get_queryset(self):
        return CustomUser.objects.filter(
            is_active=True,
            is_public=True
        )
        
# musica/views_api.py - AÑADIR ESTA CLASE


class ArtistProfileDetailView(generics.RetrieveAPIView):
    """
    Endpoint JSON: Perfil COMPLETO de artista.
    URL: /musica/api/artistas/{slug}/profile/
    
    Devuelve:
    - Datos del artista
    - Lista de canciones (máximo 50)
    - Estadísticas (total plays, likes, downloads)
    """
    permission_classes = [AllowAny]
    serializer_class = ArtistProfileSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'
    
    def get_queryset(self):
        return CustomUser.objects.filter(
            is_active=True,
            is_public=True
        ).prefetch_related('songs')