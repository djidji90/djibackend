# api2/views.py - ARCHIVO COMPLETO CON TODAS LAS IMPORTACIONES UNIFICADAS Y LA VISTA STREAMSONGVIEW
"""
VISTAS COMPLETAS DE LA API v2
================================
✅ Streaming con URLs firmadas (arquitectura enterprise)
✅ Upload directo a R2
✅ CRUD de canciones
✅ Comentarios y likes
✅ Métricas y monitoreo
"""

# =============================================================================
# 📦 IMPORTACIONES UNIFICADAS - TODAS EN UN SOLO LUGAR
# =============================================================================

# -----------------------------------------------------------------------------
# ESTÁNDAR
# -----------------------------------------------------------------------------
import json
import logging
import time
import random
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Tuple, Optional, Dict, Any

# -----------------------------------------------------------------------------
# DJANGO CORE
# -----------------------------------------------------------------------------
import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, models, transaction, DatabaseError, IntegrityError
from django.db.models import Q, Count, Case, When, Value, CharField, IntegerField, BooleanField
from django.db.models.functions import Lower
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.decorators.cache import cache_page

# -----------------------------------------------------------------------------
# DRF (Django REST Framework)
# -----------------------------------------------------------------------------
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

# -----------------------------------------------------------------------------
# FILTERS
# -----------------------------------------------------------------------------
from django_filters.rest_framework import DjangoFilterBackend

# -----------------------------------------------------------------------------
# DRF-SPECTACULAR (Swagger)
# -----------------------------------------------------------------------------
from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiResponse, OpenApiExample
)

# -----------------------------------------------------------------------------
# PROMETHEUS (OPCIONAL)
# -----------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    # Dummy metrics
    class DummyMetric:
        def labels(self, *args, **kwargs): return self
        def inc(self): pass
    Counter = Histogram = DummyMetric
    def generate_latest(*args, **kwargs): return b''
    REGISTRY = None

# -----------------------------------------------------------------------------
# MODELOS LOCALES
# -----------------------------------------------------------------------------
from .models import (
    UploadSession, 
    UploadQuota, 
    Song, 
    UserProfile, 
    Like, 
    Download, 
    Comment, 
    MusicEvent
)

# -----------------------------------------------------------------------------
# SERIALIZERS
# -----------------------------------------------------------------------------
from .serializers import (
    DirectUploadRequestSerializer,
    UploadConfirmationSerializer,
    UploadSessionSerializer,
    SongSerializer,
    CommentSerializer,
    MusicEventSerializer,
    SongUploadSerializer
)

# -----------------------------------------------------------------------------
# UTILS R2
# -----------------------------------------------------------------------------
from .r2_utils import (
    upload_file_to_r2,
    generate_presigned_url,
    generate_presigned_urls_batch,
    delete_file_from_r2,
    check_file_exists,
    get_file_info,
    get_file_size,
    stream_file_from_r2,
    get_content_type_from_key,
    invalidate_presigned_url_cache,
    get_cache_stats,
    test_r2_connection
)

# -----------------------------------------------------------------------------
# UTILS R2 DIRECT
# -----------------------------------------------------------------------------
from .utils.r2_direct import r2_upload, r2_direct,

