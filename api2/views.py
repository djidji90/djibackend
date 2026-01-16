
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from django.db import DatabaseError, IntegrityError, transaction
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.db.models.functions import Lower
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse, JsonResponse
# AGREGAR al inicio del archivo
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.utils.text import slugify
import time
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import permission_classes
from django.db.models import Value, CharField, Q, Count , IntegerField, Case, When, BooleanField
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import Song, Like, Download, Comment, MusicEvent
from django.utils import timezone
from .r2_utils import (
    upload_file_to_r2, 
    generate_presigned_url, 
    delete_file_from_r2,
    check_file_exists,
    get_file_info,
    get_file_size,
    stream_file_from_r2,  # AGREGAR esta importación
    get_content_type_from_key  # AGREGAR esta importación
)
from .serializers import SongSerializer, CommentSerializer, MusicEventSerializer
import logging
from rest_framework.renderers import JSONRenderer

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework import status
from django.core.cache import cache
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.throttling import UserRateThrottle
import random
from api2.serializers import SongUploadSerializer
from rest_framework.parsers import MultiPartParser, FormParser

# ✅ AGREGAR estos imports faltantes
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
import re
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)

# En tu views.py


class CommentPagination(PageNumberPagination):
    page_size = 3
    page_size_query_param = 'page_size'

