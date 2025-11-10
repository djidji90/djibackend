from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from .views import SongCommentsDetailView
from drf_yasg import openapi
from .views import RandomSongsView
from .views import (
    SongListView,
    LikeSongView,
    DownloadSongView,
    StreamSongView,
    SongLikesView,
    CommentListCreateView,
    SongCommentsDetailView,
    ArtistListView, 
     MusicEventListView,
      MusicEventDetailView,
    song_suggestions
)


# Configuración para generar la documentación con drf-yasg
schema_view = get_schema_view(
    openapi.Info(
        title="Music API",
        default_version='v1',
        description="Documentación de la API para la página de música, incluyendo funcionalidades como buscar canciones, dar likes, comentar y descargar canciones.",
        terms_of_service="https://www.example.com/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

# URLs de la API
urlpatterns = [
    # Ruta para acceder a la documentación de Swagger UI
    path('api2/swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    
    # Endpoints de la API
    path('songs/', SongListView.as_view(), name='song-list'),  # Lista de canciones
    path('songs/random/', RandomSongsView.as_view(), name='random-songs'),
    path('songs/<int:song_id>/like/', LikeSongView.as_view(), name='like-song'),  # Dar like a una canción
    path('songs/<int:song_id>/download/', DownloadSongView.as_view(), name='download-song'),  # Descargar una canción
    path('songs/<int:song_id>/stream/', StreamSongView.as_view(), name='stream-song'),  # Escuchar canción en streaming
    path('songs/<int:song_id>/likes/', SongLikesView.as_view(), name='song-likes'),  # Obtener likes de una canción
    path('songs/<int:song_id>/comments/', CommentListCreateView.as_view(), name='song-comments'),  # Ver y agregar com
    path('songs/<int:pk>/comments/detail/', SongCommentsDetailView.as_view(), name='song-comments-detail'),
    

     # Detalle de un comentario
    path('events/', MusicEventListView.as_view(), name='music-event-list'),
    path('events/<int:pk>/', MusicEventDetailView.as_view(), name='music-event-detail'),
    
    path('artists/', ArtistListView.as_view(), name='artist-list'),  # Lista de artistas
    path('songs/suggestions/', song_suggestions, name='song-suggestions'),
  
]


# Agregar configuración para archivos multimedia
if settings.DEBUG:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
