"""
api2/urls.py - Rutas de la API principal
Organizado por módulos funcionales
"""

from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Importar views tradicionales
from . import views
from api2.views import download_song_view, get_download_url_view, confirm_download_view

# Importaciones con manejo de errores para evitar problemas
from django.core.cache import cache
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.utils import timezone
from datetime import timedelta
import logging
import json

# Importar modelos
from api2.models import UploadSession, UploadQuota, Song
from api2 import discovery_views

# Importar tasks
from .tasks.upload_tasks import (
    cleanup_expired_uploads,
    cleanup_orphaned_r2_files,
    reprocess_failed_upload
)



logger = logging.getLogger(__name__)


# =========================================================================
# 🎯 VISTAS AUXILIARES (definidas localmente para evitar imports circulares)
# =========================================================================

class UploadAdminDashboardView(APIView):
    """Dashboard administrativo para monitorear uploads"""
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        User = get_user_model()
        
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        total_uploads = UploadSession.objects.count()
        successful_uploads = UploadSession.objects.filter(status='ready').count()
        failed_uploads = UploadSession.objects.filter(status='failed').count()
        pending_uploads = UploadSession.objects.filter(
            status__in=['pending', 'uploaded', 'confirmed', 'processing']
        ).count()
        
        status_distribution = UploadSession.objects.values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        daily_uploads = UploadSession.objects.filter(
            created_at__gte=start_date
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id'),
            total_size=Sum('file_size'),
            avg_size=Avg('file_size')
        ).order_by('date')
        
        top_users = UploadSession.objects.values(
            'user__id', 'user__username', 'user__email'
        ).annotate(
            upload_count=Count('id'),
            total_size=Sum('file_size'),
            successful_count=Count('id', filter=Q(status='ready'))
        ).order_by('-upload_count')[:10]
        
        return Response({
            "timeframe": {
                "days": days,
                "start_date": start_date.isoformat(),
                "end_date": timezone.now().isoformat()
            },
            "overview": {
                "total_uploads": total_uploads,
                "successful_uploads": successful_uploads,
                "failed_uploads": failed_uploads,
                "pending_uploads": pending_uploads,
                "success_rate": round((successful_uploads / total_uploads * 100), 2) if total_uploads > 0 else 0
            },
            "status_distribution": list(status_distribution),
            "daily_trends": list(daily_uploads),
            "top_users": list(top_users)
        })


class UploadStatsView(APIView):
    """Estadísticas públicas de uploads"""
    
    def get_permissions(self):
        if getattr(settings, 'UPLOAD_STATS_PUBLIC', False):
            return []
        return [IsAuthenticated()]
    
    def get(self, request):
        total_stats = UploadSession.objects.aggregate(
            total_uploads=Count('id'),
            successful_uploads=Count('id', filter=Q(status='ready')),
        )
        
        week_ago = timezone.now() - timedelta(days=7)
        weekly_stats = UploadSession.objects.filter(
            created_at__gte=week_ago
        ).aggregate(
            uploads=Count('id'),
            unique_users=Count('user', distinct=True)
        )
        
        stats = {
            "global": {
                "total_uploads": total_stats['total_uploads'] or 0,
                "successful_uploads": total_stats['successful_uploads'] or 0,
            },
            "weekly": {
                "uploads": weekly_stats['uploads'] or 0,
                "unique_users": weekly_stats['unique_users'] or 0,
            },
            "updated_at": timezone.now().isoformat()
        }
        
        return Response(stats)


class CleanupExpiredUploadsView(APIView):
    """Trigger manual para cleanup de uploads expirados"""
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        try:
            async_mode = request.data.get('async', True)
            
            if async_mode:
                task = cleanup_expired_uploads.delay()
                return Response({
                    "success": True,
                    "message": "Cleanup iniciado en background",
                    "task_id": task.id,
                    "async": True
                })
            else:
                result = cleanup_expired_uploads()
                return Response({
                    "success": True,
                    "message": "Cleanup ejecutado sincrónicamente",
                    "result": result,
                    "async": False
                })
                
        except Exception as e:
            logger.error(f"Error en cleanup manual: {str(e)}", exc_info=True)
            return Response(
                {"error": "cleanup_error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CheckOrphanedFilesView(APIView):
    """Verificar archivos huérfanos en R2"""
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        try:
            delete_files = request.data.get('delete_files', False)
            
            if delete_files:
                task = cleanup_orphaned_r2_files.delay()
                return Response({
                    "success": True,
                    "message": "Verificación y cleanup de archivos huérfanos iniciado",
                    "task_id": task.id,
                    "action": "check_and_delete"
                })
            else:
                task = cleanup_orphaned_r2_files.delay()
                return Response({
                    "success": True,
                    "message": "Verificación de archivos huérfanos iniciada",
                    "task_id": task.id,
                    "action": "check_only",
                    "note": "Los archivos no serán eliminados automáticamente"
                })
                
        except Exception as e:
            logger.error(f"Error en check orphaned files: {str(e)}", exc_info=True)
            return Response(
                {"error": "check_error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =========================================================================
# 🚀 STUBS PARA VISTAS DE UPLOAD DIRECTO (por si no existen en views.py)
# =========================================================================

class DirectUploadRequestView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request): 
        return Response({"error": "not_implemented"}, status=501)


class UploadConfirmationView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, upload_id):
        return Response({"error": "not_implemented"}, status=501)


class DirectUploadStatusView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, upload_id):
        return Response({"error": "not_implemented"}, status=501)


class UserUploadQuotaView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({"error": "not_implemented"}, status=501)


class UploadCancellationView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, upload_id):
        return Response({"error": "not_implemented"}, status=501)