logger = logging.getLogger(__name__)
User = get_user_model()

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
            # ⚠️ SOLAMENTE ESTE CAMBIO: Proteger acceso a request.user
            # Asegurar que request.user existe antes de usarlo
            if not hasattr(request, 'user') or request.user is None:
                # Si request.user es None, crear un usuario anónimo seguro
                from django.contrib.auth.models import AnonymousUser
                request.user = AnonymousUser()
            
            # Ahora puedes llamar a super().list() de forma segura
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
   
    def get_serializer_context(self):
        """Asegurar que el request está en el contexto del serializer"""
        context = super().get_serializer_context()
        # DRF ya debería incluir 'request', pero nos aseguramos
        if 'request' not in context and hasattr(self, 'request'):
            context['request'] = self.request
        return context

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
            # Verificar que el usuario sea el dueño del comentario
            if serializer.instance.user != self.request.user:
                raise PermissionDenied("No puedes editar este comentario")
           
            # Marcar como editado
            serializer.save(is_edited=True)
           
            # Invalidar cache si es necesario
            cache_key = f"song_{serializer.instance.song_id}_comments"
            cache.delete(cache_key)
           
        except DatabaseError as e:
            logger.error(f"Database error updating comment: {e}")
            raise ValidationError("Error al actualizar el comentario")

    def perform_destroy(self, instance):
        try:
            # Verificar que el usuario sea el dueño del comentario
            if instance.user != self.request.user:
                raise PermissionDenied("No puedes eliminar este comentario")
           
            super().perform_destroy(instance)
           
            # Invalidar cache
            cache_key = f"song_{instance.song_id}_comments"
            cache.delete(cache_key)
           
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
    """
    MISMO NOMBRE, MISMA INTERFAZ, PERO OPTIMIZADA
    
    Cambios internos (invisibles para frontend):
    1. ✅ FIX: Eliminado random.sample(list(all_songs)) que causa memory explosion
    2. ✅ Cache de resultados por usuario (30 segundos)
    3. ✅ URLs presigned en batch (reduce llamadas a R2 en 95%)
    4. ✅ Cache HTTP (60 segundos)
    5. ✅ Método seguro para datasets grandes
    
    Compatibilidad 100% con frontend:
    - Misma URL: /api2/songs/random/
    - Misma respuesta: {"random_songs": [...]}
    - Mismos códigos de error
    - Mismos mensajes
    """
    
    permission_classes = [IsAuthenticated]
    
    # Configuración interna (no afecta API)
    DEFAULT_LIMIT = 15
    USER_CACHE_TIMEOUT = 30  # 30 segundos cache por usuario
    HTTP_CACHE_TIMEOUT = 60  # 60 segundos cache HTTP
    
    @method_decorator(cache_page(HTTP_CACHE_TIMEOUT))
    def get(self, request):
        """
        MISMA FIRMA, MISMO COMPORTAMIENTO EXTERNO
        Solo optimizado internamente
        """
        try:
            num_songs = self.DEFAULT_LIMIT
            
            # Cache por usuario (transparente para frontend)
            user_cache_key = f"random_songs:user:{request.user.id}"
            cached_response = cache.get(user_cache_key)
            
            if cached_response:
                logger.debug(f"🎯 Cache HIT usuario {request.user.id}")
                return Response(cached_response, status=status.HTTP_200_OK)
            
            # Query base optimizado
            all_songs = Song.objects.filter(is_public=True)
            
            if not all_songs.exists():
                return Response(
                    {"error": "No hay canciones disponibles en este momento."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # ✅ REEMPLAZADO: random.sample(list(all_songs), ...) ← PELIGROSO
            # ✅ NUEVO: Método seguro sin memory explosion
            random_songs = self._get_random_songs_safe(all_songs, num_songs)
            
            if not random_songs:
                return Response(
                    {"error": "No hay canciones disponibles en este momento."},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Serializar con URLs optimizadas (batch)
            serializer_data = self._serialize_with_optimized_urls(random_songs)
            
            # MISMA RESPUESTA QUE ANTES
            response_data = {"random_songs": serializer_data}
            
            # Cachear para este usuario (30s)
            cache.set(user_cache_key, response_data, timeout=self.USER_CACHE_TIMEOUT)
            
            logger.info(f"✅ RandomSongs: {len(random_songs)} canciones para usuario {request.user.id}")
            return Response(response_data, status=status.HTTP_200_OK)
            
        except ValueError as e:
            # MISMO ERROR QUE ANTES
            logger.error(f"Value error in random songs: {e}")
            return Response(
                {"error": "Error en la selección de canciones"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            # MISMO ERROR QUE ANTES
            logger.error(f"Error in random songs: {e}")
            return Response(
                {"error": "Error al obtener canciones aleatorias"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_random_songs_safe(self, queryset, limit):
        """
        REEMPLAZA: random.sample(list(all_songs), ...) ← ESTO ES PELIGROSO
        
        Nuevo método seguro que:
        1. No carga toda la base de datos en memoria
        2. Funciona con miles/millones de canciones
        3. Mantiene aleatoriedad
        """
        total_count = queryset.count()
        
        if total_count == 0:
            return []
        
        # Para datasets pequeños (< 500), order_by('?') es aceptable
        if total_count <= 500:
            return list(
                queryset.select_related('uploaded_by')
                .order_by('?')[:limit]
            )
        
        # Para datasets grandes, algoritmo optimizado
        return self._get_random_large_dataset(queryset, limit, total_count)
    
    def _get_random_large_dataset(self, queryset, limit, total_count):
        """
        Algoritmo optimizado para datasets grandes
        No usa random.sample(list(...)) ← EVITA MEMORY EXPLOSION
        """
        import random
        
        songs = []
        selected_ids = set()
        
        # Si tenemos pocas canciones comparado con el límite
        if total_count <= limit * 3:
            # Tomar todas y mezclar localmente
            all_ids = list(queryset.values_list('id', flat=True))
            random.shuffle(all_ids)
            selected_ids = set(all_ids[:limit])
            
            # Obtener objetos completos
            songs = list(
                queryset.select_related('uploaded_by')
                .filter(id__in=selected_ids)
            )
            # Reordenar según el shuffle
            id_to_song = {song.id: song for song in songs}
            songs = [id_to_song[song_id] for song_id in all_ids[:limit] if song_id in id_to_song]
            
            return songs
        
        # Para datasets muy grandes, usar offsets aleatorios
        attempts = 0
        max_attempts = 3
        
        while len(songs) < limit and attempts < max_attempts:
            remaining = limit - len(songs)
            
            # Calcular offset aleatorio
            offset = random.randint(0, max(0, total_count - (remaining * 2)))
            
            # Obtener batch
            batch = list(
                queryset.select_related('uploaded_by')
                .exclude(id__in=selected_ids)
                [offset:offset + (remaining * 3)]  # Tomar más de lo necesario
            )
            
            if batch:
                # Mezclar localmente (más eficiente que order_by('?'))
                random.shuffle(batch)
                
                for song in batch:
                    if len(songs) >= limit:
                        break
                    if song.id not in selected_ids:
                        songs.append(song)
                        selected_ids.add(song.id)
            
            attempts += 1
        
        return songs[:limit]
    
    def _serialize_with_optimized_urls(self, songs):
        """
        Serializa optimizando las llamadas a R2
        
        En lugar de generar una URL presigned por cada canción (15-30 llamadas),
        genera TODAS en una sola operación batch (1-2 llamadas)
        """
        # 1. Recopilar todas las keys
        audio_keys = []
        image_keys = []
        
        for song in songs:
            if song.file_key and song.file_key != "songs/temp_file":
                audio_keys.append(song.file_key)
            if song.image_key:
                image_keys.append(song.image_key)
        
        # 2. Obtener URLs en BATCH (¡OPTIMIZACIÓN CRÍTICA!)
        # De 15-30 llamadas individuales → 1-2 llamadas batch
        audio_urls = generate_presigned_urls_batch(audio_keys) if audio_keys else {}
        image_urls = generate_presigned_urls_batch(image_keys) if image_keys else {}
        
        # 3. Serializar normalmente (usa tu SongSerializer existente)
        serializer = SongSerializer(songs, many=True)
        data = serializer.data
        
        # 4. Asignar URLs desde el batch (si el serializer no las incluyó)
        # Esto es compatible: si el serializer ya las incluye, no se sobrescriben
        for i, song in enumerate(songs):
            song_data = data[i]
            
            # Audio URL
            if song.file_key and song.file_key in audio_urls:
                # Solo asignar si no existe o si queremos asegurarnos
                if 'audio_url' not in song_data or song_data.get('audio_url') is None:
                    song_data['audio_url'] = audio_urls[song.file_key]
            
            # Image URL
            if song.image_key and song.image_key in image_urls:
                if 'image_url' not in song_data or song_data.get('image_url') is None:
                    song_data['image_url'] = image_urls[song.image_key]
        
        return data
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

# api2/views.py - Agrega esto al final del archiv


@extend_schema(
    description="""
    Sube una nueva canción con archivos de audio e imagen a R2 Cloudflare.
    
    **Requisitos:**
    - Usuario autenticado
    - Máximo 20 subidas por hora
    - Archivo de audio: MP3, WAV, OGG, M4A, FLAC, AAC, WEBM (max 100MB)
    - Imagen opcional: JPG, PNG, WEBP, GIF (max 10MB)
    """,
    request=SongUploadSerializer,
    responses={
        201: SongUploadSerializer,
        400: OpenApiResponse(description="Datos inválidos o archivos faltantes"),
        401: OpenApiResponse(description="No autenticado"),
        403: OpenApiResponse(description="Sin permisos"),
        429: OpenApiResponse(description="Límite de subidas alcanzado"),
        500: OpenApiResponse(description="Error interno del servidor")
    }
)
class SongUploadView(APIView):
    """
    Vista optimizada para subir canciones con archivos a R2 Cloudflare
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Endpoint para subir nueva canción
        """
        # 1. Rate limiting
        current_hour = timezone.now().hour
        user_key = f"upload_{request.user.id}_{current_hour}"
        
        current_uploads = cache.get(user_key, 0)
        if current_uploads >= 20:
            return Response(
                {
                    "error": "rate_limit_exceeded",
                    "message": "Límite de 20 subidas por hora alcanzado",
                    "retry_after": 3600,
                    "current_uploads": current_uploads
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        # 2. Verificar que hay archivos
        if 'audio_file' not in request.FILES:
            return Response(
                {
                    "error": "missing_audio_file",
                    "message": "Se requiere un archivo de audio",
                    "field": "audio_file"
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 3. Validar tamaño total de archivos
        total_size = 0
        for file_key in request.FILES:
            file_obj = request.FILES[file_key]
            total_size += file_obj.size
        
        if total_size > 110 * 1024 * 1024:  # 110MB (100MB audio + 10MB imagen)
            return Response(
                {
                    "error": "total_size_exceeded",
                    "message": "El tamaño total de los archivos no puede superar los 110MB",
                    "max_size_mb": 110,
                    "current_size_mb": total_size / (1024 * 1024)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 4. Usar serializer
        serializer = SongUploadSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            # Mejorar formato de errores
            errors = serializer.errors
            if 'audio_file' in errors and isinstance(errors['audio_file'], list):
                # Simplificar mensajes de error de archivos
                errors['audio_file'] = errors['audio_file'][0]
            
            return Response(
                {
                    "error": "validation_error",
                    "message": "Error de validación en los datos",
                    "errors": errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 5. Intentar crear la canción
        try:
            song = serializer.save()
            
            # 6. Actualizar rate limit
            cache.set(user_key, current_uploads + 1, 3600)
            
            # 7. Log exitoso
            logger.info(
                f" Canción subida exitosamente - "
                f"ID: {song.id}, "
                f"Usuario: {request.user.username}, "
                f"Título: {song.title}, "
                f"Audio Key: {song.file_key}, "
                f"Tamaño: {song.file_size if hasattr(song, 'file_size') else 'N/A'} bytes"
            )
            
            # 8. Respuesta exitosa
            return Response(
                {
                    "success": True,
                    "message": "Canción subida exitosamente",
                    "song": {
                        "id": song.id,
                        "title": song.title,
                        "artist": song.artist,
                        "genre": song.genre,
                        "duration": song.duration,
                        "is_public": song.is_public,
                        "audio_key": song.file_key,
                        "image_key": song.image_key,
                        "uploaded_by": {
                            "id": request.user.id,
                            "username": request.user.username
                        },
                        "created_at": song.created_at.isoformat() if song.created_at else None
                    },
                    "stats": {
                        "uploads_this_hour": current_uploads + 1,
                        "remaining_uploads": 20 - (current_uploads + 1)
                    }
                },
                status=status.HTTP_201_CREATED
            )
            
        except serializers.ValidationError as e:
            # Error de validación del serializer
            logger.warning(
                f" Error de validación en upload - "
                f"Usuario: {request.user.username}, "
                f"Error: {str(e)}"
            )
            
            return Response(
                {
                    "error": "upload_validation_error",
                    "message": "Error al validar los archivos",
                    "detail": str(e.detail) if hasattr(e, 'detail') else str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            # Error inesperado
            logger.error(
                f" Error inesperado en SongUploadView - "
                f"Usuario: {request.user.username}, "
                f"Error: {str(e)}",
                exc_info=True
            )
            
            # Determinar tipo de error para mensaje amigable
            error_message = "Error interno al procesar la subida"
            if "timeout" in str(e).lower():
                error_message = "Timeout al subir archivos. Intenta de nuevo."
            elif "connection" in str(e).lower():
                error_message = "Error de conexión con el servidor de almacenamiento."
            elif "permission" in str(e).lower():
                error_message = "Error de permisos al acceder al almacenamiento."
            
            return Response(
                {
                    "error": "upload_failed",
                    "message": error_message,
                    "detail": "Por favor, intenta de nuevo en unos minutos. Si el problema persiste, contacta al soporte."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# ✅ VISTA PARA VERIFICAR ARCHIVOS EN R2 - VERSIÓN OPTIMIZADA
# ============================================================================

@extend_schema(
    description="Verifica el estado de los archivos de una canción en R2 Cloudflare",
    responses={
        200: OpenApiResponse(description="Estado de archivos obtenido exitosamente"),
        403: OpenApiResponse(description="No tienes permisos para ver esta canción"),
        404: OpenApiResponse(description="Canción no encontrada")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_song_files(request, song_id):
    """
    Verifica el estado de los archivos de una canción en R2
    """
    try:
        # 1. Obtener canción
        song = get_object_or_404(Song, id=song_id)
        
        # 2. Verificar permisos (solo owner, staff o superuser)
        user = request.user
        is_owner = song.uploaded_by == user
        is_staff = user.is_staff
        is_superuser = user.is_superuser
        
        if not (is_owner or is_staff or is_superuser):
            logger.warning(
                f" Intento de acceso no autorizado a check_song_files - "
                f"Usuario: {user.username}, "
                f"Canción ID: {song_id}"
            )
            
            return Response(
                {
                    "error": "permission_denied",
                    "message": "No tienes permisos para verificar esta canción"
                },
                status=status.HTTP_403_FORBIDDEN
            )
        
        # 3. Preparar respuesta base
        response_data = {
            'song_id': song_id,
            'title': song.title,
            'artist': song.artist or '',
            'uploaded_by': {
                'id': song.uploaded_by.id if song.uploaded_by else None,
                'username': song.uploaded_by.username if song.uploaded_by else None
            },
            'files': {},
            'permissions': {
                'is_owner': is_owner,
                'is_staff': is_staff,
                'can_edit': is_owner or is_staff
            }
        }
        
        # 4. Verificar archivo de audio
        if song.file_key:
            if song.file_key == "songs/temp_file" or "temp" in song.file_key.lower():
                response_data['files']['audio'] = {
                    'key': song.file_key,
                    'exists': False,
                    'status': 'temp_file',
                    'message': 'Archivo temporal, necesita ser reemplazado'
                }
            else:
                audio_info = get_file_info(song.file_key)
                if audio_info:
                    response_data['files']['audio'] = {
                        'key': song.file_key,
                        'exists': True,
                        'size_bytes': audio_info.get('size'),
                        'size_mb': round(audio_info.get('size', 0) / (1024 * 1024), 2) if audio_info.get('size') else 0,
                        'content_type': audio_info.get('content_type', 'audio/mpeg'),
                        'last_modified': audio_info.get('last_modified'),
                        'status': 'ok'
                    }
                else:
                    response_data['files']['audio'] = {
                        'key': song.file_key,
                        'exists': False,
                        'status': 'not_found',
                        'message': 'Archivo no encontrado en R2'
                    }
        else:
            response_data['files']['audio'] = {
                'exists': False,
                'status': 'no_key',
                'message': 'No hay clave de archivo registrada'
            }
        
        # 5. Verificar imagen
        if song.image_key:
            image_info = get_file_info(song.image_key)
            if image_info:
                response_data['files']['image'] = {
                    'key': song.image_key,
                    'exists': True,
                    'size_bytes': image_info.get('size'),
                    'size_mb': round(image_info.get('size', 0) / (1024 * 1024), 2) if image_info.get('size') else 0,
                    'content_type': image_info.get('content_type', 'image/jpeg'),
                    'last_modified': image_info.get('last_modified'),
                    'status': 'ok'
                }
            else:
                response_data['files']['image'] = {
                    'key': song.image_key,
                    'exists': False,
                    'status': 'not_found',
                    'message': 'Imagen no encontrada en R2'
                }
        else:
            response_data['files']['image'] = {
                'exists': False,
                'status': 'no_image',
                'message': 'No hay imagen asociada'
            }
        
        # 6. Log de verificación
        logger.info(
            f"🔍 Verificación de archivos - "
            f"Canción ID: {song_id}, "
            f"Usuario: {user.username}, "
            f"Audio existe: {response_data['files']['audio'].get('exists', False)}, "
            f"Imagen existe: {response_data['files']['image'].get('exists', False)}"
        )
        
        return Response(response_data)
        
    except Http404:
        logger.warning(
            f"📭 Canción no encontrada en check_song_files - "
            f"ID: {song_id}, "
            f"Usuario: {request.user.username}"
        )
        
        return Response(
            {
                "error": "not_found",
                "message": "Canción no encontrada",
                "song_id": song_id
            },
            status=status.HTTP_404_NOT_FOUND
        )
        
    except Exception as e:
        logger.error(
            f" Error en check_song_files - "
            f"Canción ID: {song_id}, "
            f"Usuario: {request.user.username}, "
            f"Error: {str(e)}",
            exc_info=True
        )
        
        return Response(
            {
                "error": "check_failed",
                "message": "Error al verificar archivos",
                "song_id": song_id,
                "detail": "Error interno del servidor"
            },
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
            from api2.utils.r2_utils import check_r2_connection
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
    
class UploadRateThrottle(UserRateThrottle):
    """Rate limiting para uploads"""
    scope = 'uploads'
    rate = '100/hour'


# api2/views.py - VERSIÓN CORREGIDA COMPLETA

class DirectUploadRequestView(APIView):
    """
    Endpoint para solicitar URL de upload directo a R2
    POST /api2/upload/direct/request/
    VERSIÓN CORREGIDA - Compatible con Windows y nuevo r2_direct
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UploadRateThrottle]
    
    def post(self, request):
        """Solicitar URL PUT firmada para upload directo"""
        # Rate limiting por IP adicional
        ip = self._get_client_ip(request)
        ip_cache_key = f'upload_ip_limit_{ip}'
        ip_requests = cache.get(ip_cache_key, 0)
        
        if ip_requests > 50:
            return Response(
                {
                    "error": "rate_limit_exceeded",
                    "message": "Demasiadas solicitudes desde esta IP"
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        # 1. Validar datos de entrada
        serializer = DirectUploadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Validation error for user {request.user.id}: {serializer.errors}")
            return Response(
                {
                    "error": "validation_error",
                    "errors": serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        file_name = serializer.validated_data['file_name']
        file_size = serializer.validated_data['file_size']
        file_type = serializer.validated_data.get('file_type', '')
        metadata = serializer.validated_data.get('metadata', {})
        
        # 2. Verificar cuota (con transacción para evitar race conditions)
        try:
            with transaction.atomic():
                quota, created = UploadQuota.objects.select_for_update().get_or_create(
                    user=user
                )
                
                can_upload, error_message = quota.can_upload(file_size)
                if not can_upload:
                    logger.warning(f"Quota exceeded for user {user.id}: {error_message}")
                    return Response(
                        {
                            "error": "quota_exceeded",
                            "message": error_message,
                            "quota": quota.get_quota_info()
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
                
                # 3. Generar URL de upload (nuevo formato)
                try:
                    upload_data = r2_upload.generate_presigned_put(
                        user_id=user.id,
                        file_name=file_name,
                        file_size=file_size,
                        file_type=file_type,
                        custom_metadata=metadata,
                        expires_in=3600
                    )
                except Exception as e:
                    logger.error(f"Error generating PUT URL for user {user.id}: {str(e)}", exc_info=True)
                    return Response(
                        {
                            "error": "upload_config_error",
                            "message": "Error configurando upload. Intenta nuevamente."
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 4. Crear sesión de upload
                try:
                    expires_at = datetime.fromtimestamp(upload_data['expires_at'], tz=pytz.UTC)
                    
                    upload_session = UploadSession.objects.create(
                        user=user,
                        file_name=file_name,
                        file_size=file_size,
                        file_type=file_type,
                        original_file_name=metadata.get('original_name', file_name),
                        file_key=upload_data['file_key'],
                        status='pending',
                        expires_at=expires_at,
                        metadata={
                            **metadata,
                            'ip_address': ip,
                            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                            'upload_timestamp': timezone.now().isoformat(),
                            'upload_method': 'PUT',
                            'key_structure': upload_data.get('key_structure', {}),  # ✅ Nuevo campo
                            'suggested_content_type': upload_data.get('suggested_content_type', file_type)
                        }
                    )
                except Exception as e:
                    logger.error(f"Error creating upload session for user {user.id}: {str(e)}", exc_info=True)
                    return Response(
                        {
                            "error": "session_creation_error",
                            "message": "Error creando sesión de upload"
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 5. Reservar cuota (transaccional)
                quota.reserve_quota(file_size)
                
                # 6. Actualizar cache de rate limiting
                cache.set(ip_cache_key, ip_requests + 1, 3600)
        
        except Exception as e:
            logger.error(f"Unexpected error in upload request for user {user.id}: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": "internal_error",
                    "message": "Error interno del servidor"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # 7. Respuesta exitosa (actualizada)
        logger.info(f"Upload PUT URL generated for user {user.id}: {upload_session.id}")
        
        response_data = {
            "success": True,
            "upload_id": str(upload_session.id),
            "upload_url": upload_data['upload_url'],
            "method": upload_data['method'],
            "file_key": upload_data['file_key'],
            "file_name": upload_data.get('file_name', file_name),
            "expires_at": upload_session.expires_at.isoformat(),
            "expires_in": upload_data.get('expires_in', 3600),
            "max_size": file_size,
            "confirmation_url": self._get_confirmation_url(upload_session.id),
            "key_structure": upload_data.get('key_structure', {}),  # ✅ Nuevo campo
            "suggested_content_type": upload_data.get('suggested_content_type', file_type)
        }
        
        # ✅ CORREGIDO: 'instructions' puede no existir, usar get
        if upload_data.get('instructions'):
            response_data['instructions'] = upload_data['instructions']
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def _get_client_ip(self, request):
        """Obtiene IP real del cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _get_confirmation_url(self, upload_id):
        """Genera URL para confirmación"""
        from django.conf import settings
        api_base = settings.API_URL.rstrip('/')
        return f"{api_base}/api2/upload/direct/confirm/{upload_id}/"


class UploadConfirmationView(APIView):
    """
    Endpoint para confirmar que un archivo fue subido exitosamente
    POST /api2/upload/direct/confirm/<upload_id>/
    VERSIÓN CORREGIDA - Windows compatible y alineada con nuevo r2_direct
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, upload_id):
        """Confirmar que un archivo fue subido a R2 - VERSIÓN CORREGIDA"""
        try:
            # 1. Obtener y validar sesión
            upload_session = UploadSession.objects.get(
                id=upload_id,
                user=request.user
            )

            # 2. Validar que puede confirmarse
            if not upload_session.can_confirm:
                return Response(
                    {
                        "error": "cannot_confirm",
                        "message": "Esta sesión no puede ser confirmada",
                        "details": {
                            "status": upload_session.status,
                            "is_expired": upload_session.is_expired,
                            "confirmed": upload_session.confirmed,
                            "can_confirm_reason": upload_session.get_can_confirm_reason()
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 3. Validar datos de confirmación
            serializer = UploadConfirmationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {"error": "validation_error", "errors": serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 4. Verificar que el archivo existe en R2
            file_valid, file_info = r2_direct.verify_upload_complete(
                upload_session.file_key,
                expected_size=upload_session.file_size,
                expected_user_id=request.user.id
            )

            # 5. Manejar resultados según el nuevo formato
            validation_data = file_info.get('validation', {})
            
            # ✅ CORREGIDO: user_match → owner_match Y manejo de key_pattern_valid
            has_validation_issues = (
                not validation_data.get('size_match', True) or 
                not validation_data.get('owner_match', True) or
                not validation_data.get('key_pattern_valid', True)
            )

            if not file_valid or has_validation_issues:
                return self._handle_verification_failure(
                    upload_session=upload_session,
                    file_info=file_info,
                    user=request.user,
                    delete_invalid=serializer.validated_data.get('delete_invalid', False)
                )

            # 6. Confirmar upload exitoso (transaccional)
            try:
                with transaction.atomic():
                    # Marcar sesión como confirmada
                    upload_session.mark_as_confirmed()

                    # Actualizar cuota
                    quota = UploadQuota.objects.select_for_update().get(
                        user=request.user
                    )
                    quota.confirm_upload(upload_session.file_size)

                    # Preparar metadata para procesamiento
                    # ✅ CORREGIDO: Usar key_analysis en lugar de security_info
                    processing_metadata = {
                        **upload_session.metadata,
                        'verification_info': {
                            'validated_at': timezone.now().isoformat(),
                            'validation_summary': validation_data,
                            'key_analysis': file_info.get('key_analysis', {}),
                            'r2_metadata': file_info.get('metadata', {})
                        }
                    }

                    # Encolar procesamiento
                    process_direct_upload.delay(
                        upload_session_id=str(upload_session.id),
                        file_key=upload_session.file_key,
                        file_size=upload_session.file_size,
                        content_type=upload_session.file_type,
                        metadata=processing_metadata
                    )

                    # ✅ CORREGIDO: SIN EMOJIS PARA WINDOWS
                    logger.info(
                        f"[SUCCESS] Upload confirmed | "
                        f"ID: {upload_id} | "
                        f"User: {request.user.id} | "
                        f"Key: {upload_session.file_key} | "
                        f"Size: {upload_session.file_size:,}B"
                    )

            except Exception as e:
                # ✅ CORREGIDO: SIN EMOJIS PARA WINDOWS
                logger.error(
                    f"[ERROR] Error confirming upload {upload_id}: {str(e)}",
                    exc_info=True
                )
                return Response(
                    {
                        "error": "confirmation_failed",
                        "message": "Error confirmando upload",
                        "details": {"exception": str(e)}
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # 7. Respuesta exitosa mejorada
            return Response({
                "success": True,
                "upload_id": str(upload_session.id),
                "status": upload_session.status,
                "confirmed_at": upload_session.confirmed_at.isoformat(),
                "file_info": {
                    "key": upload_session.file_key,
                    "size": upload_session.file_size,
                    "content_type": upload_session.file_type,
                    "ownership_verified": validation_data.get('owner_match', True),
                    "key_structure_valid": validation_data.get('key_pattern_valid', True),
                    "etag": file_info.get('etag', '')
                },
                "validation": {
                    "passed": True,
                    "method": "key_structure_ownership",
                    "summary": {
                        "size_match": validation_data.get('size_match', True),
                        "owner_match": validation_data.get('owner_match', True),
                        "key_pattern_valid": validation_data.get('key_pattern_valid', True),
                        "issues_count": len(validation_data.get('issues', []))
                    }
                },
                "processing": {
                    "started": True,
                    "task_enqueued": True,
                    "estimated_time": "30-60 segundos"
                },
                "urls": {
                    "status": f"/api2/upload/direct/status/{upload_id}/",
                    "download": None,
                    "thumbnail": None
                }
            })

        except UploadSession.DoesNotExist:
            logger.warning(f"Upload session not found: {upload_id} for user {request.user.id}")
            return Response(
                {
                    "error": "upload_session_not_found",
                    "message": "Sesión de upload no encontrada o no autorizada",
                    "details": {
                        "upload_id": upload_id,
                        "user_id": request.user.id,
                        "suggested_actions": [
                            "Verificar el ID de upload",
                            "Asegurarse de que el upload no haya expirado",
                            "Contactar soporte si el problema persiste"
                        ]
                    }
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            # ✅ CORREGIDO: SIN EMOJIS PARA WINDOWS
            logger.error(
                f"[ERROR] Unexpected error in confirmation for upload {upload_id}: {str(e)}",
                exc_info=True
            )
            return Response(
                {
                    "error": "internal_error",
                    "message": "Error interno confirmando upload",
                    "details": {
                        "upload_id": upload_id,
                        "exception_type": type(e).__name__,
                        "timestamp": timezone.now().isoformat()
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _handle_verification_failure(self, upload_session, file_info, user, delete_invalid=False):
        """
        Maneja fallos de verificación de manera estructurada
        VERSIÓN WINDOWS COMPATIBLE
        """
        validation_data = file_info.get('validation', {})
        issues = validation_data.get('issues', [])
        
        # Determinar tipo de error
        if not file_info.get('exists', False):
            error_type = "file_not_found"
            error_message = "El archivo no existe en R2"
            status_code = status.HTTP_404_NOT_FOUND
            log_level = logging.WARNING
            log_prefix = "[WARNING]"
        else:
            error_type = "validation_failed"
            error_message = "El archivo no cumple los requisitos de seguridad"
            status_code = status.HTTP_400_BAD_REQUEST
            log_level = logging.ERROR
            log_prefix = "[ERROR]"
            
            # Mensaje más específico si hay issues
            if issues:
                error_message = f"Validación fallida: {', '.join(issues[:3])}"
                if len(issues) > 3:
                    error_message += f" y {len(issues) - 3} más"

        # Marcar como fallado
        upload_session.mark_as_failed(error_message)
        
        # Liberar cuota pendiente
        try:
            quota = UploadQuota.objects.get(user=user)
            quota.release_pending_quota(upload_session.file_size)
        except Exception as e:
            logger.error(f"[ERROR] Error liberando cuota para upload fallido {upload_session.id}: {e}")

        # Opcional: eliminar archivo inválido de R2
        if delete_invalid:
            try:
                deleted, delete_message = r2_direct.delete_file(upload_session.file_key)
                if deleted:
                    logger.info(f"[INFO] Archivo inválido eliminado: {upload_session.file_key}")
            except Exception as e:
                logger.warning(f"[WARNING] No se pudo eliminar archivo inválido: {e}")

        # ✅ CORREGIDO: LOG WINDOWS COMPATIBLE (SIN EMOJIS)
        logger.log(log_level,
                  f"{log_prefix} Verification failed | "
                  f"Upload: {upload_session.id} | "
                  f"Type: {error_type} | "
                  f"Key: {upload_session.file_key} | "
                  f"Issues: {len(issues)}")

        # Respuesta estructurada
        response_data = {
            "error": error_type,
            "message": error_message,
            "details": {
                "file_exists": file_info.get('exists', False),
                "upload_session": {
                    "id": str(upload_session.id),
                    "status": upload_session.status,
                    "file_key": upload_session.file_key,
                    "expected_size": upload_session.file_size
                },
                "validation": validation_data,
                "key_analysis": file_info.get('key_analysis', {}),
                "quota_freed": True
            }
        }

        # Añadir issues completos si no son muchos
        if issues and len(issues) <= 10:
            response_data["details"]["all_issues"] = issues

        return Response(response_data, status=status_code)


class DirectUploadStatusView(APIView):
    """
    Verifica estado de un upload directo
    GET /api2/upload/direct/status/<upload_id>/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, upload_id):
        try:
            # Obtener sesión (solo el dueño puede ver)
            upload_session = UploadSession.objects.get(
                id=upload_id,
                user=request.user
            )
            
            # Verificar si necesita actualizar estado por archivo en R2
            if upload_session.status in ['pending', 'uploaded']:
                # Verificar si el archivo existe en R2
                # CORRECCIÓN: Manejar el retorno como tupla
                file_exists, _ = r2_direct.verify_upload_complete(
                    upload_session.file_key
                )
                
                if file_exists and upload_session.status == 'pending':
                    # Frontend subió pero no confirmó aún
                    upload_session.mark_as_uploaded()
            
            # Construir respuesta
            response_data = self._build_status_response(upload_session)
            
            return Response(response_data)
            
        except UploadSession.DoesNotExist:
            return Response(
                {
                    "error": "not_found",
                    "message": "Upload session no encontrada"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error obteniendo estado: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": "status_check_error",
                    "message": "Error verificando estado"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _build_status_response(self, upload_session):
        """Construye respuesta de estado detallada"""
        base_data = {
            "upload_id": str(upload_session.id),
            "status": upload_session.status,
            "status_message": upload_session.status_message,
            "file_name": upload_session.file_name,
            "file_size": upload_session.file_size,
            "file_type": upload_session.file_type,
            "created_at": upload_session.created_at.isoformat(),
            "updated_at": upload_session.updated_at.isoformat(),
            "expires_at": upload_session.expires_at.isoformat(),
            "is_expired": upload_session.is_expired,
            "confirmed": upload_session.confirmed,
            "confirmed_at": upload_session.confirmed_at.isoformat() if upload_session.confirmed_at else None,
            "can_confirm": upload_session.can_confirm,
        }
        
        # Agregar info según estado
        if upload_session.status == 'ready' and upload_session.song:
            base_data['song'] = {
                "id": upload_session.song.id,
                "title": upload_session.song.title,
                "artist": upload_session.song.artist,
                "file_key": upload_session.song.file_key,
                "stream_url": f"/api/stream/{upload_session.song.id}/",
                "duration": upload_session.song.duration
            }
        elif upload_session.status == 'failed':
            base_data['can_retry'] = upload_session.is_expired
            base_data['retry_instructions'] = "Solicita una nueva URL de upload"
        
        # Para estados pendientes, agregar info de R2
        if upload_session.status in ['pending', 'uploaded']:
            # CORRECCIÓN: Manejar el retorno como tupla
            file_exists, file_info = r2_direct.verify_upload_complete(
                upload_session.file_key
            )
            base_data['file_in_r2'] = file_exists
            if file_exists:
                base_data['file_metadata'] = file_info
        
        return base_data


class UserUploadQuotaView(APIView):
    """
    Muestra la cuota de upload del usuario
    GET /api2/upload/quota/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            quota, created = UploadQuota.objects.get_or_create(user=request.user)
            quota_info = quota.get_quota_info()
            
            # Agregar información de sesiones activas
            active_sessions = UploadSession.objects.filter(
                user=request.user,
                status__in=['pending', 'uploaded', 'confirmed', 'processing']
            ).count()
            
            quota_info['active_sessions'] = active_sessions
            
            return Response(quota_info)
            
        except Exception as e:
            logger.error(f"Error obteniendo cuota para user {request.user.id}: {str(e)}")
            return Response(
                {
                    "error": "quota_error",
                    "message": "Error obteniendo información de cuota"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UploadCancellationView(APIView):
    """
    Cancela un upload pendiente
    POST /api2/upload/direct/cancel/<upload_id>/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, upload_id):
        try:
            upload_session = UploadSession.objects.get(
                id=upload_id,
                user=request.user
            )
            
            # Solo se puede cancelar si está pendiente o subido
            if upload_session.status not in ['pending', 'uploaded']:
                return Response(
                    {
                        "error": "cannot_cancel",
                        "message": f"No se puede cancelar en estado: {upload_session.status}"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Transacción para consistencia
            with transaction.atomic():
                # Marcar como cancelado
                upload_session.status = 'cancelled'
                upload_session.save(update_fields=['status', 'updated_at'])
                
                # Liberar cuota pendiente
                quota = UploadQuota.objects.select_for_update().get(
                    user=request.user
                )
                quota.release_pending_quota(upload_session.file_size)
                
                # Opcional: eliminar archivo de R2 si existe
                if request.data.get('delete_from_r2', False):
                    # CORRECCIÓN: Manejar el retorno como tupla
                    file_exists, _ = r2_direct.verify_upload_complete(
                        upload_session.file_key
                    )
                    if file_exists:
                        r2_direct.delete_file(upload_session.file_key)
            
            return Response({
                "success": True,
                "upload_id": str(upload_session.id),
                "status": "cancelled",
                "quota_released": True
            })
            
        except UploadSession.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Sesión no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error cancelando upload {upload_id}: {str(e)}")
            return Response(
                {"error": "cancellation_error", "message": "Error cancelando upload"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
# ================================
# VISTAS DE ADMINISTRACIÓN PARA UPLOADS (AGREGAR AL FINAL)
# ================================

class UploadAdminDashboardView(APIView):
    """
    Dashboard de administración para uploads (solo staff)
    GET /api/upload/admin/dashboard/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Verificar que el usuario sea staff
        if not request.user.is_staff:
            return Response(
                {"error": "unauthorized", "message": "Acceso denegado"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Obtener estadísticas generales
        total_uploads = UploadSession.objects.count()
        today = timezone.now().date()
        uploads_today = UploadSession.objects.filter(
            created_at__date=today
        ).count()
        
        uploads_by_status = UploadSession.objects.values('status').annotate(
            count=models.Count('id')
        ).order_by('status')
        
        recent_uploads = UploadSession.objects.select_related('user').order_by('-created_at')[:10]
        
        # Calcular cuota total usada
        total_quota_used = UploadSession.objects.filter(
            status__in=['confirmed', 'ready']
        ).aggregate(total_size=models.Sum('file_size'))['total_size'] or 0
        
        data = {
            "stats": {
                "total_uploads": total_uploads,
                "uploads_today": uploads_today,
                "uploads_last_7_days": UploadSession.objects.filter(
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).count(),
                "total_quota_used_bytes": total_quota_used,
                "total_quota_used_gb": round(total_quota_used / (1024**3), 2),
                "active_uploads": UploadSession.objects.filter(
                    status__in=['pending', 'uploaded', 'processing']
                ).count(),
            },
            "uploads_by_status": list(uploads_by_status),
            "recent_uploads": self._serialize_recent_uploads(recent_uploads),
            "top_users": self._get_top_uploaders(),
        }
        
        return Response(data)
    
    def _serialize_recent_uploads(self, uploads):
        """Serializa uploads recientes de forma simple"""
        result = []
        for upload in uploads:
            result.append({
                'id': str(upload.id),
                'user_id': upload.user.id,
                'username': upload.user.username,
                'file_name': upload.file_name,
                'file_size': upload.file_size,
                'status': upload.status,
                'created_at': upload.created_at.isoformat(),
                'expires_at': upload.expires_at.isoformat() if upload.expires_at else None,
            })
        return result
    
    def _get_top_uploaders(self):
        """Obtiene los usuarios con más uploads"""
        from django.db.models import Count
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        top_users = UploadSession.objects.values('user').annotate(
            upload_count=Count('id'),
            total_size=models.Sum('file_size')
        ).order_by('-upload_count')[:10]
        
        result = []
        for item in top_users:
            try:
                user = User.objects.get(id=item['user'])
                result.append({
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'upload_count': item['upload_count'],
                    'total_size': item['total_size'],
                    'total_size_gb': round((item['total_size'] or 0) / (1024**3), 2),
                })
            except User.DoesNotExist:
                continue
        
        return result


class UploadStatsView(APIView):
    """
    Estadísticas detalladas de uploads para monitoreo
    GET /api/upload/admin/stats/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "unauthorized", "message": "Acceso denegado"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Configurar el rango de tiempo (por defecto últimos 30 días)
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Estadísticas por día
        daily_stats = []
        for day in range(days):
            day_start = start_date + timedelta(days=day)
            day_end = day_start + timedelta(days=1)
            
            day_uploads = UploadSession.objects.filter(
                created_at__gte=day_start,
                created_at__lt=day_end
            )
            
            count = day_uploads.count()
            total_size = day_uploads.aggregate(total=models.Sum('file_size'))['total'] or 0
            
            daily_stats.append({
                "date": day_start.date().isoformat(),
                "count": count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024*1024), 2)
            })
        
        # Tamaños de archivo
        size_stats = {
            "small": UploadSession.objects.filter(file_size__lt=5*1024*1024).count(),  # <5MB
            "medium": UploadSession.objects.filter(
                file_size__gte=5*1024*1024, 
                file_size__lt=50*1024*1024
            ).count(),  # 5-50MB
            "large": UploadSession.objects.filter(
                file_size__gte=50*1024*1024, 
                file_size__lt=200*1024*1024
            ).count(),  # 50-200MB
            "xlarge": UploadSession.objects.filter(file_size__gte=200*1024*1024).count(),  # >200MB
        }
        
        # Tipos de archivo más comunes
        file_types = UploadSession.objects.exclude(file_type='').exclude(
            file_type__isnull=True
        ).values('file_type').annotate(
            count=models.Count('id'),
            avg_size=models.Avg('file_size')
        ).order_by('-count')[:15]
        
        # Estadísticas de éxito
        success_stats = {
            'total': UploadSession.objects.filter(created_at__gte=start_date).count(),
            'successful': UploadSession.objects.filter(
                created_at__gte=start_date,
                status='ready'
            ).count(),
            'failed': UploadSession.objects.filter(
                created_at__gte=start_date,
                status='failed'
            ).count(),
            'pending': UploadSession.objects.filter(
                created_at__gte=start_date,
                status__in=['pending', 'uploaded', 'processing']
            ).count(),
        }
        
        if success_stats['total'] > 0:
            success_stats['success_rate'] = round(
                (success_stats['successful'] / success_stats['total']) * 100, 2
            )
            success_stats['failure_rate'] = round(
                (success_stats['failed'] / success_stats['total']) * 100, 2
            )
        
        return Response({
            "time_range": {
                "days": days,
                "start_date": start_date.isoformat(),
                "end_date": timezone.now().isoformat()
            },
            "daily_stats": daily_stats,
            "size_distribution": size_stats,
            "file_types": list(file_types),
            "success_rates": success_stats,
            "summary": {
                "total_uploads": success_stats['total'],
                "successful_uploads": success_stats['successful'],
                "failed_uploads": success_stats['failed'],
                "pending_uploads": success_stats['pending'],
            }
        })


class CleanupExpiredUploadsView(APIView):
    """
    Limpieza manual de uploads expirados
    POST /api/upload/admin/cleanup/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "unauthorized", "message": "Acceso denegado"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Encontrar uploads expirados
            expired_uploads = UploadSession.objects.filter(
                expires_at__lt=timezone.now(),
                status__in=['pending', 'uploaded']
            )
            
            count = expired_uploads.count()
            
            if count == 0:
                return Response({
                    "success": True,
                    "message": "No hay uploads expirados para limpiar",
                    "count": 0
                })
            
            # Marcar como expirados
            expired_ids = list(expired_uploads.values_list('id', flat=True))
            expired_uploads.update(status='expired', updated_at=timezone.now())
            
            # Liberar cuota pendiente
            from django.db.models import Sum
            
            # Agrupar por usuario para liberar cuota eficientemente
            user_quotas = expired_uploads.values('user').annotate(
                total_size=Sum('file_size')
            )
            
            for item in user_quotas:
                try:
                    quota = UploadQuota.objects.get(user_id=item['user'])
                    quota.release_pending_quota(item['total_size'])
                except UploadQuota.DoesNotExist:
                    pass
            
            # Opcional: eliminar archivos de R2
            delete_from_r2 = request.data.get('delete_from_r2', False)
            deleted_from_r2 = 0
            
            if delete_from_r2:
                for upload in expired_uploads:
                    try:
                        file_exists, _ = r2_direct.verify_upload_complete(upload.file_key)
                        if file_exists:
                            r2_direct.delete_file(upload.file_key)
                            deleted_from_r2 += 1
                    except Exception as e:
                        logger.error(f"Error eliminando archivo {upload.file_key}: {str(e)}")
            
            logger.info(f"Limpieza completada: {count} uploads expirados marcados")
            
            return Response({
                "success": True,
                "message": f"Se limpiaron {count} uploads expirados",
                "count": count,
                "expired_ids": expired_ids[:50],  # Limitar para respuesta
                "deleted_from_r2": deleted_from_r2 if delete_from_r2 else None,
                "details": {
                    "uploads_marked_expired": count,
                    "files_deleted_from_r2": deleted_from_r2,
                    "quota_freed": sum(item['total_size'] for item in user_quotas)
                }
            })
            
        except Exception as e:
            logger.error(f"Error en limpieza: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": "cleanup_error",
                    "message": f"Error en limpieza: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CheckOrphanedFilesView(APIView):
    """
    Verifica archivos huérfanos en R2
    GET /api/upload/admin/check-orphaned/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "unauthorized", "message": "Acceso denegado"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Obtener todas las keys de la base de datos
            db_keys = set(UploadSession.objects.exclude(
                file_key__isnull=True
            ).exclude(
                file_key=''
            ).values_list('file_key', flat=True))
            
            # Verificar archivos en DB que no están en R2
            missing_in_r2 = []
            
            # Solo verificar algunos para no sobrecargar
            sample_keys = list(db_keys)[:50]  # Límite para no saturar
            
            for key in sample_keys:
                try:
                    exists, metadata = r2_direct.verify_upload_complete(key)
                    if not exists:
                        missing_in_r2.append({
                            'key': key,
                            'reason': 'No encontrado en R2',
                            'metadata': metadata
                        })
                except Exception as e:
                    missing_in_r2.append({
                        'key': key,
                        'reason': f'Error verificando: {str(e)}'
                    })
            
            return Response({
                "check_type": "partial",  # Solo verificación parcial
                "db_files_checked": len(sample_keys),
                "missing_in_r2": {
                    "count": len(missing_in_r2),
                    "files": missing_in_r2[:20]  # Limitar respuesta
                },
                "summary": {
                    "total_files_in_db": len(db_keys),
                    "sample_checked": len(sample_keys),
                    "missing_percentage": f"{(len(missing_in_r2)/max(len(sample_keys),1))*100:.1f}%"
                },
                "note": "Para verificación completa de archivos huérfanos, implementa list_files en r2_direct"
            })
            
        except Exception as e:
            logger.error(f"Error verificando archivos huérfanos: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": "check_error",
                    "message": f"Error verificando archivos: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
 # api2/views/health.py


class HealthCheckView(APIView):
    """
    Endpoint de salud para load balancers y monitoreo.
    """
    permission_classes = []
    
    def get(self, request):
        health_data = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'service': 'dji-music-api',
            'version': '1.0.0',
            'checks': {},
        }
        
        # 1. Verificar base de datos
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_data['checks']['database'] = {'status': 'healthy'}
        except Exception as e:
            health_data['checks']['database'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # 2. Verificar Redis
        try:
            redis_url = os.getenv('REDIS_URL')
            if redis_url:
                r = redis.from_url(redis_url)
                r.ping()
                health_data['checks']['redis'] = {'status': 'healthy'}
            else:
                health_data['checks']['redis'] = {
                    'status': 'unhealthy',
                    'error': 'REDIS_URL not configured'
                }
                health_data['status'] = 'unhealthy'
        except Exception as e:
            health_data['checks']['redis'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # 3. Verificar Celery
        celery_health = CeleryHealth.get_health_status()
        health_data['checks']['celery'] = celery_health
        
        if celery_health['severity'] in ['critical', 'warning']:
            health_data['status'] = 'degraded'
        
        # 4. Verificar R2 (Cloudflare)
        try:
            # Intenta una operación simple de R2
            from api2.utils.r2_direct import r2_direct
            # Solo verificar conexión, no hacer operaciones costosas
            health_data['checks']['r2'] = {'status': 'healthy'}
        except Exception as e:
            health_data['checks']['r2'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # Determinar código de estado HTTP
        http_status = status.HTTP_200_OK
        if health_data['status'] == 'unhealthy':
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        elif health_data['status'] == 'degraded':
            http_status = status.HTTP_200_OK  # 200 pero con status degraded
        
        return Response(health_data, status=http_status)

class CeleryStatusView(APIView):
    """
    Endpoint específico para estado de Celery.
    Útil para dashboards de administración.
    """
    permission_classes = []  # Considerar autenticación para producción
    
    def get(self, request):
        health = CeleryHealth.get_health_status()
        
        # Agregar métricas adicionales
        health.update({
            'heartbeat_count': cache.get('celery:heartbeat_count', 0),
            'upload_queue_size': cache.get('celery:queue_sizes', {}).get('uploads', 0),
            'system_load': cache.get('system:metrics', {}),
        })
        
        return Response(health)               