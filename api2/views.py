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
    description="Obtener sugerencias de búsqueda en tiempo real",
    parameters=[
        OpenApiParameter(name='query', description='Texto de búsqueda', required=True, type=str)
    ]
)
@api_view(['GET'])
def song_suggestions(request):
    query = request.GET.get('query', '').strip()[:100]
    
    if not query:
        return Response({"suggestions": []})
    
    # Búsqueda en múltiples campos con ponderación
    title_results = Song.objects.filter(
        Q(title__icontains=query)
    ).annotate(
        type=Value('song', output_field=CharField()),
        display=Lower('title')
    ).values('id', 'display', 'type', 'artist', 'genre')[:3]
    
    artist_results = Song.objects.filter(
        Q(artist__icontains=query)
    ).annotate(
        type=Value('artist', output_field=CharField()),
        display=Lower('artist')
    ).values('id', 'display', 'type', 'artist', 'genre').distinct()[:3]
    
    genre_results = Song.objects.filter(
        Q(genre__icontains=query)
    ).annotate(
        type=Value('genre', output_field=CharField()),
        display=Lower('genre')
    ).values('id', 'display', 'type', 'artist', 'genre').distinct()[:2]
    
    # Combinar resultados preservando el orden de relevancia
    suggestions = list(title_results) + list(artist_results) + list(genre_results)
    
    # Eliminar duplicados manteniendo el primer ocurrencia
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        key = (s['display'], s['type'])
        if key not in seen:
            seen.add(key)
            unique_suggestions.append({
                "id": s['id'],
                "title": s['display'] if s['type'] == 'song' else None,
                "artist": s['artist'],
                "genre": s['genre'],
                "type": s['type'],
                "display": f"{s['display']} ({s['type']})"
            })
    
    return Response({"suggestions": unique_suggestions[:5]})

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

# Download Song View
# REEMPLAZAR la vista DownloadSongView actual


# =============================================================================
# 🆕 DOWNLOAD SONG VIEW - VERSIÓN MEJORADA
# =============================================================================