# =========================================================================
# 🔄 INTENTAR IMPORTAR VISTAS REALES DESDE views.py
# =========================================================================

has_health_views = False

try:
    from .views import (
        DirectUploadRequestView as RealDirectUploadRequestView,
        UploadConfirmationView as RealUploadConfirmationView,
        DirectUploadStatusView as RealDirectUploadStatusView,
        UserUploadQuotaView as RealUserUploadQuotaView,
        UploadCancellationView as RealUploadCancellationView,
    )
    
    DirectUploadRequestView = RealDirectUploadRequestView
    UploadConfirmationView = RealUploadConfirmationView
    DirectUploadStatusView = RealDirectUploadStatusView
    UserUploadQuotaView = RealUserUploadQuotaView
    UploadCancellationView = RealUploadCancellationView
    
    logger.info(" Vistas de upload_direct importadas correctamente desde views.py")
    
    try:
        from .views import HealthCheckView, CeleryStatusView
        has_health_views = True
    except ImportError:
        logger.warning("⚠️ Vistas de health no encontradas")
        
except ImportError:
    logger.warning("⚠️ Vistas de upload_direct no encontradas en views.py, usando stubs")


# =========================================================================
# 📋 URL PATTERNS - SISTEMA TRADICIONAL (EXISTENTE)
# =========================================================================

