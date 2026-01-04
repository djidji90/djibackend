from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # =========================================================================
    # 📚 DOCUMENTACIÓN API
    # =========================================================================
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # =========================================================================
    # 🎵 GESTIÓN DE CANCIONES
    # =========================================================================
    path('songs/', views.SongListView.as_view(), name='song-list'),
    path('songs/upload/', views.SongUploadView.as_view(), name='song-upload'),
    path('songs/random/', views.RandomSongsView.as_view(), name='random-songs'),
    path('songs/<int:song_id>/delete/', views.SongDeleteView.as_view(), name='song-delete'),
    path('search/complete/', views.complete_search, name='complete_search'),
    # =========================================================================
    # 🔄 INTERACCIONES CON CANCIONES (STREAMING & DESCARGAS)
    # =========================================================================
    path('songs/<int:song_id>/like/', views.LikeSongView.as_view(), name='song-like'),
    path('songs/<int:song_id>/download/', views.DownloadSongView.as_view(), name='song-download'),
    path('songs/<int:song_id>/stream/', views.StreamSongView.as_view(), name='song-stream'),
    path('songs/<int:song_id>/likes/', views.SongLikesView.as_view(), name='song-likes'),
    
    # =========================================================================
    # 🔍 VERIFICACIÓN Y DIAGNÓSTICO
    # =========================================================================
    path('songs/<int:song_id>/check-files/', views.check_song_files, name='check-song-files'),

    # =========================================================================
    # 💬 COMENTARIOS
    # =========================================================================
    path('songs/<int:song_id>/comments/', views.CommentListCreateView.as_view(), name='song-comments'),
    path('songs/comments/<int:pk>/', views.SongCommentsDetailView.as_view(), name='comment-detail'),
    
    # =========================================================================
    # 🔍 BÚSQUEDA Y DESCUBRIMIENTO
    # =========================================================================
    path('suggestions/', views.song_suggestions, name='song-suggestions'),
    path('search/suggestions/', views.SongSearchSuggestionsView.as_view(), name='song-search-suggestions'),
    path('artists/', views.ArtistListView.as_view(), name='artist-list'),

    # =========================================================================
    # 📅 EVENTOS MUSICALES
    # =========================================================================
    path('events/', views.MusicEventListView.as_view(), name='event-list'),
    path('events/<int:pk>/', views.MusicEventDetailView.as_view(), name='event-detail'),

    # =========================================================================
    # 📊 MÉTRICAS Y ANALYTICS (NUEVO)
    # =========================================================================
    path('metrics/admin/', views.admin_metrics, name='admin-metrics'),
    path('metrics/personal/', views.user_personal_metrics, name='personal-metrics'),

    # =========================================================================
    # 🩺 HEALTH CHECKS (NUEVO)
    # =========================================================================
    path('health/', views.health_check, name='health_check'),
]

# =============================================================================
# 🛠️ URLS PARA DESARROLLO
# =============================================================================
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Health check adicional para desarrollo
    urlpatterns += [
        path('health/debug/', views.health_check, name='health-debug'),
    ]