# Music Event List View
@extend_schema(description="Listar eventos de música")
class MusicEventListView(generics.ListCreateAPIView):
    queryset = MusicEvent.objects.all()
    serializer_class = MusicEventSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def handle_exception(self, exc):
        if isinstance(exc, (DatabaseError, IntegrityError)):
            logger.error(f"Database error in MusicEventListView: {exc}")
            return Response(
                {"error": "Error de base de datos al procesar eventos"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return super().handle_exception(exc)

    def perform_create(self, serializer):
        try:
            serializer.save()
        except IntegrityError as e:
            logger.error(f"Integrity error creating event: {e}")
            raise ValidationError("Error de integridad en los datos del evento")
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            raise ValidationError("Error inesperado al crear el evento")

# Music Event Detail View
@extend_schema(description="Obtener, actualizar o eliminar un evento de música")
class MusicEventDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = MusicEvent.objects.all()
    serializer_class = MusicEventSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def handle_exception(self, exc):
        if isinstance(exc, (DatabaseError, IntegrityError)):
            logger.error(f"Database error in MusicEventDetailView: {exc}")
            return Response(
                {"error": "Error de base de datos al procesar el evento"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return super().handle_exception(exc)

    def perform_update(self, serializer):
        try:
            if not self.request.user.is_authenticated:
                raise PermissionDenied("No puedes editar este evento.")
            super().perform_update(serializer)
        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            raise ValidationError("Error inesperado al actualizar el evento")

    def perform_destroy(self, instance):
        try:
            if not self.request.user.is_authenticated:
                raise PermissionDenied("No puedes eliminar este evento.")
            super().perform_destroy(instance)
        except DatabaseError as e:
            logger.error(f"Database error deleting event: {e}")
            raise ValidationError("Error de base de datos al eliminar el evento")
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            raise ValidationError("Error inesperado al eliminar el evento")

# Song Likes View
class SongLikesView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(description="Obtener el conteo de likes de una canción")
    def get(self, request, song_id):
        try:
            song = get_object_or_404(Song, id=song_id)
            likes_count = cache.get(f"song_{song_id}_likes_count", song.likes_count)
            return Response({
                "song_id": song_id,
                "likes_count": likes_count,
                "title": song.title
            })
        except Exception as e:
            logger.error(f"Error getting song likes: {e}")
            return Response(
                {"error": "Error al obtener los likes de la canción"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Song List View with Flexible Search



# ============================================
# 🔍 VISTA PRINCIPAL DE SUGERENCIAS - DEPURADA
# ============================================

@extend_schema(
    description="""
    🔍 SISTEMA ÚNICO de sugerencias de búsqueda - OPTIMIZADO
    
    Características:
    • Búsqueda en título, artista y género
    • Ordenación por relevancia automática
    • Cache inteligente (5 minutos)
    • Fallback silencioso (mejor UX)
    • Compatible con frontend antiguo y nuevo
    """,
    parameters=[
        OpenApiParameter(
            name='query', 
            description='Texto de búsqueda (mínimo 2 caracteres)',
            required=True, 
            type=str
        ),
        OpenApiParameter(
            name='q',
            description='Alias de "query" para compatibilidad',
            required=False,
            type=str
        ),
        OpenApiParameter(
            name='limit',
            description='Número máximo de resultados (default: 8, max: 20)',
            required=False,
            type=int
        ),
        OpenApiParameter(
            name='types',
            description='Tipos a incluir: song,artist,genre,all (default: song)',
            required=False,
            type=str
        )
    ]
)
@api_view(['GET'])
def song_suggestions(request):
    """
    🔥 VERSIÓN FINAL - Funciona perfectamente
    """
    start_time = time.time()
    
    # Configuración
    MIN_QUERY_LENGTH = 2
    DEFAULT_LIMIT = 8
    MAX_LIMIT = 20
    CACHE_TIMEOUT = 300
    
    # Detectar si es ruta legacy
    request_path = request.path_info
    is_legacy_route = 'songs/search/suggestions' in request_path
    
    # Obtener query (soporta ambos parámetros)
    query = request.GET.get('query') or request.GET.get('q') or ''
    query = query.strip()
    
    # Validaciones
    if len(query) < MIN_QUERY_LENGTH:
        if is_legacy_route:
            return Response([], status=status.HTTP_200_OK)
        return Response({
            "suggestions": [],
            "error": "query_too_short",
            "message": f"La búsqueda requiere al menos {MIN_QUERY_LENGTH} caracteres"
        }, status=status.HTTP_400_BAD_REQUEST)
    
    original_query = query
    search_query = query.lower()
    
    # Configurar parámetros
    try:
        limit = min(int(request.GET.get('limit', DEFAULT_LIMIT)), MAX_LIMIT)
    except (ValueError, TypeError):
        limit = DEFAULT_LIMIT
    
    # Para rutas legacy, solo mostrar canciones
    types_param = request.GET.get('types', 'song')
    if is_legacy_route:
        types_param = 'song'
    
    types_to_include = [t.strip().lower() for t in types_param.split(',')]
    
    # Cache
    cache_key = f"suggestions_{search_query}_{limit}_{'legacy' if is_legacy_route else 'modern'}"
    cached_data = cache.get(cache_key)
    
    if cached_data:
        processing_time = (time.time() - start_time) * 1000
        if is_legacy_route:
            return Response(cached_data)
        else:
            return Response({
                **cached_data,
                "_metadata": {
                    **cached_data.get("_metadata", {}),
                    "cached": True,
                    "processing_time_ms": round(processing_time, 2),
                    "timestamp": timezone.now().isoformat()
                }
            })
    
    try:
        # BÚSQUEDA PRINCIPAL
        songs = Song.objects.filter(
            Q(title__icontains=search_query) | 
            Q(artist__icontains=search_query) | 
            Q(genre__icontains=search_query)
        ).only('id', 'title', 'artist', 'genre')
        
        songs_list = list(songs)
        
        # Procesar resultados
        processed_items = []
        seen_items = set()
        
        for song in songs_list:
            if len(processed_items) >= limit:
                break
            
            # Preparar datos
            title = song.title or "Sin título"
            artist = song.artist or "Artista desconocido"
            genre = song.genre or "Sin género"
            
            # Calcular score de relevancia
            score = 0
            exact_match = False
            
            # Título (más importante)
            if search_query in title.lower():
                score += 3
                if search_query == title.lower():
                    exact_match = True
                    score += 2  # Bonus por match exacto
            
            # Artista
            if search_query in artist.lower():
                score += 2
                if search_query == artist.lower():
                    score += 1
            
            # Género
            if search_query in genre.lower():
                score += 1
            
            if is_legacy_route:
                # Formato LEGACY (simple)
                item_key = f"{title}|{artist}"
                if item_key not in seen_items:
                    processed_items.append({
                        "title": title,
                        "artist": artist,
                        "genre": genre
                    })
                    seen_items.add(item_key)
            else:
                # Formato MODERNO (completo)
                item_type = "song"
                item_key = f"{item_type}:{song.id}"
                
                if item_key not in seen_items:
                    processed_items.append({
                        "id": song.id,
                        "type": item_type,
                        "title": title,
                        "artist": artist,
                        "genre": genre,
                        "display": f"{title} - {artist}",
                        "exact_match": exact_match,
                        "score": score
                    })
                    seen_items.add(item_key)
        
        # Ordenar por score (más alto primero)
        processed_items.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        processing_time = (time.time() - start_time) * 1000
        
        # Preparar respuesta
        if is_legacy_route:
            response_data = processed_items[:limit]
        else:
            response_data = {
                "suggestions": processed_items[:limit],
                "_metadata": {
                    "query": original_query,
                    "total": len(processed_items[:limit]),
                    "limit": limit,
                    "cached": False,
                    "processing_time_ms": round(processing_time, 2),
                    "timestamp": timezone.now().isoformat(),
                    "route_type": "legacy" if is_legacy_route else "modern"
                }
            }
        
        # Cachear resultados
        if len(processed_items) > 0 and len(search_query) >= 2:
            cache.set(cache_key, response_data, CACHE_TIMEOUT)
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error en song_suggestions: {str(e)}", exc_info=True)
        
        if is_legacy_route:
            return Response([])
        else:
            return Response({
                "suggestions": [],
                "_metadata": {
                    "query": original_query,
                    "error": "internal_error",
                    "timestamp": timezone.now().isoformat()
                }
            })
# ============================================
# 🎵 VISTA DE LISTA DE CANCIONES (MANTENIENDO)
# ============================================

@extend_schema(
    description="Lista y busca canciones con filtros avanzados",
    parameters=[
        OpenApiParameter(name='title', description='Filtrar por título', required=False, type=str),
        OpenApiParameter(name='artist', description='Filtrar por artista', required=False, type=str),
        OpenApiParameter(name='genre', description='Filtrar por género', required=False, type=str),
        OpenApiParameter(name='q', description='Búsqueda general', required=False, type=str),
        OpenApiParameter(name='page', description='Número de página', required=False, type=int),
        OpenApiParameter(name='page_size', description='Items por página', required=False, type=int),
    ]
)
class SongListView(generics.ListCreateAPIView):
    """
    Vista para listar y crear canciones con filtros avanzados
    """
    serializer_class = SongSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['title', 'artist', 'genre']
    
    # Optimizaciones
    renderer_classes = [JSONRenderer]
    pagination_class = PageNumberPagination
    page_size = 20
    max_page_size = 100
    throttle_classes = [UserRateThrottle]

    def get_queryset(self):
        """
        Construye el queryset con filtros avanzados
        """
        try:
            queryset = Song.objects.all()
            
            # Obtener parámetros de filtro
            title = self.request.query_params.get('title', '').strip()
            artist = self.request.query_params.get('artist', '').strip()
            genre = self.request.query_params.get('genre', '').strip()
            general_query = self.request.query_params.get('q', '').strip()
            
            # Aplicar filtros
            if title:
                queryset = queryset.filter(title__icontains=title)
            
            if artist:
                queryset = queryset.filter(artist__icontains=artist)
            
            if genre:
                queryset = queryset.filter(genre__icontains=genre)
            
            # Búsqueda general (en múltiples campos)
            if general_query:
                queryset = queryset.filter(
                    Q(title__icontains=general_query) |
                    Q(artist__icontains=general_query) |
                    Q(genre__icontains=general_query)
                )
            
            # Ordenar por fecha de creación (más recientes primero)
            queryset = queryset.order_by('-created_at')
            
            return queryset
            
        except Exception as e:
            logger.error(f"Error building song query: {str(e)}")
            raise ValidationError("Parámetros de búsqueda inválidos")

    def list(self, request, *args, **kwargs):
        """
        Sobrescribir para agregar mensajes personalizados y metadatos
        """
        try:
            response = super().list(request, *args, **kwargs)
            
            # Agregar mensaje si no hay resultados
            if not response.data.get('results', []):
                has_search = any([
                    request.GET.get('title'),
                    request.GET.get('artist'),
                    request.GET.get('genre'),
                    request.GET.get('q')
                ])
                
                if has_search:
                    response.data['message'] = "No se encontraron canciones con los criterios especificados"
                else:
                    response.data['message'] = "No hay canciones disponibles"
            
            # Agregar metadatos
            response.data['_metadata'] = {
                'timestamp': timezone.now().isoformat(),
                'page': int(request.GET.get('page', 1)),
                'page_size': self.pagination_class.page_size,
                'has_filters': any([
                    request.GET.get('title'),
                    request.GET.get('artist'),
                    request.GET.get('genre'),
                    request.GET.get('q')
                ])
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error listing songs: {str(e)}")
            return Response(
                {"error": "Error al listar canciones"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def handle_exception(self, exc):
        """
        Manejar excepciones específicas
        """
        if isinstance(exc, (DatabaseError, IntegrityError)):
            logger.error(f"Database error in SongListView: {exc}")
            return Response(
                {"error": "Error de base de datos"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return super().handle_exception(exc)


# ============================================
# 🩺 VISTA DE DIAGNÓSTICO (NUEVA)
# ============================================

@api_view(['GET'])
def debug_suggestions(request):
    """
    Vista de diagnóstico para verificar el estado del sistema
    """
    try:
        # Verificar base de datos
        song_count = Song.objects.count()
        
        # Verificar campos del modelo
        sample_song = Song.objects.first()
        
        # Probar una búsqueda simple
        test_query = "test"
        test_results = Song.objects.filter(
            Q(title__icontains=test_query) |
            Q(artist__icontains=test_query) |
            Q(genre__icontains=test_query)
        ).count()
        
        return Response({
            "status": "ok",
            "database": {
                "total_songs": song_count,
                "sample_song": {
                    "id": sample_song.id if sample_song else None,
                    "title": sample_song.title if sample_song else None,
                    "artist": sample_song.artist if sample_song else None,
                    "genre": sample_song.genre if sample_song else None
                }
            },
            "test_search": {
                "query": test_query,
                "results": test_results
            },
            "timestamp": timezone.now().isoformat()
        })
        
    except Exception as e:
        return Response({
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ============================================
# 🎵 VISTA DE LISTA DE CANCIONES
# ============================================

@extend_schema(
    description="Lista y busca canciones con filtros avanzados",
    parameters=[
        OpenApiParameter(name='title', description='Filtrar por título', required=False, type=str),
        OpenApiParameter(name='artist', description='Filtrar por artista', required=False, type=str),
        OpenApiParameter(name='genre', description='Filtrar por género', required=False, type=str),
        OpenApiParameter(name='q', description='Búsqueda general', required=False, type=str),
        OpenApiParameter(name='page', description='Número de página', required=False, type=int),
        OpenApiParameter(name='page_size', description='Items por página', required=False, type=int),
    ]
)
# ============================================
# 🎵 VISTA DE LISTA DE CANCIONES (MANTENIENDO)
# ============================================

@extend_schema(
    description="Lista y busca canciones con filtros avanzados",
    parameters=[
        OpenApiParameter(name='title', description='Filtrar por título', required=False, type=str),
        OpenApiParameter(name='artist', description='Filtrar por artista', required=False, type=str),
        OpenApiParameter(name='genre', description='Filtrar por género', required=False, type=str),
        OpenApiParameter(name='q', description='Búsqueda general', required=False, type=str),
        OpenApiParameter(name='page', description='Número de página', required=False, type=int),
        OpenApiParameter(name='page_size', description='Items por página', required=False, type=int),
    ]
)
class SongListView(generics.ListCreateAPIView):
    """
    Vista para listar y crear canciones con filtros avanzados
    """
    serializer_class = SongSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['title', 'artist', 'genre']
    
    # Optimizaciones
    renderer_classes = [JSONRenderer]
    pagination_class = PageNumberPagination
    page_size = 20
    max_page_size = 100
    throttle_classes = [UserRateThrottle]

    def get_queryset(self):
        """
        Construye el queryset con filtros avanzados
        """
        try:
            queryset = Song.objects.all()
            
            # Obtener parámetros de filtro
            title = self.request.query_params.get('title', '').strip()
            artist = self.request.query_params.get('artist', '').strip()
            genre = self.request.query_params.get('genre', '').strip()
            general_query = self.request.query_params.get('q', '').strip()
            
            # Aplicar filtros
            if title:
                queryset = queryset.filter(title__icontains=title)
            
            if artist:
                queryset = queryset.filter(artist__icontains=artist)
            
            if genre:
                queryset = queryset.filter(genre__icontains=genre)
            
            # Búsqueda general (en múltiples campos)
            if general_query:
                queryset = queryset.filter(
                    Q(title__icontains=general_query) |
                    Q(artist__icontains=general_query) |
                    Q(genre__icontains=general_query)
                )
            
            # Ordenar por fecha de creación (más recientes primero)
            queryset = queryset.order_by('-created_at')
            
            return queryset
            
        except Exception as e:
            logger.error(f"Error building song query: {str(e)}")
            raise ValidationError("Parámetros de búsqueda inválidos")

    def list(self, request, *args, **kwargs):
        """
        Sobrescribir para agregar mensajes personalizados y metadatos
        """
        try:
            response = super().list(request, *args, **kwargs)
            
            # Agregar mensaje si no hay resultados
            if not response.data.get('results', []):
                has_search = any([
                    request.GET.get('title'),
                    request.GET.get('artist'),
                    request.GET.get('genre'),
                    request.GET.get('q')
                ])
                
                if has_search:
                    response.data['message'] = "No se encontraron canciones con los criterios especificados"
                else:
                    response.data['message'] = "No hay canciones disponibles"
            
            # Agregar metadatos
            response.data['_metadata'] = {
                'timestamp': timezone.now().isoformat(),
                'page': int(request.GET.get('page', 1)),
                'page_size': self.pagination_class.page_size,
                'has_filters': any([
                    request.GET.get('title'),
                    request.GET.get('artist'),
                    request.GET.get('genre'),
                    request.GET.get('q')
                ])
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Error listing songs: {str(e)}")
            return Response(
                {"error": "Error al listar canciones"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def handle_exception(self, exc):
        """
        Manejar excepciones específicas
        """
        if isinstance(exc, (DatabaseError, IntegrityError)):
            logger.error(f"Database error in SongListView: {exc}")
            return Response(
                {"error": "Error de base de datos"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return super().handle_exception(exc)


# ============================================
# 🩺 VISTA DE DIAGNÓSTICO (NUEVA)
# ============================================

@api_view(['GET'])
def debug_suggestions(request):
    """
    Vista de diagnóstico para verificar el estado del sistema
    """
    try:
        # Verificar base de datos
        song_count = Song.objects.count()
        
        # Verificar campos del modelo
        sample_song = Song.objects.first()
        
        # Probar una búsqueda simple
        test_query = "test"
        test_results = Song.objects.filter(
            Q(title__icontains=test_query) |
            Q(artist__icontains=test_query) |
            Q(genre__icontains=test_query)
        ).count()
        
        return Response({
            "status": "ok",
            "database": {
                "total_songs": song_count,
                "sample_song": {
                    "id": sample_song.id if sample_song else None,
                    "title": sample_song.title if sample_song else None,
                    "artist": sample_song.artist if sample_song else None,
                    "genre": sample_song.genre if sample_song else None
                }
            },
            "test_search": {
                "query": test_query,
                "results": test_results
            },
            "timestamp": timezone.now().isoformat()
        })
        
    except Exception as e:
        return Response({
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================
# 🔄 VISTA DE COMPATIBILIDAD - CORREGIDA
# ============================================

@extend_schema(
    description="""
    ⚠️ VISTA DE COMPATIBILIDAD - Para rutas legacy
    
    Esta vista mantiene compatibilidad con frontends antiguos
    que usan la ruta /api2/songs/search/suggestions/
    """,
    parameters=[
        OpenApiParameter(
            name='q',
            description='Texto de búsqueda',
            required=True,
            type=str
        ),
        OpenApiParameter(
            name='limit',
            description='Número máximo de resultados',
            required=False,
            type=int
        )
    ]
)
class SongSearchSuggestionsView(APIView):
    """
    Vista wrapper para rutas legacy - IMPLEMENTACIÓN INDEPENDIENTE
    NO llama a song_suggestions, tiene su propia implementación
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get(self, request):
        """
        Implementación independiente para rutas legacy
        """
        start_time = time.time()
        
        # ============================================
        # CONFIGURACIÓN PARA LEGACY
        # ============================================
        MIN_QUERY_LENGTH = 2
        DEFAULT_LIMIT = 8
        MAX_LIMIT = 20
        CACHE_TIMEOUT = 300
        
        # Obtener query (legacy usa 'q')
        query = request.GET.get('q', '').strip()
        
        # Validar
        if len(query) < MIN_QUERY_LENGTH:
            return Response([], status=status.HTTP_200_OK)
        
        original_query = query
        query = query[:100].lower()
        
        # Configurar límite
        try:
            limit = min(int(request.GET.get('limit', DEFAULT_LIMIT)), MAX_LIMIT)
        except (ValueError, TypeError):
            limit = DEFAULT_LIMIT
        
        # ============================================
        # CACHE
        # ============================================
        cache_key = f"suggestions_legacy_{query}_{limit}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)
        
        # ============================================
        # BÚSQUEDA EN DB
        # ============================================
        try:
            # Búsqueda simple para legacy
            songs = Song.objects.filter(
                Q(title__icontains=query) | 
                Q(artist__icontains=query) | 
                Q(genre__icontains=query)
            ).select_related('uploaded_by').only(
                'title', 'artist', 'genre'
            ).distinct().order_by('title')[:limit]
            
            # Procesar resultados (formato legacy simple)
            suggestions = []
            seen_items = set()
            
            for song in songs:
                item_key = f"{song.title}|{song.artist}"
                if item_key not in seen_items and len(suggestions) < limit:
                    suggestions.append({
                        "title": song.title,
                        "artist": song.artist or "",
                        "genre": song.genre or ""
                    })
                    seen_items.add(item_key)
            
            # Cachear
            if len(query) >= 3:
                cache.set(cache_key, suggestions, CACHE_TIMEOUT)
            
            logger.info(
                f"LEGACY_SUGGESTIONS - query='{original_query}' results={len(suggestions)}"
            )
            
            return Response(suggestions)
            
        except Exception as e:
            logger.error(f"Error en SongSearchSuggestionsView: {str(e)}", exc_info=True)
            return Response([])  # Fallback silencioso para legacy

# Like Song View
@extend_schema(description="Dar o quitar like a una canción")
class LikeSongView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, song_id):
        try:
            song = get_object_or_404(Song, id=song_id)
            like, created = Like.objects.get_or_create(user=request.user, song=song)
            
            if not created:
                like.delete()
                message = "Like removido"
            else:
                message = "Like agregado"

            # Actualización atómica del contador
            song.likes_count = Like.objects.filter(song=song).count()
            song.save(update_fields=['likes_count'])
            cache.set(f"song_{song_id}_likes_count", song.likes_count, timeout=300)

            return Response({
                "message": message,
                "likes_count": song.likes_count,
                "song_id": song_id
            })
        except DatabaseError as e:
            logger.error(f"Database error in like: {e}")
            return Response(
                {"error": "Error de base de datos al procesar el like"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Error in like: {e}")
            return Response(
                {"error": "Error inesperado al procesar el like"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
@extend_schema(
    description="""
    Descargar una canción con streaming eficiente y soporte para reanudación.
    """
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_song_view(request, song_id):
    """
    Vista basada en función para descargas
    """
    CHUNK_SIZE = 64 * 1024
    RATE_CACHE_TIMEOUT = 3600
    
    def _parse_range_header(range_header, file_size):
        """
        Parse simple 'bytes=start-end' header.
        Devuelve (start, end) o None si no hay header.
        """
        if not range_header:
            return None

        try:
            unit, range_spec = range_header.split('=', 1)
        except ValueError:
            return HttpResponse(status=400)

        if unit.strip().lower() != 'bytes':
            return HttpResponse(status=400)

        parts = range_spec.split('-', 1)
        try:
            start = int(parts[0]) if parts[0] else None
            end = int(parts[1]) if len(parts) > 1 and parts[1] != '' else None
        except ValueError:
            return HttpResponse(status=400)

        # Support suffix-byte-range-spec e.g. '-500' (last 500 bytes)
        if start is None and end is not None:
            if end <= 0:
                return HttpResponse(status=416)
            start = max(0, file_size - end)
            end = file_size - 1
        else:
            if start is None:
                start = 0
            if end is None:
                end = file_size - 1

        if start < 0 or end < start or start >= file_size:
            return HttpResponse(status=416)

        if end >= file_size:
            end = file_size - 1

        return (start, end)

    def _build_content_disposition(self, filename):
        """
        Build Content-Disposition supporting unicode via filename* RFC5987.
        """
        # filename safe ascii fallback
        ascii_name = re.sub(r'[^\x20-\x7E]', '_', filename)
        # filename* with utf-8 urlencoded
        from urllib.parse import quote
        filename_star = quote(filename)
        return f"attachment; filename=\"{ascii_name}.mp3\"; filename*=UTF-8''{filename_star}.mp3"

    try:
        # 1. Obtener canción
        song = get_object_or_404(Song, id=song_id)
        if not song.file_key:
            logger.warning("Attempt to download song without file_key id=%s", song_id)
            return Response({"error": "Archivo no disponible para descarga"}, status=status.HTTP_404_NOT_FOUND)

        # 2. Rate limiting simple por cache (por user+song)
        cache_key = f"download_{request.user.id}_{song_id}"
        if cache.get(cache_key):
            return Response(
                {
                    "error": "Límite de descargas alcanzado",
                    "message": "Espere antes de volver a descargar esta canción",
                    "retry_after": RATE_CACHE_TIMEOUT
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # 3. Verificar en R2
        if not check_file_exists(song.file_key):
            logger.error("File not found in R2: %s", song.file_key)
            return Response({"error": "El archivo de audio no está disponible"}, status=status.HTTP_404_NOT_FOUND)

        # 4. Metadata
        file_info = get_file_info(song.file_key)
        if not file_info:
            logger.error("No file_info for key: %s", song.file_key)
            return Response({"error": "Error al obtener información del archivo"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        file_size = int(file_info.get('size', 0))
        content_type = file_info.get('content_type') or get_content_type_from_key(song.file_key)
        etag = file_info.get('etag')

        # 5. Registrar descarga
        try:
            with transaction.atomic():
                Download.objects.create(user=request.user, song=song)
                cache.set(cache_key, True, timeout=RATE_CACHE_TIMEOUT)
        except IntegrityError:
            logger.exception("Error registrando descarga (se continúa con el stream)")

        # 6. Parse Range header (si existe)
        range_header = request.META.get('HTTP_RANGE', '').strip()
        parsed = _parse_range_header(range_header, file_size) if range_header else None
        if isinstance(parsed, HttpResponse):
            return parsed  # error 400/416

        if parsed:
            start, end = parsed
            status_code = 206
            content_length = (end - start) + 1
            content_range = f"bytes {start}-{end}/{file_size}"
            
            # Construir Range header para R2
            range_for_r2 = f"bytes={start}-{end}"
            logger.debug(f"DOWNLOAD Range requested: {range_header} -> {range_for_r2}")
        else:
            start = None
            end = None
            status_code = 200
            content_length = file_size
            content_range = None
            range_for_r2 = None

        # ✅ Llamada a stream_file_from_r2
        s3_resp = stream_file_from_r2(
            song.file_key, 
            range_header=range_for_r2
        )

        if not s3_resp or 'Body' not in s3_resp:
            logger.error("stream_file_from_r2 returned no body for key %s", song.file_key)
            return Response({"error": "Error al acceder al archivo"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        body = s3_resp['Body']

        # 8. Filename seguro (unicode)
        filename = slugify(song.title or f"song_{song.id}", allow_unicode=True)

        # 9. StreamingHttpResponse con closure seguro
        def stream_generator():
            try:
                bytes_streamed = 0
                for chunk in body.iter_chunks(chunk_size=CHUNK_SIZE):
                    if chunk:
                        bytes_streamed += len(chunk)
                        yield chunk
                logger.debug(f"DOWNLOAD Complete: {bytes_streamed} bytes downloaded")
            finally:
                try:
                    body.close()
                    logger.debug("DOWNLOAD Body closed successfully")
                except Exception:
                    logger.debug("body.close() failed in download")

        # ✅ Usar StreamingHttpResponse
        response = StreamingHttpResponse(
            stream_generator(), 
            status=status_code, 
            content_type=content_type
        )
        
        # Configurar headers
        from urllib.parse import quote
        filename_star = quote(filename)
        response['Content-Disposition'] = f"attachment; filename=\"{filename}.mp3\"; filename*=UTF-8''{filename_star}.mp3"
        response['Content-Transfer-Encoding'] = 'binary'
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['Content-Length'] = str(content_length)
        if etag:
            response['ETag'] = etag
        if content_range:
            response['Content-Range'] = content_range

        logger.info("DOWNLOAD START - user=%s song=%s size=%s range=%s", 
                   request.user.id, song_id, content_length, 
                   f"{start}-{end}" if start is not None else "full")
        return response

    except Exception as exc:
        logger.exception("ERROR DOWNLOAD - song=%s user=%s", song_id, getattr(request.user, 'id', None))
        return Response(
            {"error": "Error interno del servidor", "message": "No se pudo completar la descarga."}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class StreamSongView(APIView):
    """
    Streaming de canciones con soporte completo de HTTP Range (seek/reanudación)
    OPTIMIZADO para África Central con timeout protection
    """
    permission_classes = [IsAuthenticated]
    CHUNK_SIZE = 32 * 1024  # 32KB - OPTIMIZADO para redes africanas
    STREAM_TIMEOUT = 30  # 30 segundos máximo por stream

    def _parse_range_header(self, range_header, file_size):
        """
        Parser reutilizable para Range headers
        """
        if not range_header:
            return None

        try:
            unit, range_spec = range_header.split('=', 1)
        except ValueError:
            return None

        if unit.strip().lower() != 'bytes':
            return None

        parts = range_spec.split('-', 1)
        try:
            start = int(parts[0]) if parts[0] else None
            # ✅ YA CORREGIDO: len(parts) > 1
            end = int(parts[1]) if len(parts) > 1 and parts[1] != '' else None
        except ValueError:
            return None

        # Soporte para suffix-byte-range-spec
        if start is None and end is not None:
            if end <= 0:
                return None
            start = max(0, file_size - end)
            end = file_size - 1
        else:
            if start is None:
                start = 0
            if end is None:
                end = file_size - 1

        if start < 0 or end < start or start >= file_size:
            return None

        if end >= file_size:
            end = file_size - 1

        return (start, end)

    def _safe_stream_generator(self, body, chunk_size, timeout):
        """
        Generador de streaming con protección contra timeout
        """
        bytes_yielded = 0
        max_bytes = 50 * 1024 * 1024  # 50MB máximo por conexión
        
        try:
            for chunk in body.iter_chunks(chunk_size=chunk_size):
                if not chunk:
                    break  # Fin del stream
                
                bytes_yielded += len(chunk)
                
                # Protección: máximo 50MB por stream
                if bytes_yielded > max_bytes:
                    logger.warning(f"Stream excedió límite de {max_bytes} bytes")
                    break
                
                yield chunk
                
        except Exception as e:
            logger.error(f"Error en stream generator: {e}")
            yield b''
        finally:
            try:
                body.close()
            except Exception as e:
                logger.debug(f"Error cerrando body: {e}")

    @extend_schema(
        description="""
        Reproducir una canción en streaming con soporte completo para seek y reanudación.
        OPTIMIZADO para redes africanas con chunk reducido.
        """
    )
    def get(self, request, song_id):
        try:
            # 1️⃣ Obtener canción y validar
            song = get_object_or_404(Song, id=song_id)
            if not song.file_key:
                return Response(
                    {"error": "Archivo no disponible para streaming"}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # 2️⃣ Verificar que el archivo existe
            if not check_file_exists(song.file_key):
                logger.error("File not found in R2 for streaming: %s", song.file_key)
                return Response(
                    {"error": "El archivo de audio no está disponible en este momento"},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 3️⃣ Obtener metadata
            file_info = get_file_info(song.file_key)
            if not file_info:
                return Response(
                    {"error": "Error al obtener información del archivo"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            file_size = int(file_info.get('size', 0))
            content_type = file_info.get('content_type') or get_content_type_from_key(song.file_key)

            # 4️⃣ Parse Range header
            range_header = request.META.get('HTTP_RANGE', '').strip()
            parsed = self._parse_range_header(range_header, file_size) if range_header else None
            
            if parsed is None and range_header:
                return Response(
                    {"error": "Invalid Range header"},
                    status=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE
                )

            if parsed:
                start, end = parsed
                status_code = 206
                content_length = (end - start) + 1
                content_range = f"bytes {start}-{end}/{file_size}"
                range_for_r2 = f"bytes={start}-{end}"
            else:
                start = None
                end = None
                status_code = 200
                content_length = file_size
                content_range = None
                range_for_r2 = None

            # 5️⃣ Stream desde R2 con timeout
            s3_resp = stream_file_from_r2(
                song.file_key, 
                range_header=range_for_r2
            )

            if not s3_resp or 'Body' not in s3_resp:
                logger.error("stream_file_from_r2 returned no body for key %s", song.file_key)
                return Response(
                    {"error": "Error al acceder al archivo para streaming"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            body = s3_resp['Body']

            # Usar ContentLength de R2 si está disponible
            r2_content_length = s3_resp.get('ContentLength')
            if r2_content_length is not None:
                content_length = r2_content_length

            # 6️⃣ Crear respuesta
            response = StreamingHttpResponse(
                self._safe_stream_generator(body, self.CHUNK_SIZE, self.STREAM_TIMEOUT), 
                status=status_code, 
                content_type=content_type
            )

            # 7️⃣ Headers optimizados
            response['Content-Length'] = str(content_length)
            response['Content-Type'] = content_type
            response['Accept-Ranges'] = 'bytes'
            response['Cache-Control'] = 'public, max-age=3600'
            response['X-Content-Duration'] = str(song.duration) if song.duration else '0'
            response['X-Audio-Title'] = song.title
            response['X-Audio-Artist'] = song.artist or 'Unknown Artist'
            response['X-Chunk-Size'] = str(self.CHUNK_SIZE)

            # Usar ContentRange de R2 si está disponible
            r2_content_range = s3_resp.get('ContentRange')
            if r2_content_range:
                response['Content-Range'] = r2_content_range
            elif content_range:
                response['Content-Range'] = content_range

            # ETag para caching
            r2_etag = s3_resp.get('ETag')
            if r2_etag:
                response['ETag'] = r2_etag.strip('"')

            # 8️⃣ Log de streaming
            range_info = f"{start}-{end}" if start is not None else "full"
            logger.info(
                "STREAM start user=%s song=%s size=%s range=%s duration=%s chunksize=%s",
                request.user.id, song_id, content_length, range_info, 
                song.duration or 'unknown', self.CHUNK_SIZE
            )

            return response

        except Exception as exc:
            logger.exception("ERROR STREAM - song=%s user=%s", song_id, getattr(request.user, 'id', None))
            return Response(
                {
                    "error": "Error en streaming",
                    "message": "No se pudo iniciar la reproducción. Intente nuevamente."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )          
# Comments Views
@extend_schema(tags=['Comentarios'])
class CommentListCreateView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = CommentPagination

    def get_queryset(self):
        try:
            song_id = self.kwargs.get('song_id')
            if not song_id:
                logger.error("No se proporcionó song_id en la URL")
                return Comment.objects.none()
                
            return Comment.objects.filter(song_id=song_id).select_related('user').order_by("-created_at")
        except KeyError as e:
            logger.error(f"Error: Parámetro 'song_id' no encontrado en URL: {e}")
            return Comment.objects.none()
        except Exception as e:
            logger.error(f"Error getting comments: {e}")
            raise ValidationError("Error al obtener comentarios")

    def perform_create(self, serializer):
        try:
            song_id = self.kwargs.get('song_id')
            if not song_id:
                raise ValidationError("ID de canción no proporcionado en la URL")
            
            song = Song.objects.filter(id=song_id).first()
            if not song:
                raise ValidationError("La canción especificada no existe")
                
            serializer.save(user=self.request.user, song_id=song_id)
            cache.delete(f"song_{song_id}_comments")
            
        except IntegrityError as e:
            logger.error(f"Error creating comment: {e}")
            raise ValidationError("Error de integridad al crear comentario")
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error creating comment: {e}")
            raise ValidationError("Error inesperado al crear comentario")

@extend_schema(tags=['Comentarios'])
class SongCommentsDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def handle_exception(self, exc):
        if isinstance(exc, DatabaseError):
            logger.error(f"Database error in comment detail: {exc}")
            return Response(
                {"error": "Error de base de datos al procesar comentario"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return super().handle_exception(exc)

    def perform_update(self, serializer):
        try:
            if serializer.instance.user != self.request.user:
                raise PermissionDenied("No puedes editar este comentario")
            super().perform_update(serializer)
        except DatabaseError as e:
            logger.error(f"Database error updating comment: {e}")
            raise ValidationError("Error al actualizar el comentario")

    def perform_destroy(self, instance):
        try:
            if instance.user != self.request.user:
                raise PermissionDenied("No puedes eliminar este comentario")
            super().perform_destroy(instance)
            cache.delete(f"song_{instance.song_id}_comments")
        except DatabaseError as e:
            logger.error(f"Database error deleting comment: {e}")
            raise ValidationError("Error al eliminar el comentario")

# Artist List View
@extend_schema(description="Lista de artistas únicos con cache")
class ArtistListView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        try:
            artists = cache.get_or_set(
                "unique_artists_list",
                lambda: list(Song.objects.values_list("artist", flat=True).distinct()),
                600
            )
            return Response({"artists": artists})
        except DatabaseError as e:
            logger.error(f"Database error getting artists: {e}")
            return Response(
                {"error": "Error al obtener la lista de artistas"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Error getting artists: {e}")
            return Response(
                {"error": "Error inesperado al obtener artistas"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Random Songs View
@extend_schema(description="Selección aleatoria de canciones")
class RandomSongsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            num_songs = 15
            all_songs = Song.objects.all()

            if not all_songs.exists():
                return Response(
                    {"error": "No hay canciones disponibles en este momento."},
                    status=status.HTTP_404_NOT_FOUND
                )

            random_songs = random.sample(list(all_songs), min(num_songs, all_songs.count()))
            serializer = SongSerializer(random_songs, many=True)

            return Response({"random_songs": serializer.data}, status=status.HTTP_200_OK)
        except ValueError as e:
            logger.error(f"Value error in random songs: {e}")
            return Response(
                {"error": "Error en la selección de canciones"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Error in random songs: {e}")
            return Response(
                {"error": "Error al obtener canciones aleatorias"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Vista adicional para eliminar canciones con limpieza en R2
@extend_schema(description="Eliminar una canción y su archivo en R2")
class SongDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, song_id):
        try:
            song = get_object_or_404(Song, id=song_id)
            
            # Verificar permisos (solo el propietario o admin puede eliminar)
            if song.uploaded_by != request.user and not request.user.is_staff:
                raise PermissionDenied("No tienes permisos para eliminar esta canción")
            
            # Eliminar archivo de R2 si existe
            if song.file_key:
                delete_file_from_r2(song.file_key)
            
            # Eliminar la canción de la base de datos
            song.delete()
            
            return Response(
                {"message": "Canción eliminada correctamente"},
                status=status.HTTP_200_OK
            )
            
        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f"Error deleting song: {e}")
            return Response(
                {"error": "Error al eliminar la canción"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
# Al final de api2/views.py - Agrega estas vistas para manejo de errores
from django.http import JsonResponse

def custom_404(request, exception=None):
    return JsonResponse({
        'error': 'Página no encontrada',
        'message': 'El recurso solicitado no existe'
    }, status=404)

def custom_500(request):
    return JsonResponse({
        'error': 'Error interno del servidor',
        'message': 'Ha ocurrido un error inesperado'
    }, status=500)


# api2/views.py - Agrega esto al final del archivo

import logging
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, OpenApiResponse

# Importa tus modelos y serializers
from .models import Song
from .serializers import SongUploadSerializer

logger = logging.getLogger(__name__)

class SongUploadView(APIView):
    """
    Vista SIMPLIFICADA que delega todo al serializer
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        # Rate limiting simple
        from django.core.cache import cache
        
        user_key = f"upload_{request.user.id}_{timezone.now().hour}"
        if cache.get(user_key, 0) >= 20:
            return Response(
                {"error": "Límite de subidas por hora alcanzado"},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        # DELEGAR TODO al serializer
        serializer = SongUploadSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            try:
                song = serializer.save()  # Serializer maneja uploads y creación
                
                # Actualizar rate limit
                cache.set(user_key, cache.get(user_key, 0) + 1, 3600)
                
                return Response({
                    "message": "Canción subida exitosamente",
                    "song_id": song.id,
                    "title": song.title,
                    "artist": song.artist,
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                logger.error(f"Upload error: {e}")
                return Response(
                    {"error": "Error al procesar la subida"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    description="Verificar estado de archivos en R2 para una canción",
    responses={
        200: OpenApiResponse(description="Estado de archivos obtenido"),
        404: OpenApiResponse(description="Canción no encontrada"),
        403: OpenApiResponse(description="No autorizado")
    }
)
 # ← IMPORTANTE: Agrega este import en la parte superior

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_song_files(request, song_id):
    """
    Verifica el estado de los archivos de una canción en R2
    """
    try:
        song = get_object_or_404(Song, id=song_id)
        
        # Verificar permisos (solo owner o admin)
        if not (request.user == song.uploaded_by or request.user.is_staff):
            return Response(
                {"error": "No tienes permisos para verificar esta canción"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        from .r2_utils import get_file_info
        
        file_status = {
            'song_id': song_id,
            'title': song.title,
            'artist': song.artist or '',
            'uploaded_by': song.uploaded_by.username if song.uploaded_by else None,
            'files': {}
        }
        
        # Verificar archivo de audio
        if song.file_key and song.file_key != "songs/temp_file":
            audio_info = get_file_info(song.file_key)
            file_status['files']['audio'] = {
                'key': song.file_key,
                'exists': bool(audio_info),  # get_file_info devuelve None si no existe
                'size': audio_info.get('size') if audio_info else 0,
                'content_type': audio_info.get('content_type', 'audio/mpeg') if audio_info else None
            }
        else:
            file_status['files']['audio'] = {'exists': False, 'error': 'No file_key o temp_file'}
        
        # Verificar imagen (usa image_key, no image)
        if song.image_key:
            image_info = get_file_info(song.image_key)
            file_status['files']['image'] = {
                'key': song.image_key,
                'exists': bool(image_info),
                'size': image_info.get('size') if image_info else 0,
                'content_type': image_info.get('content_type', 'image/jpeg') if image_info else None
            }
        
        return Response(file_status)
        
    except Http404:  # ← MANEJO EXPLÍCITO DE 404
        return Response(
            {"error": "Canción no encontrada"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error check_song_files {song_id}: {e}")
        return Response(
            {"error": "Error al verificar archivos"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
# 📊 VISTAS DE MÉTRICAS - AGREGAR AL FINAL DE views.py
# =============================================================================

@extend_schema(
    description="Métricas completas del sistema para administradores",
    responses={
        200: OpenApiResponse(description="Métricas obtenidas exitosamente"),
        403: OpenApiResponse(description="No autorizado - Se requieren permisos de administrador")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_metrics(request):
    """
    Métricas detalladas para administradores
    """
    # Verificar que el usuario es staff
    if not request.user.is_staff:
        return Response(
            {"error": "Se requieren permisos de administrador para acceder a estas métricas"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now()
        last_7_days = today - timedelta(days=7)
        
        metrics = {
            "timestamp": today.isoformat(),
            "general_stats": {
                "total_songs": Song.objects.count(),
                "total_users": User.objects.count(),
                "total_likes": Like.objects.count(),
                "total_downloads": Download.objects.count(),
                "total_comments": Comment.objects.count(),
                "total_events": MusicEvent.objects.count(),
            },
            "recent_activity": {
                "new_songs_7d": Song.objects.filter(created_at__gte=last_7_days).count(),
                "new_users_7d": User.objects.filter(date_joined__gte=last_7_days).count(),
                "new_likes_7d": Like.objects.filter(created_at__gte=last_7_days).count(),
            },
            "popular_content": {
                "most_liked_songs": list(Song.objects.annotate(
                    like_count=Count('likes')
                ).order_by('-like_count')[:5].values('id', 'title', 'artist', 'like_count')),
                "most_downloaded_songs": list(Song.objects.annotate(
                    download_count=Count('downloads')
                ).order_by('-download_count')[:5].values('id', 'title', 'artist', 'download_count')),
            }
        }
        
        return Response(metrics, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error obteniendo métricas de administrador: {e}")
        return Response(
            {"error": "Error al generar las métricas del sistema"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    description="Métricas personales del usuario",
    responses={
        200: OpenApiResponse(description="Métricas personales obtenidas exitosamente")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_personal_metrics(request):
    """
    Métricas personales para el usuario autenticado
    """
    try:
        user = request.user
        from django.utils import timezone
        from datetime import timedelta
        
        last_30_days = timezone.now() - timedelta(days=30)
        
        metrics = {
            "user_info": {
                "username": user.username,
                "date_joined": user.date_joined.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
            },
            "personal_stats": {
                "songs_uploaded": Song.objects.filter(uploaded_by=user).count(),
                "likes_given": Like.objects.filter(user=user).count(),
                "comments_made": Comment.objects.filter(user=user).count(),
                "downloads_made": Download.objects.filter(user=user).count(),
            },
            "recent_activity_30d": {
                "recent_likes": Like.objects.filter(
                    user=user, 
                    created_at__gte=last_30_days
                ).count(),
                "recent_downloads": Download.objects.filter(
                    user=user,
                    downloaded_at__gte=last_30_days
                ).count(),
            }
        }
        
        return Response(metrics, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error obteniendo métricas personales: {e}")
        return Response(
            {"error": "Error al generar tus métricas personales"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    description="Health check completo del sistema con métricas",
    responses={
        200: OpenApiResponse(description="Sistema saludable"),
        503: OpenApiResponse(description="Problemas detectados")
    }
)
@api_view(['GET'])
def health_check(request):
    """
    Health check detallado para monitoring y load balancers
    """
    health_status = {
        "status": "OK",
        "timestamp": timezone.now().isoformat(),
        "service": "DjiMusic API",
        "version": "1.0.0",
        "checks": {}
    }
    
    all_ok = True
    
    try:
        # 1. Check de base de datos
        db_start = timezone.now()
        db_count = Song.objects.count()
        db_time = (timezone.now() - db_start).total_seconds() * 1000
        
        health_status["checks"]["database"] = {
            "status": "OK",
            "response_time_ms": round(db_time, 2),
            "song_count": db_count,
            "message": f"Database accessible with {db_count} songs"
        }
        
        # 2. Check de cache
        cache_start = timezone.now()
        cache.set('health_check_test', 'ok', 10)
        cache_test = cache.get('health_check_test')
        cache_time = (timezone.now() - cache_start).total_seconds() * 1000
        
        health_status["checks"]["cache"] = {
            "status": "OK" if cache_test == 'ok' else "ERROR",
            "response_time_ms": round(cache_time, 2),
            "message": "Cache system working" if cache_test == 'ok' else "Cache failure"
        }
        
        if cache_test != 'ok':
            all_ok = False
        
        # 3. Check de R2 (opcional, puede ser más lento)
        try:
            from .r2_utils import check_r2_connection
            r2_start = timezone.now()
            r2_ok = check_r2_connection()  # Necesitarías implementar esta función
            r2_time = (timezone.now() - r2_start).total_seconds() * 1000
            
            health_status["checks"]["r2_storage"] = {
                "status": "OK" if r2_ok else "WARNING",
                "response_time_ms": round(r2_time, 2),
                "message": "R2 storage accessible" if r2_ok else "R2 connection issues"
            }
            
            if not r2_ok:
                all_ok = False
                health_status["status"] = "DEGRADED"
        except Exception as r2_error:
            health_status["checks"]["r2_storage"] = {
                "status": "ERROR",
                "message": f"R2 check failed: {str(r2_error)[:100]}"
            }
            all_ok = False
        
        # 4. Métricas del sistema
        health_status["metrics"] = {
            "active_users_last_hour": User.objects.filter(
                last_login__gte=timezone.now() - timezone.timedelta(hours=1)
            ).count(),
            "songs_uploaded_today": Song.objects.filter(
                created_at__date=timezone.now().date()
            ).count(),
            "total_likes": Like.objects.count(),
            "total_downloads": Download.objects.count(),
            "uptime": "TODO"  # Podrías agregar uptime real
        }
        
        # 5. Estado general
        if not all_ok:
            health_status["status"] = "DEGRADED" if health_status["status"] == "OK" else "ERROR"
        
        status_code = 200 if all_ok else 503
        
        return Response(health_status, status=status_code)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        
        return Response({
            "status": "ERROR",
            "timestamp": timezone.now().isoformat(),
            "service": "DjiMusic API",
            "error": str(e)[:200],
            "checks": {
                "overall": {
                    "status": "ERROR",
                    "message": f"Health check failed: {type(e).__name__}"
                }
            }
        }, status=503)
    
@extend_schema(
    description="Búsqueda completa para frontend moderno (todo en una respuesta)",
    parameters=[
        OpenApiParameter(name='q', description='Texto de búsqueda', required=True, type=str),
        OpenApiParameter(name='limit', description='Límite por categoría (default: 5, max: 10)', required=False, type=int),
        OpenApiParameter(name='include', description='Incluir: songs,artists,suggestions,all', required=False, type=str)
    ]  # ← CIERRA LA LISTA
)  # ← ¡Y ESTE ES EL PARÉNTESIS QUE FALTA! CIERRA EL DECORADOR
@api_view(['GET'])
@permission_classes([IsAuthenticatedOrReadOnly])
def complete_search(request):
    """
    Endpoint único para el search bar profesional
    Devuelve canciones, artistas y sugerencias en una sola respuesta
    Optimizado para el frontend React + search.service.js
    """
    query = request.GET.get('q', '').strip()
    limit = min(int(request.GET.get('limit', 5)), 10)
    include = request.GET.get('include', 'all').split(',')

    # Validaciones básicas
    if not query or len(query) < 2:
        return Response({
            "songs": [],
            "artists": [],
            "suggestions": [],
            "albums": [],
            "playlists": [],
            "_metadata": {
                "query": query,
                "timestamp": timezone.now().isoformat(),
                "source": "empty_query",
                "total": 0,
                "cache_hit": False
            }
        })

    if len(query) > 100:
        query = query[:100]

    try:
        from django.db.models import Count, F, Value, CharField, Case, When
        from django.core.cache import cache
        import hashlib
        import json

        # Generar cache key
        cache_key = f"complete_search:{hashlib.md5(f'{query}:{limit}:{include}'.encode()).hexdigest()}"
        cache_timeout = 300  # 5 minutos para búsquedas

        # Intentar cache primero
        if 'no_cache' not in request.GET:
            cached = cache.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT para búsqueda: {query}")
                cached['_metadata']['cache_hit'] = True
                cached['_metadata']['cached_at'] = timezone.now().isoformat()
                return Response(cached)

        logger.debug(f"Cache MISS para búsqueda: {query}")

        result = {
            "songs": [],
            "artists": [],
            "suggestions": [],
            "albums": [],
            "playlists": [],
        }

        # 1. BUSCAR CANCIONES (si está incluido) - ERROR CORREGIDO AQUÍ
        if 'all' in include or 'songs' in include:
            songs = Song.objects.filter(
                Q(title__icontains=query) | Q(artist__icontains=query) | Q(genre__icontains=query)
            ).annotate(
                # SOLO anotar match_relevance - NO usar likes_count aquí
                # porque ya existe como campo en el modelo Song
                match_relevance=Case(
                    When(title__icontains=query, artist__icontains=query, then=Value(100)),
                    When(title__icontains=query, then=Value(80)),
                    When(artist__icontains=query, then=Value(60)),
                    When(genre__icontains=query, then=Value(40)),
                    default=Value(0),
                    output_field=CharField()
                )
            ).select_related('uploaded_by').values(
                'id', 'title', 'artist', 'genre', 'duration',
                'uploaded_by__username', 'created_at', 'likes_count',  # ← Usar campo existente del modelo
                'file_key', 'stream_url', 'download_url'
            ).order_by('-match_relevance', '-likes_count', '-created_at')[:limit]  # ← Ordenar por campo existente

            result["songs"] = list(songs)

        # 2. BUSCAR ARTISTAS (si está incluido)
        if 'all' in include or 'artists' in include:
            from django.db.models import Subquery, OuterRef

            artists = Song.objects.filter(
                artist__icontains=query
            ).values('artist').annotate(
                song_count=Count('id'),
                latest_song_title=Subquery(
                    Song.objects.filter(artist=OuterRef('artist'))
                    .order_by('-created_at')
                    .values('title')[:1]
                ),
                latest_song_id=Subquery(
                    Song.objects.filter(artist=OuterRef('artist'))
                    .order_by('-created_at')
                    .values('id')[:1]
                ),
                total_likes=Subquery(
                    Song.objects.filter(artist=OuterRef('artist'))
                    .annotate(total=Count('likes'))
                    .values('total')[:1]
                )
            ).distinct().order_by('-song_count')[:limit]

            result["artists"] = [
                {
                    "name": a['artist'],
                    "song_count": a['song_count'],
                    "latest_song": {
                        "title": a['latest_song_title'],
                        "id": a['latest_song_id']
                    } if a['latest_song_title'] else None,
                    "total_likes": a['total_likes'] or 0
                }
                for a in artists
            ]

        # 3. SUGERENCIAS (usar el endpoint optimizado)
        if 'all' in include or 'suggestions' in include:
            # Crear request simulada para llamar a song_suggestions internamente
            from django.test import RequestFactory
            factory = RequestFactory()
            mock_request = factory.get(f'/api2/suggestions/?query={query}&limit={limit}')
            mock_request.user = request.user

            # Llamar a la función optimizada
            suggestions_response = song_suggestions(mock_request)
            if suggestions_response.status_code == 200:
                result["suggestions"] = suggestions_response.data.get("suggestions", [])

        # 4. METADATA ENRIQUECIDA
        total_items = (
            len(result["songs"]) + 
            len(result["artists"]) + 
            len(result["suggestions"])
        )

        metadata = {
            "query": query,
            "timestamp": timezone.now().isoformat(),
            "source": "network",
            "total": total_items,
            "cache_hit": False,
            "limits": {
                "songs": len(result["songs"]),
                "artists": len(result["artists"]),
                "suggestions": len(result["suggestions"])
            },
            "query_length": len(query),
            "response_time_ms": 0  # Podrías calcular esto
        }

        result["_metadata"] = metadata

        # Guardar en cache (excepto para queries muy cortas)
        if len(query) >= 3 and total_items > 0:
            cache.set(cache_key, result, timeout=cache_timeout)
            logger.debug(f"Cache SET para búsqueda: {query} ({total_items} items)")

        return Response(result)

    except Exception as e:
        logger.error(f"Error en búsqueda completa para '{query}': {e}", exc_info=True)

        return Response({
            "songs": [],
            "artists": [],
            "suggestions": [],
            "albums": [],
            "playlist": [],
            "_metadata": {
                "query": query,
                "timestamp": timezone.now().isoformat(),
                "source": "error",
                "total": 0,
                "error": "search_failed",
                "cache_hit": False
            }
        }, status=200)  # Siempre 200 para que frontend maneje el error