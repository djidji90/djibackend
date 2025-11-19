# api2/urls.py
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from . import views

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
    # Documentación
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    
    # Songs - Listado y gestión
    path('songs/', views.SongListView.as_view(), name='song-list'),
    path('songs/random/', views.RandomSongsView.as_view(), name='random-songs'),
    path('songs/<int:song_id>/delete/', views.SongDeleteView.as_view(), name='song-delete'),
    
    # Songs - Interacciones
    path('songs/<int:song_id>/like/', views.LikeSongView.as_view(), name='song-like'),
    path('songs/<int:song_id>/download/', views.DownloadSongView.as_view(), name='song-download'),
    path('songs/<int:song_id>/stream/', views.StreamSongView.as_view(), name='song-stream'),
    path('songs/<int:song_id>/likes/', views.SongLikesView.as_view(), name='song-likes'),
    
    # Songs - Comentarios
    path('songs/<int:song_id>/comments/', views.CommentListCreateView.as_view(), name='song-comments'),
    path('songs/comments/<int:pk>/', views.SongCommentsDetailView.as_view(), name='comment-detail'),
    
    # Búsqueda y descubrimiento
    path('suggestions/', views.song_suggestions, name='song-suggestions'),
    path('search/suggestions/', views.SongSearchSuggestionsView.as_view(), name='song-search-suggestions'),
    path('artists/', views.ArtistListView.as_view(), name='artist-list'),
    
    # Eventos musicales
    path('events/', views.MusicEventListView.as_view(), name='event-list'),
    path('events/<int:pk>/', views.MusicEventDetailView.as_view(), name='event-detail'),
]

# Agregar configuración para archivos multimedia en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)