# api2/views/discovery_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django.core.cache import cache
from django.db.models import Count, Q, F
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
import logging

from api2.models import Song
from api2.discovery_serializers import DiscoverySongSerializer, GenreSerializer

logger = logging.getLogger(__name__)

# ============================================
# CONSTANTES
# ============================================
CACHE_TTL = {
    'trending': 3600,        # 1 hora
    'top_plays': 3600,       # 1 hora
    'top_downloads': 3600,   # 1 hora
    'top_likes': 3600,       # 1 hora
    'recent': 300,           # 5 minutos
    'genres': 86400,         # 24 horas
    'genre_songs': 1800,     # 30 minutos
}

# ============================================
# TRENDING (Popularidad combinada)
# ============================================
@extend_schema(
    description="""
    Canciones trending según algoritmo de popularidad.
    Fórmula: plays_count + (downloads_count × 2) + (likes_count × 3)
    """,
    parameters=[
        OpenApiParameter(name='limit', description='Número de resultados (default: 20, max: 100)', required=False, type=int),
    ]
)
class TrendingSongsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        limit = min(int(request.GET.get('limit', 20)), 100)
        cache_key = f'trending_songs_{limit}'
        
        # Intentar obtener de caché
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({
                'status': 'success',
                'data': cached_data,
                'metadata': {
                    'cached': True,
                    'cache_ttl': CACHE_TTL['trending'],
                    'timestamp': timezone.now().isoformat()
                }
            })

        # Calcular trending con anotación
        songs = Song.objects.filter(is_public=True).annotate(
            popularity_score=(
                F('plays_count') * 1 +
                F('downloads_count') * 2 +
                F('likes_count') * 3
            )
        ).order_by('-popularity_score', '-created_at')[:limit]

        serializer = DiscoverySongSerializer(songs, many=True, context={'request': request})
        
        # Guardar en caché
        cache.set(cache_key, serializer.data, timeout=CACHE_TTL['trending'])

        return Response({
            'status': 'success',
            'data': serializer.data,
            'metadata': {
                'cached': False,
                'cache_ttl': CACHE_TTL['trending'],
                'timestamp': timezone.now().isoformat(),
                'total': len(serializer.data)
            }
        })

# ============================================
# TOP DESCARGAS
# ============================================
@extend_schema(
    description="Canciones más descargadas de todos los tiempos",
    parameters=[
        OpenApiParameter(name='limit', description='Número de resultados', required=False, type=int),
    ]
)
class TopDownloadsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        limit = min(int(request.GET.get('limit', 20)), 100)
        cache_key = f'top_downloads_{limit}'
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({
                'status': 'success',
                'data': cached_data,
                'metadata': {'cached': True, 'cache_ttl': CACHE_TTL['top_downloads']}
            })

        songs = Song.objects.filter(is_public=True).order_by('-downloads_count', '-created_at')[:limit]
        serializer = DiscoverySongSerializer(songs, many=True, context={'request': request})
        
        cache.set(cache_key, serializer.data, timeout=CACHE_TTL['top_downloads'])
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'metadata': {'cached': False, 'cache_ttl': CACHE_TTL['top_downloads']}
        })

# ============================================
# TOP REPRODUCCIONES
# ============================================
@extend_schema(
    description="Canciones más reproducidas",
    parameters=[
        OpenApiParameter(name='limit', description='Número de resultados', required=False, type=int),
    ]
)
class TopPlaysView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        limit = min(int(request.GET.get('limit', 20)), 100)
        cache_key = f'top_plays_{limit}'
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({
                'status': 'success',
                'data': cached_data,
                'metadata': {'cached': True, 'cache_ttl': CACHE_TTL['top_plays']}
            })

        songs = Song.objects.filter(is_public=True).order_by('-plays_count', '-created_at')[:limit]
        serializer = DiscoverySongSerializer(songs, many=True, context={'request': request})
        
        cache.set(cache_key, serializer.data, timeout=CACHE_TTL['top_plays'])
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'metadata': {'cached': False, 'cache_ttl': CACHE_TTL['top_plays']}
        })

# ============================================
# TOP LIKES
# ============================================
@extend_schema(
    description="Canciones con más likes",
    parameters=[
        OpenApiParameter(name='limit', description='Número de resultados', required=False, type=int),
    ]
)
class TopLikesView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        limit = min(int(request.GET.get('limit', 20)), 100)
        cache_key = f'top_likes_{limit}'
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({
                'status': 'success',
                'data': cached_data,
                'metadata': {'cached': True, 'cache_ttl': CACHE_TTL['top_likes']}
            })

        songs = Song.objects.filter(is_public=True).order_by('-likes_count', '-created_at')[:limit]
        serializer = DiscoverySongSerializer(songs, many=True, context={'request': request})
        
        cache.set(cache_key, serializer.data, timeout=CACHE_TTL['top_likes'])
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'metadata': {'cached': False, 'cache_ttl': CACHE_TTL['top_likes']}
        })

