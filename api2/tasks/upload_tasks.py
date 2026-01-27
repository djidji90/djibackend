# api2/tasks/upload_tasks.py
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone
from django.conf import settings
from django.db import transaction, Count, Q, F
import logging
import os
import tempfile
import hashlib
from datetime import datetime, timedelta
import requests

from api2.models import UploadSession, Song, UserProfile, UploadQuota
from api2.utils.r2_direct import r2_direct, R2UploadValidator

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_direct_upload(self, upload_session_id, file_key=None, file_size=None, 
                          content_type=None, metadata=None):
    """
    Procesa un archivo subido directamente a R2 después de confirmación
    """
    
    logger.info(f"🎵 Iniciando procesamiento de upload: {upload_session_id}")
    
    try:
        # 1. Obtener sesión y actualizar estado
        try:
            upload_session = UploadSession.objects.get(id=upload_session_id)
        except UploadSession.DoesNotExist:
            logger.error(f"Upload session no encontrada: {upload_session_id}")
            raise ValueError(f"Upload session no encontrada: {upload_session_id}")
        
        # Verificar estado
        if upload_session.status != 'confirmed':
            logger.warning(
                f"Upload session {upload_session_id} en estado incorrecto: "
                f"{upload_session.status}. Esperaba 'confirmed'"
            )
            if upload_session.status == 'ready':
                logger.info(f"Upload {upload_session_id} ya está procesado")
                return {'status': 'already_processed', 'song_id': upload_session.song.id}
            elif upload_session.status == 'failed':
                raise ValueError(f"Upload ya falló: {upload_session.status_message}")
        
        # Actualizar estado
        upload_session.status = 'processing'
        upload_session.save(update_fields=['status', 'updated_at'])
        user = upload_session.user
        
        # Usar datos de sesión si no se proporcionan
        if not file_key:
            file_key = upload_session.file_key
        if not file_size:
            file_size = upload_session.file_size
        if not content_type:
            content_type = upload_session.file_type
        if not metadata:
            metadata = upload_session.metadata
        
        # 2. Validar que el archivo existe en R2
        file_exists, file_metadata = r2_direct.verify_file_uploaded(file_key)
        if not file_exists:
            error_msg = f"Archivo no encontrado en R2: {file_key}"
            upload_session.mark_as_failed(error_msg)
            raise ValueError(error_msg)
        
        # 3. Validar integridad del archivo
        validation_result = r2_direct.validate_upload_integrity(
            key=file_key,
            expected_size=file_size,
            expected_uploader_id=user.id
        )
        
        if not validation_result['valid']:
            issues = validation_result.get('issues', [])
            error_msg = f"Archivo inválido: {', '.join(issues)}"
            upload_session.mark_as_failed(error_msg)
            
            # Liberar cuota pendiente
            try:
                quota = UploadQuota.objects.get(user=user)
                quota.release_pending_quota(file_size)
            except Exception as quota_error:
                logger.warning(f"Error liberando cuota: {quota_error}")
            
            raise ValueError(error_msg)
        
        # 4. Procesar archivo
        temp_file = None
        
        try:
            # Generar URL temporal para descarga
            download_url = r2_direct.generate_download_url(file_key, expires_in=600)
            if not download_url:
                raise Exception("No se pudo generar URL de descarga")
            
            # Descargar archivo temporalmente
            temp_file = download_to_tempfile(download_url)
            
            # Validar que sea un archivo de audio válido
            audio_info = validate_and_analyze_audio(temp_file, upload_session.original_file_name)
            
            if not audio_info['is_valid']:
                error_msg = f"Archivo de audio inválido: {audio_info.get('error', 'Unknown error')}"
                upload_session.mark_as_failed(error_msg)
                raise ValueError(error_msg)
            
            # Extraer metadatos de audio (opcional)
            audio_metadata = extract_audio_metadata(temp_file, audio_info)
            
            # Combinar metadatos
            final_metadata = {
                **metadata,
                'audio_info': audio_info,
                'audio_metadata': audio_metadata,
                'processing_timestamp': timezone.now().isoformat(),
                'file_checksum': calculate_file_checksum(temp_file)
            }
            
            # 5. Crear objeto Song con transacción (AJUSTADO A TU MODELO)
            with transaction.atomic():
                song = create_song_record(
                    upload_session=upload_session,
                    user=user,
                    file_key=file_key,
                    audio_info=audio_info,
                    metadata=final_metadata
                )
                
                # Actualizar sesión como completada
                upload_session.mark_as_ready(song)
                
                # Actualizar estadísticas del usuario
                update_user_stats(user, file_size)
                
                logger.info(
                    f"✅ Upload procesado exitosamente: {upload_session_id} → "
                    f"Song: {song.id} ({song.title})"
                )
            
            return {
                'status': 'success',
                'upload_session_id': upload_session_id,
                'song_id': song.id,
                'song_title': song.title,
                'duration': audio_info.get('duration_formatted', '0:00'),
                'file_size_mb': round(file_size / (1024 * 1024), 2)
            }
            
        except Exception as processing_error:
            logger.error(
                f"Error procesando upload {upload_session_id}: {str(processing_error)}",
                exc_info=True
            )
            
            # Marcar como fallido
            upload_session.mark_as_failed(str(processing_error))
            
            # Reintentar si es un error transitorio
            if is_transient_error(processing_error):
                try:
                    logger.warning(f"Reintentando upload {upload_session_id}")
                    raise self.retry(exc=processing_error, countdown=60 * (2 ** self.request.retries))
                except MaxRetriesExceededError:
                    logger.error(f"Max retries exceeded for upload {upload_session_id}")
                    raise
            
            raise
            
        finally:
            # Limpiar archivo temporal
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception as cleanup_error:
                    logger.warning(f"Error limpiando archivo temporal: {cleanup_error}")
    
    except Exception as e:
        logger.error(
            f"Error crítico en process_direct_upload para {upload_session_id}: {str(e)}",
            exc_info=True
        )
        raise


