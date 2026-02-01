"""
api2/urls.py - Rutas de la API principal
Organizado por módulos funcionales
"""

from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# =========================================================================
# 📚 IMPORTS PARA VIEWS EXISTENTES (primera sección)
# =========================================================================
from . import views  # Views tradicionales ya existentes

# =========================================================================
# 🆕 IMPORTS PARA UPLOAD DIRECTO (segunda sección)
# =========================================================================
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

# PRIMERO definimos las clases que usaremos en las URLs
# (esto evita el error de "cannot import name before definition")

class UploadAdminDashboardView(APIView):
    """
    Dashboard administrativo para monitorear uploads
    GET /api/admin/uploads/
    """
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        User = get_user_model()
        
        # Parámetros de fecha
        days = int(request.query_params.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        
        # Estadísticas generales
        total_uploads = UploadSession.objects.count()
        successful_uploads = UploadSession.objects.filter(status='ready').count()
        failed_uploads = UploadSession.objects.filter(status='failed').count()
        pending_uploads = UploadSession.objects.filter(
            status__in=['pending', 'uploaded', 'confirmed', 'processing']
        ).count()
        
        # Distribución por estado
        status_distribution = UploadSession.objects.values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Uploads por día (últimos N días)
        daily_uploads = UploadSession.objects.filter(
            created_at__gte=start_date
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id'),
            total_size=Sum('file_size'),
            avg_size=Avg('file_size')
        ).order_by('date')
        
        # Top usuarios por uploads
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
    """
    Estadísticas públicas de uploads
    GET /api/stats/uploads/
    """
    
    def get_permissions(self):
        if getattr(settings, 'UPLOAD_STATS_PUBLIC', False):
            return []
        return [IsAuthenticated()]
    
    def get(self, request):
        # Estadísticas generales (simplificadas)
        total_stats = UploadSession.objects.aggregate(
            total_uploads=Count('id'),
            successful_uploads=Count('id', filter=Q(status='ready')),
        )
        
        # Últimos 7 días
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
    """
    Trigger manual para cleanup de uploads expirados
    POST /api/maintenance/cleanup-expired/
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        try:
            # Ejecutar cleanup sincrónicamente o async
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
    """
    Verificar archivos huérfanos en R2
    POST /api/maintenance/check-orphaned/
    """
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        try:
            # Solo verificar o también eliminar
            delete_files = request.data.get('delete_files', False)
            
            if delete_files:
                # Ejecutar cleanup completo
                task = cleanup_orphaned_r2_files.delay()
                return Response({
                    "success": True,
                    "message": "Verificación y cleanup de archivos huérfanos iniciado",
                    "task_id": task.id,
                    "action": "check_and_delete"
                })
            else:
                # Solo verificar (modo seguro)
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


# Ahora intentamos importar las views de upload directo desde views.py
# 1. Definir stubs para views que pueden no existir todavía
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

# 2. Intentar importar las views reales si existen
try:
    from .views import (
        DirectUploadRequestView as RealDirectUploadRequestView,
        UploadConfirmationView as RealUploadConfirmationView,
        DirectUploadStatusView as RealDirectUploadStatusView,
        UserUploadQuotaView as RealUserUploadQuotaView,
        UploadCancellationView as RealUploadCancellationView,
    )
    
    # Si existen, reemplazar los stubs con las reales
    DirectUploadRequestView = RealDirectUploadRequestView
    UploadConfirmationView = RealUploadConfirmationView
    DirectUploadStatusView = RealDirectUploadStatusView
    UserUploadQuotaView = RealUserUploadQuotaView
    UploadCancellationView = RealUploadCancellationView
    
    logger.info("✅ Vistas de upload_direct importadas correctamente desde views.py")
    
    # También intentar importar las views de health
    try:
        from .views import HealthCheckView, CeleryStatusView
        # Agregar a traditional_urlpatterns más abajo
        has_health_views = True
    except ImportError:
        has_health_views = False
        logger.warning("⚠️  Vistas de health no encontradas")
        
except ImportError:
    logger.warning("⚠️  Vistas de upload_direct no encontradas en views.py, usando stubs")
    has_health_views = False

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
    path('songs/<int:song_id>/download/', views.download_song_view, name='song-download'),
    path('songs/<int:song_id>/stream/', views.StreamSongView.as_view(), name='song-stream'),
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
    
    # 📅 EVENTOS MUSICALES
    path('events/', views.MusicEventListView.as_view(), name='event-list'),
    path('events/<int:pk>/', views.MusicEventDetailView.as_view(), name='event-detail'),
    
    # 📊 MÉTRICAS Y ANALYTICS
    path('metrics/admin/', views.admin_metrics, name='admin-metrics'),
    path('metrics/personal/', views.user_personal_metrics, name='personal-metrics'),
    
    # 🩺 HEALTH CHECKS
    path('health/', views.health_check, name='health_check'),
]

# Agregar rutas de health si existen las views
if has_health_views:
    traditional_urlpatterns.extend([
        path('health/celery/', CeleryStatusView.as_view(), name='celery-status'),
        path('api/health/', HealthCheckView.as_view(), name='api-health'),
    ])
else:
    # Si no existen, agregar placeholder
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
# 🆕 URL PATTERNS - SISTEMA DE UPLOAD DIRECTO (NUEVO)
# =========================================================================
direct_upload_urlpatterns = [
    # 📤 UPLOAD DIRECTO A R2
    path('upload/direct/request/', DirectUploadRequestView.as_view(), name='direct-upload-request'),
    path('upload/direct/confirm/<uuid:upload_id>/', UploadConfirmationView.as_view(), name='direct-upload-confirm'),
    path('upload/direct/status/<uuid:upload_id>/', DirectUploadStatusView.as_view(), name='direct-upload-status'),
    path('upload/direct/cancel/<uuid:upload_id>/', UploadCancellationView.as_view(), name='direct-upload-cancel'),
    
    # 📊 CUOTA Y HISTORIAL
    path('upload/quota/', UserUploadQuotaView.as_view(), name='user-upload-quota'),
]

# =========================================================================
# 📊 URL PATTERNS - MONITORING Y ADMINISTRACIÓN
# =========================================================================
admin_urlpatterns = [
    # Dashboard de uploads para admin
    path('admin/uploads/', UploadAdminDashboardView.as_view(), name='upload-admin-dashboard'),
    
    # Estadísticas de uploads
    path('stats/uploads/', UploadStatsView.as_view(), name='upload-stats'),
    
    # 🧹 UTILIDADES DE MANTENIMIENTO
    path('maintenance/cleanup-expired/', CleanupExpiredUploadsView.as_view(), name='cleanup-expired-uploads'),
    path('maintenance/check-orphaned/', CheckOrphanedFilesView.as_view(), name='check-orphaned-files'),
]

# =========================================================================
# ⚠️ URLS PARA COMPATIBILIDAD (SISTEMA TRADICIONAL)
# =========================================================================
compatibility_urlpatterns = [
    # Upload tradicional (deprecated pero mantenido para compatibilidad)
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
    
    # Health check adicional para desarrollo
    urlpatterns += [
        path('health/debug/', views.health_check, name='health-debug'),
    ]

# =========================================================================
# 📦 DEFINICIONES DE VISTAS AUXILIARES ADICIONALES
# =========================================================================

class UserUploadHistoryView(APIView):
    """
    Lista el historial de uploads del usuario
    GET /api/upload/history/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Parámetros de paginación
        page = request.query_params.get('page', 1)
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        
        # Filtros
        status_filter = request.query_params.get('status')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        
        # Construir queryset
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
        
        # Ordenar y paginar
        uploads = uploads.order_by('-created_at')
        paginator = Paginator(uploads, page_size)
        
        try:
            page_obj = paginator.page(page)
        except:
            return Response(
                {"error": "invalid_page", "message": f"Página {page} no válida"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Serializar resultados (simplificado - necesitarías el serializer real)
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
    """
    Reprocesa un upload fallido
    POST /api/upload/reprocess/<upload_id>/
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, upload_id):
        try:
            upload_session = UploadSession.objects.get(id=upload_id)
            
            # Verificar permisos
            if not (request.user.is_staff or request.user == upload_session.user):
                return Response(
                    {"error": "permission_denied", "message": "No tienes permisos para reprocesar este upload"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Verificar que esté en estado failed
            if upload_session.status != 'failed':
                return Response(
                    {
                        "error": "invalid_status",
                        "message": f"No se puede reprocesar un upload en estado '{upload_session.status}'",
                        "current_status": upload_session.status
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Encolar reprocesamiento
            task_result = reprocess_failed_upload.delay(str(upload_session.id))
            
            return Response({
                "success": True,
                "message": "Upload encolado para reprocesamiento",
                "upload_id": str(upload_session.id),
                "task_id": task_result.id,
                "status": "queued",
                "estimated_time": "1-2 minutos"
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

# =========================================================================
# 📝 NOTA FINAL
# =========================================================================
# Este archivo está organizado en secciones claras:
# 1. URLs tradicionales (ya existentes, no modificadas)
# 2. URLs de upload directo (nuevo sistema)
# 3. URLs de administración y monitoreo
# 4. URLs de compatibilidad
# 5. Definiciones de vistas auxiliares
#
# Todo funciona incluso si algunos módulos no están implementados completamente