# ============================================
# RECIENTES (Novedades)
# ============================================
@extend_schema(
    description="Canciones más recientes añadidas a la plataforma",
    parameters=[
        OpenApiParameter(name='limit', description='Número de resultados', required=False, type=int),
    ]
)
class RecentSongsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        limit = min(int(request.GET.get('limit', 20)), 100)
        cache_key = f'recent_songs_{limit}'
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({
                'status': 'success',
                'data': cached_data,
                'metadata': {'cached': True, 'cache_ttl': CACHE_TTL['recent']}
            })

        songs = Song.objects.filter(is_public=True).order_by('-created_at')[:limit]
        serializer = DiscoverySongSerializer(songs, many=True, context={'request': request})
        
        cache.set(cache_key, serializer.data, timeout=CACHE_TTL['recent'])
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'metadata': {'cached': False, 'cache_ttl': CACHE_TTL['recent']}
        })

# ============================================
# LISTA DE GÉNEROS (con conteo)
# ============================================
@extend_schema(
    description="Lista todos los géneros disponibles con conteo de canciones",
)
class GenreListView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        cache_key = 'genres_list'
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({
                'status': 'success',
                'data': cached_data,
                'metadata': {'cached': True, 'cache_ttl': CACHE_TTL['genres']}
            })

        # Obtener todos los géneros con conteo
        genres = Song.objects.filter(is_public=True).values('genre').annotate(
            song_count=Count('id')
        ).exclude(genre__isnull=True).exclude(genre='').order_by('-song_count')

        # Para cada género, obtener una imagen de muestra
        result = []
        for g in genres:
            sample_song = Song.objects.filter(genre=g['genre'], is_public=True).first()
            sample_image = None
            if sample_song and sample_song.image_key:
                from api2.r2_utils import generate_presigned_url
                sample_image = generate_presigned_url(sample_song.image_key, expiration=3600)

            # Obtener artistas destacados de este género
            top_artists = Song.objects.filter(genre=g['genre'], is_public=True).values('artist').annotate(
                count=Count('id')
            ).order_by('-count')[:5]

            result.append({
                'name': g['genre'],
                'song_count': g['song_count'],
                'sample_image': sample_image,
                'top_artists': [a['artist'] for a in top_artists]
            })

        cache.set(cache_key, result, timeout=CACHE_TTL['genres'])
        
        return Response({
            'status': 'success',
            'data': result,
            'metadata': {'cached': False, 'cache_ttl': CACHE_TTL['genres']}
        })

# ============================================
# CANCIONES POR GÉNERO
# ============================================
@extend_schema(
    description="Obtiene canciones de un género específico",
    parameters=[
        OpenApiParameter(name='limit', description='Número de resultados (default: 20, max: 100)', required=False, type=int),
        OpenApiParameter(name='sort', description='Orden: popular, recent, downloads, plays, likes', required=False, type=str),
    ]
)
class SongsByGenreView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request, genre):
        limit = min(int(request.GET.get('limit', 20)), 100)
        sort_by = request.GET.get('sort', 'popular')
        cache_key = f'genre_{genre}_{sort_by}_{limit}'
        
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({
                'status': 'success',
                'data': cached_data,
                'metadata': {'cached': True, 'cache_ttl': CACHE_TTL['genre_songs']}
            })

        # Base queryset
        queryset = Song.objects.filter(genre=genre, is_public=True)

        # Aplicar ordenamiento
        if sort_by == 'popular':
            queryset = queryset.annotate(
                popularity=F('plays_count') + 2*F('downloads_count') + 3*F('likes_count')
            ).order_by('-popularity', '-created_at')
        elif sort_by == 'recent':
            queryset = queryset.order_by('-created_at')
        elif sort_by == 'downloads':
            queryset = queryset.order_by('-downloads_count', '-created_at')
        elif sort_by == 'plays':
            queryset = queryset.order_by('-plays_count', '-created_at')
        elif sort_by == 'likes':
            queryset = queryset.order_by('-likes_count', '-created_at')

        songs = queryset[:limit]
        serializer = DiscoverySongSerializer(songs, many=True, context={'request': request})
        
        cache.set(cache_key, serializer.data, timeout=CACHE_TTL['genre_songs'])
        
        return Response({
            'status': 'success',
            'data': serializer.data,
            'metadata': {
                'cached': False,
                'cache_ttl': CACHE_TTL['genre_songs'],
                'genre': genre,
                'sort': sort_by,
                'total': len(serializer.data)
            }
        })