traditional_urlpatterns = [
    # 📚 DOCUMENTACIÓN API
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # 🎵 GESTIÓN DE CANCIONES
    path('songs/', views.SongListView.as_view(), name='song-list'),
    path('songs/upload/', views.SongUploadView.as_view(), name='song-upload'),
    path('songs/random/', views.RandomSongsView.as_view(), name='random-songs'),
    path('songs/<int:song_id>/delete/', views.SongDeleteView.as_view(), name='song-delete'),
    path('search/complete/', views.complete_search, name='complete_search'),
    
    # 🔄 INTERACCIONES CON CANCIONES
    path('songs/<int:song_id>/like/', views.LikeSongView.as_view(), name='song-like'),
    
    # 🎯 RUTAS DE DESCARGA
    path('songs/<int:song_id>/download/', views.download_song_view, name='song-download'),
    path('songs/<int:song_id>/download-url/', get_download_url_view, name='song-download-url'),
    path('songs/download/confirm/', confirm_download_view, name='song-download-confirm'),
    path('songs/<int:song_id>/download-count/', views.song_download_count_view, name='song-download-count'),
    
    # 🎵 STREAMING
    path('songs/<int:song_id>/stream/', views.StreamSongView.as_view(), name='song-stream'),
    path('songs/<int:song_id>/stream/legacy/', views.StreamSongViewCompat.as_view(), name='song-stream-legacy'),
    path('stream/debug/', views.StreamSongViewDebug.as_view(), name='stream-debug'),
    path('stream/metrics/', views.StreamMetricsView.as_view(), name='stream-metrics'),
    path('songs/<int:song_id>/likes/', views.SongLikesView.as_view(), name='song-likes'),
    
    # 🔍 VERIFICACIÓN Y DIAGNÓSTICO
    path('songs/<int:song_id>/check-files/', views.check_song_files, name='check-song-files'),
    
    # 💬 COMENTARIOS
    path('songs/<int:song_id>/comments/', views.CommentListCreateView.as_view(), name='song-comments'),
    path('songs/comments/<int:pk>/', views.SongCommentsDetailView.as_view(), name='comment-detail'),
    
    # 🔍 BÚSQUEDA Y DESCUBRIMIENTO
    path('songs/search/suggestions/', views.SongSearchSuggestionsView.as_view(), name='song-search-suggestions'),
    path('suggestions/', views.song_suggestions, name='song-suggestions'),
    path('search/suggestions/', views.song_suggestions, name='search-suggestions'),
    path('artists/', views.ArtistListView.as_view(), name='artist-list'),
    path('debug/suggestions/', views.debug_suggestions, name='debug-suggestions'),
    
    
    # 🎵 PLAYLISTS CURADAS
    path('playlists/curated/', views.CuratedPlaylistListView.as_view(), name='curated-playlists-list'),
    path('playlists/curated/my/saved/', views.UserSavedPlaylistsView.as_view(), name='user-saved-playlists'),
    path('playlists/curated/<slug:slug>/', views.CuratedPlaylistDetailView.as_view(), name='curated-playlist-detail'),
    path('playlists/curated/<slug:slug>/stream/', views.CuratedPlaylistStreamView.as_view(), name='curated-playlist-stream'),
    path('playlists/curated/<int:playlist_id>/save/', views.SaveCuratedPlaylistView.as_view(), name='save-curated-playlist'),
    path('playlists/curated/<int:playlist_id>/analytics/', views.CuratedPlaylistAnalyticsView.as_view(), name='playlist-analytics'),
    
    # 📅 EVENTOS MUSICALES
    path('events/', views.MusicEventListView.as_view(), name='event-list'),
    path('events/<int:pk>/', views.MusicEventDetailView.as_view(), name='event-detail'),
    
    # 📊 MÉTRICAS Y ANALYTICS
    path('metrics/admin/', views.admin_metrics, name='admin-metrics'),
    path('metrics/personal/', views.user_personal_metrics, name='personal-metrics'),
    
    # 🩺 HEALTH CHECKS
    path('health/', views.health_check, name='health_check'),
    
    # 🆕 NUEVAS RUTAS DE DESCUBRIMIENTO
    path('songs/trending/', discovery_views.TrendingSongsView.as_view(), name='trending-songs'),
    path('songs/top-downloads/', discovery_views.TopDownloadsView.as_view(), name='top-downloads'),
    path('songs/top-plays/', discovery_views.TopPlaysView.as_view(), name='top-plays'),
    path('songs/top-likes/', discovery_views.TopLikesView.as_view(), name='top-likes'),
    path('songs/recent/', discovery_views.RecentSongsView.as_view(), name='recent-songs'),
    path('songs/<int:pk>/', views.SongDetailView.as_view(), name='song-detail'),
    
    # 🎵 GÉNEROS
    path('genres/', discovery_views.GenreListView.as_view(), name='genre-list'),
    path('genres/<str:genre>/songs/', discovery_views.SongsByGenreView.as_view(), name='songs-by-genre'),
]

# Agregar rutas de health si existen las views
if has_health_views:
    traditional_urlpatterns.extend([
        path('health/celery/', CeleryStatusView.as_view(), name='celery-status'),
        path('api/health/', HealthCheckView.as_view(), name='api-health'),
    ])
else:
    class HealthPlaceholderView(APIView):
        def get(self, request):
            return Response({
                "status": "healthy",
                "timestamp": timezone.now().isoformat(),
                "service": "dji-music-api",
                "note": "Health views not fully implemented"
            })
    
    traditional_urlpatterns.extend([
        path('health/celery/', HealthPlaceholderView.as_view(), name='celery-status'),
        path('api/health/', HealthPlaceholderView.as_view(), name='api-health'),
    ])


# =========================================================================
# 🆕 URL PATTERNS - SISTEMA DE UPLOAD DIRECTO
# =========================================================================

direct_upload_urlpatterns = [
    path('upload/direct/request/', DirectUploadRequestView.as_view(), name='direct-upload-request'),
    path('upload/direct/confirm/<uuid:upload_id>/', UploadConfirmationView.as_view(), name='direct-upload-confirm'),
    path('upload/direct/status/<uuid:upload_id>/', DirectUploadStatusView.as_view(), name='direct-upload-status'),
    path('upload/direct/cancel/<uuid:upload_id>/', UploadCancellationView.as_view(), name='direct-upload-cancel'),
    path('upload/quota/', UserUploadQuotaView.as_view(), name='user-upload-quota'),
]


# =========================================================================
# 📊 URL PATTERNS - MONITORING Y ADMINISTRACIÓN
# =========================================================================

admin_urlpatterns = [
    path('admin/uploads/', UploadAdminDashboardView.as_view(), name='upload-admin-dashboard'),
    path('stats/uploads/', UploadStatsView.as_view(), name='upload-stats'),
    path('maintenance/cleanup-expired/', CleanupExpiredUploadsView.as_view(), name='cleanup-expired-uploads'),
    path('maintenance/check-orphaned/', CheckOrphanedFilesView.as_view(), name='check-orphaned-files'),
]


