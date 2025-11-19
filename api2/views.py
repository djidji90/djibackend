# Importaciones optimizadas y corregidas
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.db import DatabaseError, IntegrityError, transaction
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.db.models.functions import Lower
from django.db.models import Value, CharField, Q, Count
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import Song, Like, Download, Comment, MusicEvent
from .r2_utils import upload_file_to_r2, generate_presigned_url, delete_file_from_r2, check_file_exists
from .r2_client import r2_client, R2_BUCKET_NAME
from .serializers import SongSerializer, CommentSerializer, MusicEventSerializer
import logging
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework import status
from django.core.cache import cache
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.throttling import UserRateThrottle
from django.http import StreamingHttpResponse
import random
from rest_framework.filters import SearchFilter

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
            queryset = Song.objects.annotate(annotated_likes_count=Count('like'))
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
            song = serializer.save()
            file_obj = self.request.FILES.get('file')
            
            if file_obj:
                # Generar key única para R2
                key = f"songs/{song.id}/{file_obj.name}"
                
                # Subir archivo a R2
                if upload_file_to_r2(file_obj, key):
                    # Actualizar el modelo con la referencia al archivo en R2
                    song.file.name = key
                    song.save()
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
@extend_schema(description="Descargar una canción con control de frecuencia")
class DownloadSongView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request, song_id):
        try:
            song = get_object_or_404(Song, id=song_id)
            if not song.file:
                return Response({"error": "Archivo no disponible"}, status=status.HTTP_404_NOT_FOUND)

            cache_key = f"download_{request.user.id}_{song_id}"
            if cache.get(cache_key):
                return Response(
                    {"error": "Espere 1 hora antes de volver a descargar"},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            # Registrar descarga
            with transaction.atomic():
                Download.objects.create(user=request.user, song=song)
                cache.set(cache_key, True, timeout=3600)

            # Generar URL firmada temporal usando la función de utilidad
            download_url = generate_presigned_url(song.file.name, expiration=3600)
            
            if not download_url:
                return Response(
                    {"error": "Error al generar URL de descarga"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response({"download_url": download_url}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in download: {e}")
            return Response(
                {"error": "Error al procesar la descarga"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Stream Song View
@extend_schema(description="Reproducir una canción en streaming")
class StreamSongView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, song_id):
        try:
            song = get_object_or_404(Song, id=song_id)
            if not song.file:
                return Response({"error": "Archivo no disponible"}, status=status.HTTP_404_NOT_FOUND)

            # Generar URL temporal para streaming usando la función de utilidad
            stream_url = generate_presigned_url(song.file.name, expiration=3600)
            
            if not stream_url:
                return Response(
                    {"error": "Error al generar URL de streaming"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Devolver la URL para que el frontend la use
            return Response({
                "stream_url": stream_url,
                "song_title": song.title,
                "artist": song.artist,
                "duration": song.duration
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            return Response(
                {"error": "Error al iniciar la transmisión"},
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
            # ⚠️ CORRECCIÓN: Usar get() con valor por defecto
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
            # ⚠️ CORRECCIÓN: Verificar que song_id existe
            song_id = self.kwargs.get('song_id')
            if not song_id:
                raise ValidationError("ID de canción no proporcionado en la URL")
            
            # ⚠️ CORRECCIÓN: Verificar que la canción existe
            from .models import Song
            song = Song.objects.filter(id=song_id).first()
            if not song:
                raise ValidationError("La canción especificada no existe")
                
            serializer.save(user=self.request.user, song_id=song_id)
            cache.delete(f"song_{song_id}_comments")
            
        except IntegrityError as e:
            logger.error(f"Error creating comment: {e}")
            raise ValidationError("Error de integridad al crear comentario")
        except ValidationError:
            raise  # Re-lanzar ValidationError para que DRF lo maneje
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
            if song.file:
                delete_file_from_r2(song.file.name)
            
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