@shared_task
def cleanup_expired_uploads():
    """
    Limpia sesiones de upload expiradas
    Se ejecuta periódicamente (ej: cada hora)
    """
    logger.info("🧹 Iniciando cleanup de uploads expirados...")
    
    expired_cutoff = timezone.now()
    cleaned_count = 0
    quota_freed = 0
    
    try:
        # Buscar sesiones expiradas en estados transitorios
        expired_sessions = UploadSession.objects.filter(
            expires_at__lt=expired_cutoff,
            status__in=['pending', 'uploaded', 'confirmed']
        ).select_related('user')
        
        for session in expired_sessions:
            try:
                with transaction.atomic():
                    # Marcar como expirado
                    old_status = session.status
                    session.mark_as_expired()
                    
                    # Liberar cuota pendiente
                    quota = UploadQuota.objects.select_for_update().get(
                        user=session.user
                    )
                    quota.release_pending_quota(session.file_size)
                    
                    # Opcional: eliminar archivo de R2 si existe
                    if getattr(settings, 'DELETE_EXPIRED_R2_FILES', False):
                        file_exists, _ = r2_direct.verify_file_uploaded(session.file_key)
                        if file_exists:
                            deleted = r2_direct.delete_file(session.file_key)
                            if deleted:
                                logger.debug(f"Archivo expirado eliminado de R2: {session.file_key}")
                    
                    cleaned_count += 1
                    quota_freed += session.file_size
                    
                    logger.debug(
                        f"Session expirada limpiada: {session.id}, "
                        f"estado anterior: {old_status}, "
                        f"tamaño: {session.file_size} bytes"
                    )
                    
            except Exception as session_error:
                logger.error(
                    f"Error limpiando session {session.id}: {str(session_error)}",
                    exc_info=False
                )
                continue
        
        # Limpiar sesiones fallidas muy antiguas (> 7 días)
        if getattr(settings, 'CLEANUP_OLD_FAILED_SESSIONS', True):
            old_failed_cutoff = timezone.now() - timedelta(days=7)
            old_failed = UploadSession.objects.filter(
                status='failed',
                updated_at__lt=old_failed_cutoff
            )
            
            old_count = old_failed.count()
            if old_count > 0:
                old_failed.delete()
                logger.info(f"🧹 Eliminadas {old_count} sesiones fallidas antiguas")
                cleaned_count += old_count
        
        logger.info(
            f"🧹 Cleanup completado: {cleaned_count} sesiones limpiadas, "
            f"{quota_freed / (1024*1024):.2f} MB liberados"
        )
        
        return {
            "cleaned_sessions": cleaned_count,
            "quota_freed_bytes": quota_freed,
            "quota_freed_mb": round(quota_freed / (1024 * 1024), 2),
            "timestamp": timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error en cleanup_expired_uploads: {str(e)}", exc_info=True)
        return {"error": str(e), "cleaned_sessions": 0}


@shared_task
def cleanup_orphaned_r2_files():
    """
    Encuentra y elimina archivos en R2 sin sesión correspondiente
    """
    logger.info("🔍 Buscando archivos huérfanos en R2...")
    
    try:
        # Obtener todas las keys válidas de la base de datos
        valid_keys = set(
            UploadSession.objects.exclude(
                status__in=['expired', 'cancelled']
            ).values_list('file_key', flat=True)
        )
        
        # También incluir canciones existentes
        song_keys = set(Song.objects.values_list('file_key', flat=True))
        valid_keys.update(song_keys)
        
        # Listar todos los archivos en R2
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        orphaned_files = []
        
        for user in User.objects.all():
            user_files = r2_direct.list_user_files(user.id)
            
            for file_info in user_files:
                if file_info['key'] not in valid_keys:
                    orphaned_files.append(file_info)
        
        # Eliminar archivos huérfanos (si está habilitado)
        deleted_count = 0
        if getattr(settings, 'DELETE_ORPHANED_R2_FILES', False) and orphaned_files:
            logger.warning(f"Encontrados {len(orphaned_files)} archivos huérfanos en R2")
            
            for file_info in orphaned_files:
                try:
                    deleted = r2_direct.delete_file(file_info['key'])
                    if deleted:
                        deleted_count += 1
                        logger.info(f"🗑️  Eliminado archivo huérfano: {file_info['key']}")
                except Exception as delete_error:
                    logger.error(f"Error eliminando archivo huérfano {file_info['key']}: {delete_error}")
        
        result = {
            "orphaned_files_found": len(orphaned_files),
            "orphaned_files_deleted": deleted_count,
            "orphaned_files": [
                {
                    'key': f['key'],
                    'size_mb': round(f.get('size', 0) / (1024 * 1024), 2),
                }
                for f in orphaned_files[:10]
            ]
        }
        
        logger.info(f"✅ Cleanup de archivos huérfanos completado: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error en cleanup_orphaned_r2_files: {str(e)}", exc_info=True)
        return {"error": str(e)}


@shared_task
def reprocess_failed_upload(upload_session_id):
    """
    Reintenta procesar un upload que falló previamente
    """
    try:
        upload_session = UploadSession.objects.get(id=upload_session_id)
        
        if upload_session.status != 'failed':
            return {
                'error': 'not_failed',
                'message': f"Upload no está en estado failed (actual: {upload_session.status})"
            }
        
        # Resetear a confirmed para reprocesar
        upload_session.status = 'confirmed'
        upload_session.save(update_fields=['status', 'updated_at'])
        
        # Encolar reprocesamiento
        process_direct_upload.delay(
            upload_session_id=str(upload_session.id),
            file_key=upload_session.file_key,
            file_size=upload_session.file_size,
            content_type=upload_session.file_type,
            metadata=upload_session.metadata
        )
        
        logger.info(f"🔄 Upload {upload_session_id} encolado para reprocesamiento")
        
        return {
            'status': 'reprocessing_queued',
            'upload_session_id': upload_session_id,
            'timestamp': timezone.now().isoformat()
        }
        
    except UploadSession.DoesNotExist:
        return {'error': 'not_found', 'message': 'Upload session no encontrada'}
    except Exception as e:
        logger.error(f"Error en reprocess_failed_upload: {str(e)}")
        return {'error': str(e)}


# ==================== MÉTODOS HELPER ====================

def download_to_tempfile(url):
    """Descarga un archivo a un archivo temporal"""
    temp_fd, temp_path = tempfile.mkstemp(prefix='djidji_upload_', suffix='.tmp')
    os.close(temp_fd)
    
    try:
        response = requests.get(
            url,
            stream=True,
            timeout=(30, 300)
        )
        response.raise_for_status()
        
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return temp_path
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise Exception(f"Error descargando archivo: {str(e)}")


def validate_and_analyze_audio(file_path, original_filename):
    """Valida y analiza un archivo de audio"""
    try:
        # Validaciones básicas
        if not os.path.exists(file_path):
            return {'is_valid': False, 'error': 'File does not exist'}
        
        file_size = os.path.getsize(file_path)
        if file_size < 1024:
            return {'is_valid': False, 'error': 'File too small (< 1KB)'}
        if file_size > 300 * 1024 * 1024:
            return {'is_valid': False, 'error': 'File too large (> 300MB)'}
        
        # Análisis con mutagen si está disponible
        audio_info = {
            'is_valid': True,
            'filename': original_filename,
            'file_size': file_size,
            'analysis_timestamp': timezone.now().isoformat(),
            'duration': 0,
            'duration_formatted': '0:00',
        }
        
        try:
            import mutagen
            audio = mutagen.File(file_path, easy=True)
            
            if audio is not None:
                audio_info['duration'] = audio.info.length
                
                # Formatear duración
                duration_sec = audio_info['duration']
                minutes = int(duration_sec // 60)
                seconds = int(duration_sec % 60)
                audio_info['duration_formatted'] = f"{minutes}:{seconds:02d}"
                
                # Validaciones de calidad
                if audio_info['duration'] < 1:
                    audio_info['is_valid'] = False
                    audio_info['error'] = 'Duration too short (< 1 second)'
                elif audio_info['duration'] > 3600:
                    audio_info['is_valid'] = False
                    audio_info['error'] = 'Duration too long (> 1 hour)'
        
        except ImportError:
            logger.warning("mutagen no instalado, usando validación básica")
        
        return audio_info
        
    except Exception as e:
        logger.error(f"Error analizando audio {file_path}: {str(e)}")
        return {
            'is_valid': False,
            'error': str(e),
            'filename': original_filename
        }


def extract_audio_metadata(file_path, audio_info):
    """Extrae metadatos de audio"""
    metadata = {}
    
    try:
        import mutagen
        audio = mutagen.File(file_path, easy=True)
        
        if audio is not None:
            # Extraer tags comunes
            tags_to_extract = {
                'title': ['title', 'TIT2'],
                'artist': ['artist', 'TPE1'],
                'album': ['album', 'TALB'],
                'genre': ['genre', 'TCON'],
            }
            
            for key, tag_names in tags_to_extract.items():
                for tag in tag_names:
                    if hasattr(audio, 'get'):
                        value = audio.get(tag)
                        if value:
                            if isinstance(value, list):
                                metadata[key] = value[0]
                            else:
                                metadata[key] = str(value)
                            break
            
            # Limpiar strings
            for key in ['title', 'artist', 'album', 'genre']:
                if key in metadata and metadata[key]:
                    metadata[key] = metadata[key].strip()[:255]
    
    except ImportError:
        logger.debug("mutagen no disponible para extraer metadatos")
    
    return metadata


def create_song_record(upload_session, user, file_key, audio_info, metadata):
    """Crea el registro de Song en la base de datos (AJUSTADO A TU MODELO)"""
    
    # Extraer título y artista
    title = (
        metadata.get('title') or 
        metadata.get('audio_metadata', {}).get('title') or
        os.path.splitext(upload_session.original_file_name)[0]
    )
    title = title.replace('_', ' ').replace('-', ' ').title()[:255]
    
    artist = (
        metadata.get('artist') or 
        metadata.get('audio_metadata', {}).get('artist') or 
        'Desconocido'
    )[:255]
    
    # Usar metadata del audio si está disponible
    audio_metadata = metadata.get('audio_metadata', {})
    
    # Crear canción según TU modelo Song
    song = Song.objects.create(
        title=title,
        artist=artist,
        genre=audio_metadata.get('genre', metadata.get('genre', 'Otro'))[:100],
        duration=audio_info.get('duration_formatted', '0:00')[:20],
        file_key=file_key,  # Usamos la key real de R2, NO generamos nueva
        uploaded_by=user,
        is_public=metadata.get('is_public', True),
    )
    
    # Relacionar upload_session con song
    upload_session.song = song
    upload_session.save(update_fields=['song'])
    
    return song


def update_user_stats(user, file_size):
    """Actualiza estadísticas del usuario"""
    try:
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Incrementar contador de canciones subidas
        if hasattr(profile, 'songs_uploaded'):
            profile.songs_uploaded += 1
        
        # Actualizar timestamp de último upload
        if hasattr(profile, 'last_upload_at'):
            profile.last_upload_at = timezone.now()
        
        # Actualizar tamaño total si existe el campo
        if hasattr(profile, 'total_upload_size'):
            current_total = profile.total_upload_size or 0
            profile.total_upload_size = current_total + file_size
        
        profile.save()
        
    except Exception as e:
        logger.warning(f"Error actualizando estadísticas de usuario {user.id}: {str(e)}")


def calculate_file_checksum(file_path):
    """Calcula checksum SHA256 del archivo"""
    sha256_hash = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    
    return sha256_hash.hexdigest()


def is_transient_error(error):
    """Determina si un error es transitorio"""
    error_str = str(error).lower()
    
    transient_keywords = [
        'connection', 'timeout', 'network',
        'temporary', 'unavailable', 'busy',
        'slowdown', 'throttling', 'retry'
    ]
    
    return any(keyword in error_str for keyword in transient_keywords)


# ==================== NUEVAS TAREAS ====================

@shared_task
def reset_monthly_quotas():
    """
    Reset mensual de contadores de quotas
    Se ejecuta el día 1 de cada mes
    """
    logger.info("🔄 Iniciando reset mensual de quotas...")
    
    try:
        # Resetear contadores diarios si tienen más de 30 días
        month_ago = timezone.now() - timedelta(days=30)
        quotas_to_reset = UploadQuota.objects.filter(
            daily_uploads_reset_at__lt=month_ago
        )
        
        count = quotas_to_reset.count()
        
        for quota in quotas_to_reset:
            quota.daily_uploads_count = 0
            quota.daily_uploads_size = 0
            quota.daily_uploads_reset_at = timezone.now()
            quota.save(update_fields=[
                'daily_uploads_count', 
                'daily_uploads_size', 
                'daily_uploads_reset_at'
            ])
        
        logger.info(f"✅ Reset mensual completado: {count} quotas actualizadas")
        
        return {
            "status": "success",
            "quotas_reset": count,
            "timestamp": timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error en reset mensual de quotas: {str(e)}", exc_info=True)
        return {"error": str(e)}


@shared_task
def system_health_check():
    """
    Verificación de salud del sistema
    Monitorea R2, DB, Redis, y métricas clave
    """
    logger.info("❤️  Iniciando health check del sistema...")
    
    health_report = {
        "timestamp": timezone.now().isoformat(),
        "status": "healthy",
        "checks": {},
        "metrics": {},
        "alerts": []
    }
    
    try:
        # 1. CHECK: Base de datos
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            health_report["checks"]["database"] = {
                "status": "healthy",
                "response_time_ms": 0
            }
    except Exception as e:
        health_report["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_report["status"] = "degraded"
        health_report["alerts"].append(f"❌ Database error: {str(e)}")
    
    try:
        # 2. CHECK: Cache Redis
        from django.core.cache import cache
        
        cache.set("health_check_test", "ok", 10)
        test_value = cache.get("health_check_test")
        
        health_report["checks"]["cache"] = {
            "status": "healthy" if test_value == "ok" else "unhealthy",
            "test_value": test_value
        }
        
        if test_value != "ok":
            health_report["status"] = "degraded"
            health_report["alerts"].append("⚠️ Cache Redis test failed")
            
    except Exception as e:
        health_report["checks"]["cache"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_report["status"] = "degraded"
        health_report["alerts"].append(f"❌ Cache error: {str(e)}")
    
    try:
        # 3. CHECK: R2 Connection
        from .r2_utils import check_file_exists
        
        # Prueba simple con un path que no debería existir
        test_key = "health_check_test_nonexistent_" + str(int(timezone.now().timestamp()))
        exists = check_file_exists(test_key)
        
        health_report["checks"]["r2"] = {
            "status": "healthy",
            "connection_test": True,
            "test_key_should_not_exist": not exists
        }
        
    except Exception as e:
        health_report["checks"]["r2"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_report["status"] = "degraded"
        health_report["alerts"].append(f"❌ R2 error: {str(e)}")
    
    # 4. MÉTRICAS: Uploads pendientes
    try:
        pending_count = UploadSession.objects.filter(
            status__in=['pending', 'uploaded']
        ).count()
        
        expired_count = UploadSession.objects.filter(
            status='expired'
        ).count()
        
        failed_last_hour = UploadSession.objects.filter(
            status='failed',
            updated_at__gte=timezone.now() - timezone.timedelta(hours=1)
        ).count()
        
        health_report["metrics"]["uploads"] = {
            "pending": pending_count,
            "expired": expired_count,
            "failed_last_hour": failed_last_hour
        }
        
        # ALERTAS basadas en métricas
        if pending_count > 50:
            health_report["alerts"].append(f"⚠️ Many pending uploads: {pending_count}")
            health_report["status"] = "warning"
        
        if failed_last_hour > 10:
            health_report["alerts"].append(f"🚨 High failure rate: {failed_last_hour} failed in last hour")
            health_report["status"] = "warning"
            
    except Exception as e:
        health_report["metrics"]["uploads"] = {"error": str(e)}
        health_report["alerts"].append(f"⚠️ Error collecting upload metrics: {str(e)}")
    
    # 5. MÉTRICAS: Uso de quotas
    try:
        quota_stats = UploadQuota.objects.aggregate(
            total_users=Count('id'),
            high_usage=Count('id', filter=Q(daily_uploads_count__gte=F('max_daily_uploads') * 0.8)),
            storage_near_limit=Count('id', filter=Q(total_uploads_size__gte=F('max_total_storage') * 0.9))
        )
        
        health_report["metrics"]["quotas"] = {
            "total_users": quota_stats["total_users"] or 0,
            "users_near_daily_limit": quota_stats["high_usage"] or 0,
            "users_near_storage_limit": quota_stats["storage_near_limit"] or 0
        }
        
        if quota_stats["storage_near_limit"]:
            health_report["alerts"].append(f"⚠️ {quota_stats['storage_near_limit']} users near storage limit")
            
    except Exception as e:
        health_report["metrics"]["quotas"] = {"error": str(e)}
    
    # Log del reporte completo
    logger.info(f"❤️  Health check completed: {health_report['status']}")
    
    # Si hay alertas, log them
    if health_report["alerts"]:
        for alert in health_report["alerts"]:
            logger.warning(f"HEALTH ALERT: {alert}")
    
    return health_report