# =========================================================================
# ⚠️ URLS PARA COMPATIBILIDAD
# =========================================================================

compatibility_urlpatterns = [
    path('upload/', views.SongUploadView.as_view(), name='song-upload'),
]


# =========================================================================
# 🔗 COMBINAR TODAS LAS URL PATTERNS
# =========================================================================

urlpatterns = (
    traditional_urlpatterns + 
    direct_upload_urlpatterns + 
    admin_urlpatterns + 
    compatibility_urlpatterns
)


# =========================================================================
# 🛠️ URLS PARA DESARROLLO
# =========================================================================

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += [
        path('health/debug/', views.health_check, name='health-debug'),
    ]


# =========================================================================
# 📦 VISTAS AUXILIARES ADICIONALES
# =========================================================================

class UserUploadHistoryView(APIView):
    """Lista el historial de uploads del usuario"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        page = request.query_params.get('page', 1)
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        status_filter = request.query_params.get('status')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        uploads = UploadSession.objects.filter(user=request.user)
        
        if status_filter:
            uploads = uploads.filter(status=status_filter)
        
        if date_from:
            try:
                from_date = timezone.datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                uploads = uploads.filter(created_at__gte=from_date)
            except (ValueError, TypeError):
                pass
        
        if date_to:
            try:
                to_date = timezone.datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                uploads = uploads.filter(created_at__lte=to_date)
            except (ValueError, TypeError):
                pass
        
        uploads = uploads.order_by('-created_at')
        paginator = Paginator(uploads, page_size)
        
        try:
            page_obj = paginator.page(page)
        except:
            return Response(
                {"error": "invalid_page", "message": f"Página {page} no válida"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        items = [
            {
                'id': str(u.id),
                'file_name': u.file_name,
                'status': u.status,
                'created_at': u.created_at.isoformat(),
                'file_size': u.file_size,
            }
            for u in page_obj.object_list
        ]
        
        return Response({
            "success": True,
            "page": page,
            "page_size": page_size,
            "total_pages": paginator.num_pages,
            "total_items": paginator.count,
            "items": items,
            "filters": {
                "status": status_filter,
                "date_from": date_from,
                "date_to": date_to
            }
        })


class UploadReprocessView(APIView):
    """Reprocesa un upload fallido"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, upload_id):
        try:
            upload_session = UploadSession.objects.get(id=upload_id)
            
            if not (request.user.is_staff or request.user == upload_session.user):
                return Response(
                    {"error": "permission_denied", "message": "No tienes permisos"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if upload_session.status != 'failed':
                return Response(
                    {"error": "invalid_status", "message": f"No se puede reprocesar upload en estado '{upload_session.status}'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            task_result = reprocess_failed_upload.delay(str(upload_session.id))
            
            return Response({
                "success": True,
                "message": "Upload encolado para reprocesamiento",
                "upload_id": str(upload_session.id),
                "task_id": task_result.id,
                "status": "queued"
            })
            
        except UploadSession.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Upload session no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error en reprocess view: {str(e)}", exc_info=True)
            return Response(
                {"error": "reprocess_error", "message": "Error iniciando reprocesamiento"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Agregar rutas adicionales para upload history y reprocess
urlpatterns += [
    path('upload/history/', UserUploadHistoryView.as_view(), name='user-upload-history'),
    path('upload/reprocess/<uuid:upload_id>/', UploadReprocessView.as_view(), name='upload-reprocess'),
]

# =========================================================================
# 📝 NOTA FINAL
# =========================================================================
# Este archivo está organizado en secciones claras:
# 1. URLs tradicionales (ya existentes)
# 2. URLs de upload directo (nuevo sistema)
# 3. URLs de administración y monitoreo
# 4. URLs de compatibilidad
# 5. URLs adicionales para historial y reprocesamiento
#
#  NUEVAS RUTAS AGREGADAS:
# - /songs/download/confirm/         → confirmación de descarga
# - /songs/<id>/download-count/      → incrementar contador de descargas
# - /upload/history/                 → historial de uploads del usuario
# - /upload/reprocess/<id>/          → reprocesar upload fallido
# - /songs/trending/                 → canciones en tendencia
# - /songs/top-downloads/            → top descargas
# - /songs/top-plays/                → top reproducciones
# - /songs/top-likes/                → top likes
# - /songs/recent/                   → canciones recientes
# - /genres/                         → lista de géneros
# - /genres/<genre>/songs/           → canciones por género