class DownloadSongView(APIView):
    """
    Descarga con streaming directo desde R2 (attachment), con soporte de Range (resume).
    Requiere que stream_file_from_r2 pueda aceptar start/end o range_header y devuelva
    un dict con 'Body' (StreamingBody con iter_chunks y close) y opcionalmente 'content_length'.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    RATE_CACHE_TIMEOUT = 3600  # segundos (1 hora)
    CHUNK_SIZE = 64 * 1024  # 64 KB recommended

    def _parse_range_header(self, range_header, file_size):
        """
        Parse simple 'bytes=start-end' header.
        Devuelve (start, end) o None si no hay header.
        Lanza HttpResponse(status=400/416) si el header está mal formado / no satisfacible.
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

    @extend_schema(
        description="""
        Descargar una canción con streaming eficiente y soporte para reanudación.
        
        Características:
        - Streaming directo desde R2 sin intermediarios
        - Soporte para Range requests (reanudar descargas)
        - Control de frecuencia (1 descarga por hora por canción)
        - Nombres de archivo compatibles con Unicode
        - Chunks optimizados de 64KB para mejor performance
        """,
        responses={
            200: OpenApiResponse(description="Stream de descarga iniciado"),
            206: OpenApiResponse(description="Stream parcial (Range request)"),
            404: OpenApiResponse(description="Canción o archivo no encontrado"),
            416: OpenApiResponse(description="Range no satisfacible"),
            429: OpenApiResponse(description="Límite de descargas excedido"),
            500: OpenApiResponse(description="Error interno del servidor")
        }
    )
    def get(self, request, song_id):
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
                        "retry_after": self.RATE_CACHE_TIMEOUT
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

            # 5. Registrar descarga (no bloquear la experiencia del usuario)
            try:
                with transaction.atomic():
                    Download.objects.create(user=request.user, song=song)
                    cache.set(cache_key, True, timeout=self.RATE_CACHE_TIMEOUT)
            except IntegrityError:
                logger.exception("Error registrando descarga (se continúa con el stream)")

            # 6. Parse Range header (si existe)
            range_header = request.META.get('HTTP_RANGE', '').strip()
            parsed = self._parse_range_header(range_header, file_size) if range_header else None
            if isinstance(parsed, HttpResponse):
                return parsed  # error 400/416

            if parsed:
                start, end = parsed
                status_code = 206
                content_length = (end - start) + 1
                content_range = f"bytes {start}-{end}/{file_size}"
            else:
                start = None
                end = None
                status_code = 200
                content_length = file_size
                content_range = None

            # 7. Obtener stream desde R2 — usar start/end con la nueva función mejorada
            s3_resp = stream_file_from_r2(
                song.file_key, 
                start=start, 
                end=end, 
                range_header=range_header if range_header else None
            )

            if not s3_resp or 'Body' not in s3_resp:
                logger.error("stream_file_from_r2 returned no body for key %s", song.file_key)
                return Response({"error": "Error al acceder al archivo"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            body = s3_resp['Body']  # StreamingBody-like object expected

            # 8. Filename seguro (unicode)
            filename = slugify(song.title or f"song_{song.id}", allow_unicode=True)

            # 9. StreamingHttpResponse con closure seguro
            def stream_generator():
                try:
                    for chunk in body.iter_chunks(chunk_size=self.CHUNK_SIZE):
                        if chunk:
                            yield chunk
                finally:
                    # Ensure the body is closed to free connection
                    try:
                        body.close()
                    except Exception:
                        logger.debug("body.close() failed or not available")

            response = StreamingHttpResponse(stream_generator(), status=status_code, content_type=content_type)
            response['Content-Disposition'] = self._build_content_disposition(filename)
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

            logger.info("DOWNLOAD start user=%s song=%s size=%s range=%s", 
                       request.user.id, song_id, content_length, 
                       f"{start}-{end}" if start is not None else "full")
            return response

        except Exception as exc:
            logger.exception("ERROR DESCARGA - song=%s user=%s", song_id, getattr(request.user, 'id', None))
            return Response(
                {"error": "Error interno del servidor", "message": "No se pudo completar la descarga."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# 🆕 STREAM SONG VIEW - VERSIÓN MEJORADA  
# =============================================================================



class StreamSongView(APIView):
    """
    Streaming seguro con logs completos y fail-safe
    """
    permission_classes = [IsAuthenticated]
    CHUNK_SIZE = 64 * 1024  # 64 KB

    def _parse_range_header(self, range_header, file_size):
        try:
            if not range_header:
                return None

            unit, range_spec = range_header.split('=', 1)
            if unit.strip().lower() != 'bytes':
                return HttpResponse(status=400)

            parts = range_spec.split('-', 1)
            start = int(parts[0]) if parts[0] else None
            end = int(parts[1]) if len(parts) > 1 and parts[1] != '' else None

            # Suffix-byte-range-spec
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
        except Exception as e:
            logger.error("Error parsing Range header: %s | header=%s", e, range_header)
            return HttpResponse(status=400)

    @extend_schema(
        description="Streaming seguro con logs detallados",
        responses={
            200: OpenApiResponse(description="Stream completo"),
            206: OpenApiResponse(description="Stream parcial"),
            404: OpenApiResponse(description="Archivo no encontrado"),
            416: OpenApiResponse(description="Range no válido"),
            500: OpenApiResponse(description="Error interno")
        }
    )
    def get(self, request, song_id):
        try:
            logger.info("STREAM START | user=%s song_id=%s", getattr(request.user, 'id', None), song_id)

            # 1️⃣ Obtener canción
            song = get_object_or_404(Song, id=song_id)
            if not song.file_key:
                logger.warning("Archivo no disponible | song_id=%s", song_id)
                return Response({"error": "Archivo no disponible"}, status=status.HTTP_404_NOT_FOUND)

            # 2️⃣ Verificar existencia en R2
            exists = check_file_exists(song.file_key)
            if not exists:
                logger.error("Archivo no encontrado en R2 | key=%s", song.file_key)
                return Response({"error": "Archivo no encontrado en R2"}, status=status.HTTP_404_NOT_FOUND)

            # 3️⃣ Obtener metadata
            file_info = get_file_info(song.file_key)
            if not file_info:
                logger.error("No se obtuvo file_info | key=%s", song.file_key)
                return Response({"error": "No se pudo obtener información del archivo"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            file_size = int(file_info.get('size', 0))
            content_type = file_info.get('content_type', 'audio/mpeg')

            # 4️⃣ Parse Range
            range_header = request.META.get('HTTP_RANGE', '').strip()
            parsed = self._parse_range_header(range_header, file_size) if range_header else None
            if isinstance(parsed, HttpResponse):
                logger.warning("Range header inválido | header=%s", range_header)
                return parsed

            if parsed:
                start, end = parsed
                status_code = 206
                content_length = (end - start) + 1
                content_range = f"bytes {start}-{end}/{file_size}"
            else:
                start, end = 0, file_size - 1
                status_code = 200
                content_length = file_size
                content_range = None

            logger.info("Streaming | start=%s end=%s size=%s", start, end, file_size)

            # 5️⃣ Obtener stream
            s3_resp = stream_file_from_r2(song.file_key, start=start, end=end, range_header=range_header)
            if not s3_resp:
                logger.error("stream_file_from_r2 returned None | key=%s", song.file_key)
                return Response({"error": "Error accediendo al archivo"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            body = s3_resp.get('Body')
            if not body or not hasattr(body, 'iter_chunks'):
                logger.error("Body inválido o iter_chunks no disponible | key=%s | body=%s", song.file_key, body)
                return Response({"error": "Archivo no apto para streaming"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 6️⃣ Generador seguro
            def stream_gen():
                try:
                    for chunk in body.iter_chunks(chunk_size=self.CHUNK_SIZE):
                        if chunk:
                            yield chunk
                finally:
                    try:
                        body.close()
                    except Exception:
                        logger.debug("body.close() falló")

            # 7️⃣ Preparar response
            response = StreamingHttpResponse(stream_gen(), status=status_code, content_type=content_type)
            response['Content-Length'] = str(content_length)
            response['Accept-Ranges'] = 'bytes'
            response['Cache-Control'] = 'no-cache'
            response['X-Audio-Title'] = song.title or 'Unknown'
            response['X-Audio-Artist'] = song.artist or 'Unknown'

            if content_range:
                response['Content-Range'] = content_range

            logger.info("STREAM SUCCESS | user=%s song=%s", getattr(request.user, 'id', None), song_id)
            return response

        except Exception as e:
            logger.exception("STREAM ERROR | user=%s song=%s | exc=%s", getattr(request.user, 'id', None), song_id, e)
            return Response({"error": "Error en streaming", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
    description="Health check del sistema para load balancers y monitoring",
    responses={
        200: OpenApiResponse(description="Sistema saludable"),
        503: OpenApiResponse(description="Sistema no saludable")
    }
)
@api_view(['GET'])
def health_check(request):
    """
    Health check mínimo para load balancers y monitoring
    """
    try:
        # Verificación básica de base de datos
        Song.objects.count()
        
        return Response({
            "status": "OK", 
            "timestamp": timezone.now().isoformat(),
            "service": "DjiMusic API",
            "version": "1.0.0"
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return Response(
            {"status": "ERROR", "error": str(e)}, 
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )