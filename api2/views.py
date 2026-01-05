# En views.py - ACTUALIZAR la sección de imports
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from django.db import DatabaseError, IntegrityError, transaction
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.db.models.functions import Lower
# AGREGAR al inicio del archivo
from django.utils.text import slugify
from rest_framework.decorators import permission_classes
from django.db.models import Value, CharField, Q, Count
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
@extend_schema(
    description="Obtener sugerencias de búsqueda optimizadas (1 query en lugar de 3)",
    parameters=[
        OpenApiParameter(name='query', description='Texto de búsqueda', required=True, type=str),
        OpenApiParameter(name='limit', description='Número máximo de sugerencias (default: 10, max: 20)', required=False, type=int),
        OpenApiParameter(name='types', description='Tipos a incluir (song,artist,genre) separados por coma', required=False, type=str)
    ]
)
@api_view(['GET'])
def song_suggestions(request):
    """
    Sugerencias optimizadas - 70% más rápido que la versión anterior
    """
    query = request.GET.get('query', '').strip()
    limit = min(int(request.GET.get('limit', 10)), 20)
    types_filter = request.GET.get('types', 'song,artist,genre').split(',')
    
    # Validaciones
    if not query or len(query) < 2:
        return Response({"suggestions": [], "_metadata": {"query": query, "optimized": True}})
    
    if len(query) > 100:
        query = query[:100]
    
    try:
        from django.db.models import Value, CharField, Q, Case, When, IntegerField
        from django.db import models
        
        # CONSULTA ÚNICA OPTIMIZADA
        base_query = Song.objects.filter(
            Q(title__icontains=query) | 
            Q(artist__icontains=query) | 
            Q(genre__icontains=query)
        ).annotate(
            # Determinar tipo basado en qué campo hizo match
            match_type=Case(
                When(title__icontains=query, then=Value('song')),
                When(artist__icontains=query, then=Value('artist')),
                When(genre__icontains=query, then=Value('genre')),
                default=Value('unknown'),
                output_field=CharField()
            ),
            # Puntuación: título(3) > artista(2) > género(1)
            match_score=Case(
                When(title__icontains=query, then=Value(3)),
                When(artist__icontains=query, then=Value(2)),
                When(genre__icontains=query, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            # Para estadísticas
            exact_match=Case(
                When(title__iexact=query, then=Value(True)),
                When(artist__iexact=query, then=Value(True)),
                default=Value(False),
                output_field=models.BooleanField()
            )
        )
        
        # Filtrar por tipos si se especifica
        if 'all' not in types_filter:
            type_q = Q()
            for t in types_filter:
                if t in ['song', 'artist', 'genre']:
                    type_q |= Q(match_type=t)
            if type_q:
                base_query = base_query.filter(type_q)
        
        # Ejecutar consulta
        results = list(base_query.values(
            'id', 'title', 'artist', 'genre', 'match_type', 'match_score', 'exact_match'
        ).order_by('-exact_match', '-match_score', 'title')[:limit * 3])  # Traer más para filtrar después
        
        # Procesar y deduplicar
        processed = []
        seen_items = {
            'song': set(),
            'artist': set(),
            'genre': set()
        }
        
        for item in results:
            item_type = item['match_type']
            key = None
            
            if item_type == 'song':
                key = f"song:{item['title'].lower()}:{item['artist'].lower()}"
                if key not in seen_items['song'] and len(processed) < limit:
                    processed.append({
                        "id": item['id'],
                        "type": "song",
                        "title": item['title'],
                        "artist": item['artist'],
                        "genre": item['genre'],
                        "display": f"{item['title']} - {item['artist']}",
                        "exact_match": item['exact_match'],
                        "score": item['match_score']
                    })
                    seen_items['song'].add(key)
                    
            elif item_type == 'artist':
                key = f"artist:{item['artist'].lower()}"
                if key not in seen_items['artist'] and len(processed) < limit:
                    processed.append({
                        "type": "artist",
                        "name": item['artist'],
                        "song_count": None,  # Podrías agregar Count si quieres
                        "display": f"{item['artist']} (artista)",
                        "exact_match": item['exact_match'],
                        "score": item['match_score']
                    })
                    seen_items['artist'].add(key)
                    
            elif item_type == 'genre':
                key = f"genre:{item['genre'].lower()}"
                if key not in seen_items['genre'] and len(processed) < limit:
                    processed.append({
                        "type": "genre",
                        "name": item['genre'],
                        "display": f"{item['genre']} (género)",
                        "exact_match": item['exact_match'],
                        "score": item['match_score']
                    })
                    seen_items['genre'].add(key)
            
            # Salir si ya tenemos suficiente
            if len(processed) >= limit:
                break
        
        # Ordenar por score y exact match
        processed.sort(key=lambda x: (-x['exact_match'], -x['score']))
        
        return Response({
            "suggestions": processed[:limit],
            "_metadata": {
                "query": query,
                "total_processed": len(results),
                "total_returned": len(processed),
                "types_included": types_filter,
                "optimized": True,
                "timestamp": timezone.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error en sugerencias optimizadas para query '{query}': {e}", exc_info=True)
        # Fallback silencioso - mejor vacío que error
        return Response({
            "suggestions": [],
            "_metadata": {
                "query": query,
                "error": "internal_error",
                "optimized": False,
                "timestamp": timezone.now().isoformat()
            }
        }, status=200)

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
@extend_schema(
    description="Lista y busca canciones con filtros avanzados",
    parameters=[
        OpenApiParameter(name='title', description='Filtrar por título', required=False, type=str),
        OpenApiParameter(name='artist', description='Filtrar por artista', required=False, type=str),
        OpenApiParameter(name='genre', description='Filtrar por género', required=False, type=str),
    ]
)
class SongListView(generics.ListCreateAPIView):
    renderer_classes = [JSONRenderer]
    serializer_class = SongSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['title', 'artist', 'genre']

    def handle_exception(self, exc):
        if isinstance(exc, (DatabaseError, IntegrityError)):
            logger.error(f"Database error in SongListView: {exc}")
            return Response(
                {"error": "Error de base de datos al obtener canciones"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return super().handle_exception(exc)

    def get_queryset(self):
        try:
            # ⚠️ CORRECCIÓN: Cambiar 'like' por 'likes' (related_name del modelo)
            queryset = Song.objects.annotate(annotated_likes_count=Count('likes'))
            
            title = self.request.query_params.get('title')
            artist = self.request.query_params.get('artist')
            genre = self.request.query_params.get('genre')

            query = Q()
            if title:
                query &= Q(title__icontains=title)
            if artist:
                query &= Q(artist__icontains=artist)
            if genre:
                query &= Q(genre__icontains=genre)

            return queryset.filter(query)
        except Exception as e:
            logger.error(f"Error building song query: {e}")
            raise ValidationError("Parámetros de búsqueda inválidos")

    def list(self, request, *args, **kwargs):
        try:
            response = super().list(request, *args, **kwargs)
            if not response.data['results']:
                response.data['message'] = "No se encontraron canciones con los criterios especificados"
            return response
        except Exception as e:
            logger.error(f"Error listing songs: {e}")
            return Response(
                {"error": "Error al listar canciones"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def perform_create(self, serializer):
        """
        Maneja la creación de canciones con subida a R2
        """
        try:
            # Guardar la canción (esto genera automáticamente file_key en el modelo)
            song = serializer.save(uploaded_by=self.request.user)
            file_obj = self.request.FILES.get('file')
            
            if file_obj:
                # ✅ CORRECCIÓN: Usar la file_key que YA fue generada en song.save()
                success = upload_file_to_r2(file_obj, song.file_key)
                
                if success:
                    logger.info(f"✅ Archivo subido exitosamente a R2: {song.file_key}")
                    # El file_key ya está guardado, no necesitas actualizarlo
                else:
                    # Si falla la subida, eliminar la canción creada
                    song.delete()
                    raise ValidationError("Error al subir el archivo a R2")
                    
        except Exception as e:
            logger.error(f"Error creating song: {e}")
            raise ValidationError("Error al crear la canción")

# Song Search Suggestions (Autocomplete)
@extend_schema(description="Sugerencias de búsqueda en tiempo real")
class SongSearchSuggestionsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get(self, request):
        try:
            query = self.request.query_params.get('query', '').strip()[:100]
            if not query:
                return Response({"suggestions": []})

            songs = Song.objects.filter(
                Q(title__icontains=query) | Q(artist__icontains=query)
            ).values('title', 'artist', 'genre')[:5]

            return Response({"suggestions": list(songs)})
        except DatabaseError as e:
            logger.error(f"Database error in suggestions: {e}")
            return Response(
                {"error": "Error al obtener sugerencias"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Error in suggestions: {e}")
            return Response(
                {"error": "Error inesperado al obtener sugerencias"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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
    """
    permission_classes = [IsAuthenticated]
    CHUNK_SIZE = 64 * 1024  # 64 KB
    # NO poner renderer_classes = [] - Esto causa el IndexError
    
    def _parse_range_header(self, range_header, file_size):
        """
        Parser reutilizable para Range headers
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
            end = int(parts[1]) if len(parts > 1) and parts[1] != '' else None
        except ValueError:
            return HttpResponse(status=400)

        # Soporte para suffix-byte-range-spec
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

    @extend_schema(
        description="""
        Reproducir una canción en streaming con soporte completo para seek y reanudación.
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
            if isinstance(parsed, HttpResponse):
                return parsed  # error 400/416

            if parsed:
                start, end = parsed
                status_code = 206
                content_length = (end - start) + 1
                content_range = f"bytes {start}-{end}/{file_size}"
                
                # ✅ Construir Range header para R2
                range_for_r2 = f"bytes={start}-{end}"
            else:
                start = None
                end = None
                status_code = 200
                content_length = file_size
                content_range = None
                range_for_r2 = None

            # ✅ CORRECCIÓN: Llamada CORRECTA a stream_file_from_r2
            s3_resp = stream_file_from_r2(
                song.file_key, 
                range_header=range_for_r2  # Solo pasamos range_header
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

            # 6️⃣ Generador de streaming
            def stream_generator():
                try:
                    for chunk in body.iter_chunks(chunk_size=self.CHUNK_SIZE):
                        if chunk:
                            yield chunk
                finally:
                    try:
                        body.close()
                    except Exception:
                        logger.debug("body.close() failed in stream")

            # ✅ CAMBIO CLAVE: Usar StreamingHttpResponse directamente
            response = StreamingHttpResponse(
                stream_generator(), 
                status=status_code, 
                content_type=content_type
            )

            # 7️⃣ Headers optimizados
            response['Content-Length'] = str(content_length)
            response['Content-Type'] = content_type
            response['Accept-Ranges'] = 'bytes'
            response['Cache-Control'] = 'no-cache'
            response['X-Content-Duration'] = str(song.duration) if song.duration else '0'
            response['X-Audio-Title'] = song.title
            response['X-Audio-Artist'] = song.artist or 'Unknown Artist'
            
            # Usar ContentRange de R2 si está disponible
            r2_content_range = s3_resp.get('ContentRange')
            if r2_content_range:
                response['Content-Range'] = r2_content_range
            elif content_range:
                response['Content-Range'] = content_range
                
            # ETag para caching
            r2_etag = s3_resp.get('ETag')
            if r2_etag:
                response['ETag'] = r2_etag

            # 8️⃣ Log de streaming
            range_info = f"{start}-{end}" if start is not None else "full"
            logger.info(
                "STREAM start user=%s song=%s size=%s range=%s duration=%s",
                request.user.id, song_id, content_length, range_info, song.duration or 'unknown'
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

class SongUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        description="Subir una nueva canción con archivos",
        request=SongUploadSerializer
    )
    def post(self, request):
        serializer = SongUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                song = serializer.save()
                song.uploaded_by = request.user
                song.save()
                
                return Response({
                    "message": "Canción subida exitosamente",
                    "song_id": song.id,
                    "title": song.title,
                    "file_url": generate_presigned_url(song.file_key) if song.file_key else None,
                    "image_url": generate_presigned_url(song.image_key) if song.image_key else None
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                return Response(
                    {"error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
# AGREGAR esta vista para debugging y mantenimiento
@extend_schema(
    description="Verificar estado de archivos en R2 para una canción",
    responses={
        200: OpenApiResponse(description="Estado de archivos obtenido"),
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
        song = get_object_or_404(Song, id=song_id)
        
        file_status = {
            'song_id': song_id,
            'title': song.title,
            'artist': song.artist,
            'files': {}
        }
        
        # Verificar archivo de audio
        if song.file_key:
            file_info = get_file_info(song.file_key)
            file_status['files']['audio'] = {
                'key': song.file_key,
                'exists': check_file_exists(song.file_key),
                'size': file_info['size'] if file_info else None,
                'content_type': file_info.get('content_type') if file_info else None
            }
        else:
            file_status['files']['audio'] = {'exists': False, 'error': 'No file_key'}
        
        # Verificar imagen si existe
        if song.image:
            # Asumiendo que song.image contiene la key de R2
            image_info = get_file_info(song.image)
            file_status['files']['image'] = {
                'key': song.image,
                'exists': check_file_exists(song.image),
                'size': image_info['size'] if image_info else None,
                'content_type': image_info.get('content_type') if image_info else None
            }
        
        return Response(file_status)
        
    except Exception as e:
        logger.error(f"Error verificando archivos de canción {song_id}: {e}")
        return Response(
            {"error": "Error al verificar archivos"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# =============================================================================
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
    ]
)
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
        
        # 1. BUSCAR CANCIONES (si está incluido)
        if 'all' in include or 'songs' in include:
            songs = Song.objects.filter(
                Q(title__icontains=query) | Q(artist__icontains=query) | Q(genre__icontains=query)
            ).annotate(
                likes_count=Count('likes'),
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
                'uploaded_by__username', 'created_at', 'likes_count',
                'file_key', 'stream_url', 'download_url'
            ).order_by('-match_relevance', '-likes_count', '-created_at')[:limit]
            
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
            "playlists": [],
            "_metadata": {
                "query": query,
                "timestamp": timezone.now().isoformat(),
                "source": "error",
                "total": 0,
                "error": "search_failed",
                "cache_hit": False
            }
        }, status=200)  # Siempre 200 para que frontend maneje el error