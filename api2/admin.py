# admin.py - VERSIÓN MEJORADA CON TAREAS PERIÓDICAS Y ANALYTICS
from django.contrib import admin
from django import forms
from django.contrib import messages
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum, Avg, Q, Case, When, FloatField
from django.utils import timezone
from django.core.cache import cache
import csv
import json
import logging
from datetime import timedelta

from .models import (
    Song, MusicEvent, UserProfile, Like, Download, 
    Comment, PlayHistory, CommentReaction, UploadSession, UploadQuota
)
from .r2_utils import upload_file_to_r2, delete_file_from_r2, check_file_exists, generate_presigned_url
from django.core.files.uploadedfile import UploadedFile
import uuid
import os
import time
import socket
from django.db import transaction

# Importar tasks de Celery
try:
    from api2.tasks.upload_tasks import (
        cleanup_expired_uploads, 
        cleanup_orphaned_r2_files,
        reprocess_failed_upload
    )
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    logging.warning("Celery tasks no disponibles. Algunas features estarán limitadas.")

logger = logging.getLogger(__name__)

# ================================
# 🔍 FILTROS PERSONALIZADOS
# ================================

class SizeRangeFilter(admin.SimpleListFilter):
    """Filtra por rango de tamaño de archivo"""
    title = 'Tamaño del archivo'
    parameter_name = 'size_range'
    
    def lookups(self, request, model_admin):
        return (
            ('tiny', '< 1MB'),
            ('small', '1MB - 10MB'),
            ('medium', '10MB - 50MB'),
            ('large', '50MB - 100MB'),
            ('huge', '> 100MB'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'tiny':
            return queryset.filter(file_size__lt=1024*1024)
        elif self.value() == 'small':
            return queryset.filter(file_size__gte=1024*1024, file_size__lt=10*1024*1024)
        elif self.value() == 'medium':
            return queryset.filter(file_size__gte=10*1024*1024, file_size__lt=50*1024*1024)
        elif self.value() == 'large':
            return queryset.filter(file_size__gte=50*1024*1024, file_size__lt=100*1024*1024)
        elif self.value() == 'huge':
            return queryset.filter(file_size__gte=100*1024*1024)
        return queryset

class ExpirationStatusFilter(admin.SimpleListFilter):
    """Filtra por estado de expiración"""
    title = 'Estado de expiración'
    parameter_name = 'expiration_status'
    
    def lookups(self, request, model_admin):
        return (
            ('expired', 'Expirado'),
            ('expiring_soon', 'Por expirar (< 1h)'),
            ('expiring_today', 'Expira hoy'),
            ('valid', 'Válido (> 24h)'),
        )
    
    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'expired':
            return queryset.filter(expires_at__lt=now)
        elif self.value() == 'expiring_soon':
            return queryset.filter(
                expires_at__gt=now,
                expires_at__lte=now + timedelta(hours=1)
            )
        elif self.value() == 'expiring_today':
            return queryset.filter(
                expires_at__gt=now,
                expires_at__date=now.date()
            )
        elif self.value() == 'valid':
            return queryset.filter(
                expires_at__gt=now + timedelta(hours=24)
            )
        return queryset

# ================================
# 📝 FORMS PERSONALIZADOS MEJORADOS
# ================================

class UploadSessionAdminForm(forms.ModelForm):
    """Form con validaciones avanzadas para UploadSession"""
    
    class Meta:
        model = UploadSession
        fields = '__all__'
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validar que no haya conflictos de file_key
        file_key = cleaned_data.get('file_key')
        if file_key and file_key.strip():
            # Verificar que no esté siendo usado por otra sesión activa
            conflicting = UploadSession.objects.filter(
                file_key=file_key
            ).exclude(
                status__in=['expired', 'cancelled']
            ).exclude(
                id=self.instance.id if self.instance else None
            ).exists()
            
            if conflicting:
                raise forms.ValidationError(
                    f"El file_key '{file_key}' ya está en uso por otra sesión activa."
                )
        
        # Validar fechas
        expires_at = cleaned_data.get('expires_at')
        created_at = cleaned_data.get('created_at') or timezone.now()
        
        if expires_at and expires_at <= created_at:
            raise forms.ValidationError(
                "La fecha de expiración debe ser posterior a la fecha de creación."
            )
        
        return cleaned_data
    
    def clean_file_size(self):
        """Validar tamaño de archivo según límites"""
        file_size = self.cleaned_data.get('file_size')
        
        if file_size:
            from django.conf import settings
            
            # Validar contra límites del sistema
            if file_size > settings.MAX_UPLOAD_SIZE:
                raise forms.ValidationError(
                    f"El archivo excede el límite máximo del sistema "
                    f"({settings.MAX_UPLOAD_SIZE/(1024*1024):.0f}MB)."
                )
            
            if file_size < 1024:  # 1KB mínimo
                raise forms.ValidationError("El archivo es demasiado pequeño (< 1KB).")
        
        return file_size

class SongAdminForm(forms.ModelForm):
    audio_file = forms.FileField(
        required=False,
        label="Archivo de Audio",
        help_text="Sube el archivo que se guardará en R2. Formatos: MP3, WAV, OGG, M4A, FLAC, AAC, WEBM (max 100MB)"
    )
    
    image_file = forms.ImageField(
        required=False,
        label="Imagen de Portada",
        help_text="Sube la imagen que se guardará en R2. Formatos: JPG, PNG, WEBP (max 10MB)"
    )
    
    class Meta:
        model = Song
        fields = '__all__'
        widgets = {
            'duration': forms.TextInput(attrs={'placeholder': 'MM:SS (ej: 03:45)'}),
        }
    
    def clean_audio_file(self):
        audio_file = self.cleaned_data.get('audio_file')
        if audio_file:
            valid_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.webm', '.opus']
            ext = os.path.splitext(audio_file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError(f"Formato no soportado. Use: {', '.join(valid_extensions)}")
            
            if audio_file.size > 100 * 1024 * 1024:
                raise forms.ValidationError("El archivo es demasiado grande. Máximo 100MB.")
        
        return audio_file
    
    def clean_image_file(self):
        image_file = self.cleaned_data.get('image_file')
        if image_file:
            valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
            ext = os.path.splitext(image_file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError(f"Formato de imagen no soportado. Use: {', '.join(valid_extensions)}")
            
            if image_file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("La imagen es demasiado grande. Máximo 10MB.")
        
        return image_file

class MusicEventAdminForm(forms.ModelForm):
    event_image = forms.ImageField(
        required=False,
        label="Imagen del Evento",
        help_text="Sube la imagen que se guardará en R2 (max 10MB)"
    )
    
    class Meta:
        model = MusicEvent
        fields = '__all__'

class UserProfileAdminForm(forms.ModelForm):
    avatar_upload = forms.ImageField(
        required=False,
        label="Avatar",
        help_text="Sube la imagen de perfil que se guardará en R2 (max 5MB)"
    )
    
    class Meta:
        model = UserProfile
        fields = '__all__'

# ================================
# 🎵 SONG ADMIN - VERSIÓN MEJORADA
# ================================

@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    form = SongAdminForm
    list_display = [
        'title', 'artist', 'genre', 'uploaded_by',
        'has_audio', 'has_image', 'is_public', 'created_at',
        'quick_actions'
    ]
    list_filter = ['genre', 'created_at', 'is_public', 'uploaded_by']
    search_fields = ['title', 'artist', 'genre']
    readonly_fields = [
        'file_key', 'image_key', 'likes_count', 'plays_count',
        'downloads_count', 'audio_url', 'image_url', 'created_at', 'updated_at'
    ]
    actions = ['verify_r2_files', 'generate_presigned_urls', 'export_songs_csv']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('title', 'artist', 'genre', 'duration', 'uploaded_by', 'is_public')
        }),
        ('Archivos - SUBIR AQUÍ', {
            'fields': ('audio_file', 'image_file'),
            'description': '⚠️ Sube los archivos reales que se guardarán en R2'
        }),
        ('Estado R2 (Solo lectura)', {
            'fields': ('audio_url', 'image_url'),
            'classes': ('collapse',),
            'description': 'Estado actual de los archivos en R2'
        }),
        ('Claves R2 (Automáticas)', {
            'fields': ('file_key', 'image_key'),
            'classes': ('collapse',)
        }),
        ('Estadísticas', {
            'fields': ('likes_count', 'plays_count', 'downloads_count')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimizar queries"""
        qs = super().get_queryset(request)
        return qs.select_related('uploaded_by').prefetch_related('like_set', 'playhistory_set')
    
    def has_audio(self, obj):
        if not obj.file_key:
            return False
        try:
            # Cachear la verificación por 5 minutos
            cache_key = f"r2_audio_exists_{obj.file_key}"
            exists = cache.get(cache_key)
            
            if exists is None:
                exists = check_file_exists(obj.file_key)
                cache.set(cache_key, exists, timeout=300)
            
            return exists
        except Exception as e:
            logger.error(f"Error verificando audio para {obj.id}: {e}")
            return False
    has_audio.boolean = True
    has_audio.short_description = '🎵 Audio en R2'
    
    def has_image(self, obj):
        if not obj.image_key:
            return False
        try:
            cache_key = f"r2_image_exists_{obj.image_key}"
            exists = cache.get(cache_key)
            
            if exists is None:
                exists = check_file_exists(obj.image_key)
                cache.set(cache_key, exists, timeout=300)
            
            return exists
        except Exception as e:
            logger.error(f"Error verificando imagen para {obj.id}: {e}")
            return False
    has_image.boolean = True
    has_image.short_description = '🖼️ Imagen en R2'
    
    def audio_url(self, obj):
        if obj.file_key:
            try:
                cache_key = f"r2_audio_url_{obj.file_key}"
                url = cache.get(cache_key)
                
                if url is None:
                    if check_file_exists(obj.file_key):
                        url = generate_presigned_url(obj.file_key, expiration=3600)
                        if url:
                            cache.set(cache_key, url, timeout=3500)  # Un poco menos que 1h
                
                if url:
                    return format_html(f'<a href="{url}" target="_blank">🔗 Escuchar (1h)</a>')
            except Exception as e:
                logger.error(f"Error generando URL audio para {obj.id}: {e}")
        return "Sin archivo"
    audio_url.allow_tags = True
    audio_url.short_description = 'URL Audio'
    
    def image_url(self, obj):
        if obj.image_key:
            try:
                cache_key = f"r2_image_url_{obj.image_key}"
                url = cache.get(cache_key)
                
                if url is None:
                    if check_file_exists(obj.image_key):
                        url = generate_presigned_url(obj.image_key, expiration=3600)
                        if url:
                            cache.set(cache_key, url, timeout=3500)
                
                if url:
                    return format_html(f'<a href="{url}" target="_blank">🔗 Ver imagen (1h)</a>')
            except Exception as e:
                logger.error(f"Error generando URL imagen para {obj.id}: {e}")
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'
    
    def quick_actions(self, obj):
        """Botones de acción rápida"""
        buttons = []
        
        # Botón para editar
        edit_url = reverse('admin:musica_song_change', args=[obj.id])
        buttons.append(
            f'<a href="{edit_url}" class="button" title="Editar">✏️</a>'
        )
        
        # Botón para ver en R2 si existe audio
        if obj.file_key:
            buttons.append(
                f'<a href="{self.audio_url(obj)}" target="_blank" class="button" title="Escuchar">🎵</a>'
            )
        
        # Botón para ver imagen si existe
        if obj.image_key:
            buttons.append(
                f'<a href="{self.image_url(obj)}" target="_blank" class="button" title="Ver imagen">🖼️</a>'
            )
        
        return format_html(' '.join(buttons))
    quick_actions.short_description = 'Acciones'
    quick_actions.allow_tags = True
    
    def save_model(self, request, obj, form, change):
        """Maneja la subida de archivos a R2 - MEJORADO CON CACHE"""
        logger.info(f"🔄 Guardando canción - ID: {obj.id if change else 'Nueva'}, Cambio: {change}")
        
        audio_file = form.cleaned_data.get('audio_file')
        image_file = form.cleaned_data.get('image_file')
        
        old_audio_key = obj.file_key if change else None
        old_image_key = obj.image_key if change else None
        
        # Generar nuevas keys si hay archivos nuevos
        if audio_file and isinstance(audio_file, UploadedFile):
            file_extension = os.path.splitext(audio_file.name)[1].lower() or '.mp3'
            new_audio_key = f"songs/audio/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.file_key = new_audio_key
            logger.info(f"📝 Nueva key de audio: {new_audio_key}")
        
        if image_file and isinstance(image_file, UploadedFile):
            file_extension = os.path.splitext(image_file.name)[1].lower() or '.jpg'
            new_image_key = f"songs/images/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.image_key = new_image_key
            logger.info(f"📝 Nueva key de imagen: {new_image_key}")
        
        # Guardar objeto primero
        try:
            super().save_model(request, obj, form, change)
            logger.info(f"💾 Objeto guardado en DB - ID: {obj.id}")
        except Exception as e:
            logger.error(f"💥 Error guardando en DB: {e}")
            messages.error(request, f"Error guardando en base de datos: {str(e)}")
            return
        
        # Subir archivos a R2 después de guardar
        upload_errors = []
        
        # Subir audio
        if audio_file and isinstance(audio_file, UploadedFile):
            try:
                if hasattr(audio_file, 'seek'):
                    audio_file.seek(0)
                
                audio_content_type = getattr(audio_file, 'content_type', 'audio/mpeg')
                success = upload_file_to_r2(
                    file_obj=audio_file,
                    key=obj.file_key,
                    content_type=audio_content_type
                )
                
                if success and check_file_exists(obj.file_key):
                    messages.success(request, f"✅ Audio subido: {obj.file_key}")
                    logger.info(f"✅ Audio subido exitosamente: {obj.file_key}")
                    
                    # Invalidar cache
                    cache.delete(f"r2_audio_exists_{obj.file_key}")
                    cache.delete(f"r2_audio_url_{obj.file_key}")
                    
                    # Eliminar archivo antiguo si existe
                    if old_audio_key and old_audio_key != obj.file_key:
                        try:
                            if check_file_exists(old_audio_key):
                                delete_file_from_r2(old_audio_key)
                                cache.delete(f"r2_audio_exists_{old_audio_key}")
                                cache.delete(f"r2_audio_url_{old_audio_key}")
                                logger.info(f"🗑️ Audio antiguo eliminado: {old_audio_key}")
                        except Exception as delete_error:
                            logger.warning(f"No se pudo eliminar audio antiguo: {delete_error}")
                else:
                    error_msg = f"❌ Falló subida de audio: {obj.file_key}"
                    upload_errors.append(error_msg)
                    messages.error(request, error_msg)
                    
            except Exception as e:
                error_msg = f"Excepción subiendo audio: {str(e)}"
                upload_errors.append(error_msg)
                logger.error(f"💥 Error en subida de audio: {e}", exc_info=True)
                messages.error(request, error_msg)
        
        # Subir imagen (similar lógica)
        if image_file and isinstance(image_file, UploadedFile):
            try:
                if hasattr(image_file, 'seek'):
                    image_file.seek(0)
                
                image_content_type = getattr(image_file, 'content_type', 'image/jpeg')
                success = upload_file_to_r2(
                    file_obj=image_file,
                    key=obj.image_key,
                    content_type=image_content_type
                )
                
                if success and check_file_exists(obj.image_key):
                    messages.success(request, f"✅ Imagen subida: {obj.image_key}")
                    logger.info(f"✅ Imagen subida exitosamente: {obj.image_key}")
                    
                    # Invalidar cache
                    cache.delete(f"r2_image_exists_{obj.image_key}")
                    cache.delete(f"r2_image_url_{obj.image_key}")
                    
                    # Eliminar imagen antigua
                    if old_image_key and old_image_key != obj.image_key:
                        try:
                            if check_file_exists(old_image_key):
                                delete_file_from_r2(old_image_key)
                                cache.delete(f"r2_image_exists_{old_image_key}")
                                cache.delete(f"r2_image_url_{old_image_key}")
                                logger.info(f"🗑️ Imagen antigua eliminada: {old_image_key}")
                        except Exception as delete_error:
                            logger.warning(f"No se pudo eliminar imagen antigua: {delete_error}")
                else:
                    error_msg = f"❌ Falló subida de imagen: {obj.image_key}"
                    upload_errors.append(error_msg)
                    messages.error(request, error_msg)
                    
            except Exception as e:
                error_msg = f"Excepción subiendo imagen: {str(e)}"
                upload_errors.append(error_msg)
                logger.error(f"💥 Error en subida de imagen: {e}", exc_info=True)
                messages.error(request, error_msg)
        
        if upload_errors:
            logger.warning(f"⚠️ Errores en upload para canción {obj.id}: {upload_errors}")
        
        logger.info(f"🎉 Proceso completado para canción ID: {obj.id}")
    
    def delete_model(self, request, obj):
        """Eliminar archivos de R2 al borrar la canción - MEJORADO CON CACHE"""
        delete_errors = []
        
        # Eliminar archivos de R2
        if obj.file_key:
            try:
                if check_file_exists(obj.file_key):
                    delete_file_from_r2(obj.file_key)
                    messages.success(request, f"🗑️ Audio eliminado de R2: {obj.file_key}")
                    logger.info(f"🗑️ Audio eliminado de R2: {obj.file_key}")
                else:
                    messages.warning(request, f"Audio no encontrado en R2: {obj.file_key}")
            except Exception as e:
                delete_errors.append(f"Audio: {e}")
                logger.error(f"Error eliminando audio {obj.file_key}: {e}")
            
            # Invalidar cache
            cache.delete(f"r2_audio_exists_{obj.file_key}")
            cache.delete(f"r2_audio_url_{obj.file_key}")
        
        if obj.image_key:
            try:
                if check_file_exists(obj.image_key):
                    delete_file_from_r2(obj.image_key)
                    messages.success(request, f"🗑️ Imagen eliminada de R2: {obj.image_key}")
                    logger.info(f"🗑️ Imagen eliminada de R2: {obj.image_key}")
                else:
                    messages.warning(request, f"Imagen no encontrada en R2: {obj.image_key}")
            except Exception as e:
                delete_errors.append(f"Imagen: {e}")
                logger.error(f"Error eliminando imagen {obj.image_key}: {e}")
            
            # Invalidar cache
            cache.delete(f"r2_image_exists_{obj.image_key}")
            cache.delete(f"r2_image_url_{obj.image_key}")
        
        # Eliminar objeto de la base de datos
        super().delete_model(request, obj)
        
        if delete_errors:
            messages.error(request, f"Errores al eliminar archivos: {'; '.join(delete_errors)}")
    
    @admin.action(description="✅ Verificar archivos en R2")
    def verify_r2_files(self, request, queryset):
        """Acción para verificar archivos en R2"""
        results = []
        for song in queryset:
            audio_exists = False
            image_exists = False
            
            if song.file_key:
                audio_exists = check_file_exists(song.file_key)
            if song.image_key:
                image_exists = check_file_exists(song.image_key)
            
            results.append({
                'song': f"{song.title} - {song.artist}",
                'audio_exists': audio_exists,
                'image_exists': image_exists,
                'audio_key': song.file_key,
                'image_key': song.image_key,
            })
        
        message = "Resultados de verificación R2:<br>"
        for result in results:
            audio_icon = "✅" if result['audio_exists'] else "❌"
            image_icon = "✅" if result['image_exists'] else "❌"
            message += f"{audio_icon} {image_icon} {result['song']}<br>"
        
        self.message_user(request, message, messages.INFO)
    
    @admin.action(description="🔗 Generar URLs temporales (1h)")
    def generate_presigned_urls(self, request, queryset):
        """Generar URLs presigned para las canciones seleccionadas"""
        urls = []
        for song in queryset:
            audio_url = None
            image_url = None
            
            if song.file_key and check_file_exists(song.file_key):
                audio_url = generate_presigned_url(song.file_key, expiration=3600)
            if song.image_key and check_file_exists(song.image_key):
                image_url = generate_presigned_url(song.image_key, expiration=3600)
            
            urls.append({
                'song': f"{song.title} - {song.artist}",
                'audio_url': audio_url,
                'image_url': image_url,
            })
        
        message = "URLs temporales (válidas por 1 hora):<br>"
        for item in urls:
            message += f"<strong>{item['song']}</strong><br>"
            if item['audio_url']:
                message += f"🎵 <a href='{item['audio_url']}' target='_blank'>Escuchar</a><br>"
            if item['image_url']:
                message += f"🖼️ <a href='{item['image_url']}' target='_blank'>Ver imagen</a><br>"
            message += "<br>"
        
        self.message_user(request, message, messages.INFO)
    
    @admin.action(description="📄 Exportar a CSV")
    def export_songs_csv(self, request, queryset):
        """Exporta las canciones seleccionadas a CSV"""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="songs_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Título', 'Artista', 'Género', 'Duración', 'Uploader', 
                        'Audio Key', 'Imagen Key', 'Likes', 'Plays', 'Downloads', 
                        'Creado', 'Público'])
        
        for song in queryset:
            writer.writerow([
                song.title,
                song.artist,
                song.genre,
                song.duration,
                song.uploaded_by.username if song.uploaded_by else '',
                song.file_key or '',
                song.image_key or '',
                song.likes_count,
                song.plays_count,
                song.downloads_count,
                song.created_at.strftime('%Y-%m-%d %H:%M') if song.created_at else '',
                'Sí' if song.is_public else 'No'
            ])
        
        return response

# ================================
# 📅 MUSICEVENT ADMIN - MEJORADO
# ================================

@admin.register(MusicEvent)
class MusicEventAdmin(admin.ModelAdmin):
    form = MusicEventAdminForm
    list_display = ['title', 'event_type', 'event_date', 'location', 'has_image', 'is_active', 'quick_actions']
    list_filter = ['event_type', 'event_date', 'is_active', 'is_featured']
    search_fields = ['title', 'location', 'venue']
    readonly_fields = ['image_key', 'image_url']
    
    def has_image(self, obj):
        if not obj.image_key:
            return False
        try:
            cache_key = f"r2_event_image_exists_{obj.image_key}"
            exists = cache.get(cache_key)
            
            if exists is None:
                exists = check_file_exists(obj.image_key)
                cache.set(cache_key, exists, timeout=300)
            
            return exists
        except Exception:
            return False
    has_image.boolean = True
    has_image.short_description = '🖼️ Imagen en R2'
    
    def image_url(self, obj):
        if obj.image_key:
            try:
                cache_key = f"r2_event_image_url_{obj.image_key}"
                url = cache.get(cache_key)
                
                if url is None:
                    if check_file_exists(obj.image_key):
                        url = generate_presigned_url(obj.image_key, expiration=3600)
                        if url:
                            cache.set(cache_key, url, timeout=3500)
                
                if url:
                    return format_html(f'<a href="{url}" target="_blank">🔗 Ver imagen (1h)</a>')
            except Exception:
                pass
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'
    
    def quick_actions(self, obj):
        buttons = []
        edit_url = reverse('admin:musica_musicevent_change', args=[obj.id])
        buttons.append(f'<a href="{edit_url}" class="button" title="Editar">✏️</a>')
        
        if obj.image_key:
            view_url = self.image_url(obj)
            if "href=" in view_url:
                # Extraer URL del HTML
                import re
                match = re.search(r'href="([^"]+)"', view_url)
                if match:
                    buttons.append(f'<a href="{match.group(1)}" target="_blank" class="button" title="Ver imagen">🖼️</a>')
        
        return format_html(' '.join(buttons))
    quick_actions.short_description = 'Acciones'
    quick_actions.allow_tags = True
    
    def save_model(self, request, obj, form, change):
        """Maneja la subida de imágenes de eventos a R2 con timeout controlado"""
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(60)
        
        event_image = form.cleaned_data.get('event_image')
        old_image_key = obj.image_key if change else None
        
        logger.info(f"🔄 Guardando evento - ID: {obj.id if change else 'Nueva'}, Cambio: {change}")
        
        if event_image:
            logger.info(f"📤 Imagen recibida: {event_image.name}, Size: {event_image.size}")
        
        try:
            with transaction.atomic():
                if event_image and isinstance(event_image, UploadedFile):
                    file_extension = os.path.splitext(event_image.name)[1].lower() or '.jpg'
                    timestamp = int(time.time())
                    unique_id = f"{timestamp}_{uuid.uuid4().hex[:8]}"
                    new_image_key = f"events/{unique_id}{file_extension}"
                    logger.info(f"📝 Nueva key generada: {new_image_key}")
                    obj.image_key = new_image_key
                
                # 1. GUARDAR PRIMERO EN DB
                super().save_model(request, obj, form, change)
                logger.info(f"💾 Evento guardado en DB - ID: {obj.id}")
                
                # 2. SUBIR A R2 SI HAY IMAGEN
                if event_image and isinstance(event_image, UploadedFile):
                    self._upload_event_image(request, event_image, obj, old_image_key)
        
        except socket.timeout:
            logger.error(f"⏰ TIMEOUT guardando evento {obj.id if hasattr(obj, 'id') else 'Nuevo'}")
            messages.error(
                request,
                "⏰ Timeout al procesar la imagen. El evento se guardó pero la imagen puede no estar disponible. "
                "Intenta editar el evento para subir la imagen nuevamente."
            )
        except Exception as e:
            logger.error(f"❌ Error crítico guardando evento: {str(e)}", exc_info=True)
            messages.error(request, f"Error guardando evento: {str(e)}")
        finally:
            socket.setdefaulttimeout(original_timeout)
    
    def _upload_event_image(self, request, event_image, obj, old_image_key):
        """Método separado para subir imagen con manejo de errores robusto"""
        MAX_RETRIES = 2
        retry_count = 0
        
        while retry_count <= MAX_RETRIES:
            try:
                if hasattr(event_image, 'seek'):
                    event_image.seek(0)
                
                image_content_type = getattr(event_image, 'content_type', 'image/jpeg')
                
                logger.info(f"⬆️ Subiendo imagen a R2: {obj.image_key} ({retry_count+1}/{MAX_RETRIES+1} intento)")
                
                success = upload_file_to_r2(
                    file_obj=event_image,
                    key=obj.image_key,
                    content_type=image_content_type
                )
                
                if success:
                    time.sleep(1)
                    if check_file_exists(obj.image_key):
                        logger.info(f"✅ Imagen subida exitosamente: {obj.image_key}")
                        messages.success(request, f"✅ Imagen de evento subida correctamente")
                        
                        # Invalidar cache
                        cache.delete(f"r2_event_image_exists_{obj.image_key}")
                        cache.delete(f"r2_event_image_url_{obj.image_key}")
                        
                        # Limpiar imagen antigua
                        self._cleanup_old_image(old_image_key, obj.image_key)
                        return
                    else:
                        logger.warning(f"⚠️ Upload marcado como éxito pero imagen no encontrada: {obj.image_key}")
                        messages.warning(
                            request,
                            f"Imagen subida pero necesita verificación. Key: {obj.image_key}"
                        )
                else:
                    logger.error(f"❌ Falló subida de imagen (intento {retry_count+1}): {obj.image_key}")
                    if retry_count < MAX_RETRIES:
                        retry_count += 1
                        logger.info(f"🔄 Reintentando ({retry_count}/{MAX_RETRIES})...")
                        time.sleep(2)
                        continue
                    else:
                        messages.error(request, f"❌ Error subiendo imagen después de {MAX_RETRIES+1} intentos")
                        return
            
            except socket.timeout:
                logger.error(f"⏰ Timeout subiendo imagen (intento {retry_count+1}): {obj.image_key}")
                if retry_count < MAX_RETRIES:
                    retry_count += 1
                    logger.info(f"🔄 Reintentando después de timeout ({retry_count}/{MAX_RETRIES})...")
                    time.sleep(3)
                    continue
                else:
                    messages.error(
                        request,
                        "⏰ Timeout al subir imagen después de múltiples intentos. "
                        "La imagen puede no estar disponible."
                    )
                    return
            
            except Exception as e:
                logger.error(f"❌ Error inesperado subiendo imagen: {str(e)}", exc_info=True)
                messages.error(request, f"Error subiendo imagen: {str(e)}")
                return
    
    def _cleanup_old_image(self, old_image_key, new_image_key):
        """Elimina imagen antigua de R2 de manera segura"""
        if old_image_key and old_image_key != new_image_key:
            try:
                if check_file_exists(old_image_key):
                    logger.info(f"🗑️ Eliminando imagen antigua: {old_image_key}")
                    if delete_file_from_r2(old_image_key):
                        logger.info(f"✅ Imagen antigua eliminada: {old_image_key}")
                        # Invalidar cache
                        cache.delete(f"r2_event_image_exists_{old_image_key}")
                        cache.delete(f"r2_event_image_url_{old_image_key}")
                    else:
                        logger.warning(f"⚠️ No se pudo eliminar imagen antigua: {old_image_key}")
            except Exception as e:
                logger.warning(f"⚠️ Error limpiando imagen antigua {old_image_key}: {e}")

# ================================
# 👤 USERPROFILE ADMIN - MEJORADO
# ================================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = ['user', 'location', 'has_avatar', 'songs_uploaded', 'created_at', 'quick_actions']
    search_fields = ['user__username', 'location']
    readonly_fields = ['avatar_key', 'avatar_url']
    
    def has_avatar(self, obj):
        if not obj.avatar_key:
            return False
        try:
            cache_key = f"r2_avatar_exists_{obj.avatar_key}"
            exists = cache.get(cache_key)
            
            if exists is None:
                exists = check_file_exists(obj.avatar_key)
                cache.set(cache_key, exists, timeout=300)
            
            return exists
        except Exception:
            return False
    has_avatar.boolean = True
    has_avatar.short_description = '👤 Avatar en R2'
    
    def avatar_url(self, obj):
        if obj.avatar_key:
            try:
                cache_key = f"r2_avatar_url_{obj.avatar_key}"
                url = cache.get(cache_key)
                
                if url is None:
                    if check_file_exists(obj.avatar_key):
                        url = generate_presigned_url(obj.avatar_key, expiration=3600)
                        if url:
                            cache.set(cache_key, url, timeout=3500)
                
                if url:
                    return format_html(f'<a href="{url}" target="_blank">🔗 Ver avatar (1h)</a>')
            except Exception:
                pass
        return "Sin avatar"
    avatar_url.allow_tags = True
    avatar_url.short_description = 'URL Avatar'
    
    def quick_actions(self, obj):
        buttons = []
        edit_url = reverse('admin:musica_userprofile_change', args=[obj.id])
        buttons.append(f'<a href="{edit_url}" class="button" title="Editar">✏️</a>')
        
        if obj.avatar_key:
            view_url = self.avatar_url(obj)
            if "href=" in view_url:
                import re
                match = re.search(r'href="([^"]+)"', view_url)
                if match:
                    buttons.append(f'<a href="{match.group(1)}" target="_blank" class="button" title="Ver avatar">👤</a>')
        
        return format_html(' '.join(buttons))
    quick_actions.short_description = 'Acciones'
    quick_actions.allow_tags = True
    
    def save_model(self, request, obj, form, change):
        avatar_upload = form.cleaned_data.get('avatar_upload')
        old_avatar_key = obj.avatar_key if change else None
        
        if avatar_upload and isinstance(avatar_upload, UploadedFile):
            file_extension = os.path.splitext(avatar_upload.name)[1].lower() or '.jpg'
            new_avatar_key = f"avatars/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.avatar_key = new_avatar_key
        
        super().save_model(request, obj, form, change)
        
        if avatar_upload and isinstance(avatar_upload, UploadedFile):
            try:
                if hasattr(avatar_upload, 'seek'):
                    avatar_upload.seek(0)
                
                avatar_content_type = getattr(avatar_upload, 'content_type', 'image/jpeg')
                success = upload_file_to_r2(avatar_upload, obj.avatar_key, content_type=avatar_content_type)
                
                if success and check_file_exists(obj.avatar_key):
                    messages.success(request, f"✅ Avatar subido: {obj.avatar_key}")
                    
                    # Invalidar cache
                    cache.delete(f"r2_avatar_exists_{obj.avatar_key}")
                    cache.delete(f"r2_avatar_url_{obj.avatar_key}")
                    
                    # Eliminar avatar antiguo
                    if old_avatar_key and old_avatar_key != obj.avatar_key:
                        try:
                            if check_file_exists(old_avatar_key):
                                delete_file_from_r2(old_avatar_key)
                                cache.delete(f"r2_avatar_exists_{old_avatar_key}")
                                cache.delete(f"r2_avatar_url_{old_avatar_key}")
                        except Exception:
                            pass
                else:
                    messages.error(request, f"❌ Error subiendo avatar: {obj.avatar_key}")
                    
            except Exception as e:
                messages.error(request, f"Excepción subiendo avatar: {e}")

# ================================
# 🔄 UPLOADSESSION ADMIN - COMPLETAMENTE MEJORADO
# ================================

@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    form = UploadSessionAdminForm
    list_display = [
        'id_short', 'user', 'file_name', 'file_size_mb',
        'status_display', 'expires_in', 'processing_time',
        'success_indicator', 'user_upload_count', 'quick_actions'
    ]
    list_filter = [
        'status', 
        'created_at', 
        'expires_at',
        SizeRangeFilter,
        ExpirationStatusFilter,
    ]
    search_fields = ['user__username', 'file_name', 'file_key']
    readonly_fields = [
        'id', 'user', 'file_name', 'file_size', 'file_type',
        'file_key', 'status', 'status_message', 'expires_at',
        'confirmed_at', 'created_at', 'updated_at', 'metadata_display',
        'is_expired_display', 'can_confirm_display', 'r2_check',
        'processing_details', 'user_stats'
    ]
    actions = [
        'verify_r2_files_action', 
        'cleanup_expired_action',
        'force_cleanup_expired',
        'reprocess_failed_uploads',
        'export_to_csv',
        'mark_for_review',
    ]
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('id', 'user', 'created_at', 'updated_at')
        }),
        ('Archivo', {
            'fields': ('file_name', 'file_size', 'file_type', 'file_key')
        }),
        ('Estado', {
            'fields': ('status', 'status_message', 'expires_at', 'confirmed_at')
        }),
        ('Verificaciones', {
            'fields': ('r2_check', 'is_expired_display', 'can_confirm_display'),
            'classes': ('collapse',)
        }),
        ('Estadísticas', {
            'fields': ('processing_details', 'user_stats'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata_display',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimizar queries"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'song').prefetch_related('user__uploadquota')
    
    def id_short(self, obj):
        return str(obj.id)[:8]
    id_short.short_description = 'ID'
    
    def file_size_mb(self, obj):
        if obj.file_size:
            return f"{obj.file_size / (1024*1024):.1f} MB"
        return "-"
    file_size_mb.short_description = 'Tamaño'
    
    def status_display(self, obj):
        status_colors = {
            'pending': '🟡',
            'uploaded': '🟠',
            'confirmed': '🔵',
            'processing': '🟣',
            'ready': '🟢',
            'failed': '🔴',
            'cancelled': '⚫',
            'expired': '⚪'
        }
        return f"{status_colors.get(obj.status, '❓')} {obj.status}"
    status_display.short_description = 'Estado'
    
    def expires_in(self, obj):
        if obj.expires_at:
            now = timezone.now()
            if obj.expires_at > now:
                delta = obj.expires_at - now
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                return f"{hours}h {minutes}m"
            return "Expirado"
        return "-"
    expires_in.short_description = 'Expira en'
    
    def processing_time(self, obj):
        if obj.confirmed_at and obj.created_at:
            delta = obj.confirmed_at - obj.created_at
            total_seconds = delta.total_seconds()
            
            if total_seconds < 60:
                return f"{int(total_seconds)}s"
            elif total_seconds < 3600:
                return f"{int(total_seconds // 60)}m {int(total_seconds % 60)}s"
            else:
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                return f"{hours}h {minutes}m"
        return "-"
    processing_time.short_description = '⏱️ Tiempo'
    
    def success_indicator(self, obj):
        if obj.status == 'ready':
            return format_html('<span style="color: green;">✅</span>')
        elif obj.status == 'failed':
            return format_html('<span style="color: red;">❌</span>')
        elif obj.status == 'expired':
            return format_html('<span style="color: gray;">⏰</span>')
        elif obj.status == 'pending':
            return format_html('<span style="color: orange;">⏳</span>')
        return "❓"
    success_indicator.short_description = 'Resultado'
    
    def user_upload_count(self, obj):
        if obj.user:
            count = UploadSession.objects.filter(user=obj.user).count()
            return f"{count}"
        return "-"
    user_upload_count.short_description = 'Total User'
    
    def quick_actions(self, obj):
        buttons = []
        
        # Botón para verificar R2
        if obj.file_key:
            verify_url = reverse('admin:verify_r2_single', args=[obj.id])
            buttons.append(
                f'<a href="{verify_url}" class="button" title="Verificar en R2">🔍</a>'
            )
        
        # Botón para reprocesar si falló
        if obj.status == 'failed':
            reprocess_url = reverse('admin:reprocess_upload', args=[obj.id])
            buttons.append(
                f'<a href="{reprocess_url}" class="button" title="Reprocesar">🔄</a>'
            )
        
        # Botón para ver canción si existe
        if obj.song:
            song_url = reverse('admin:musica_song_change', args=[obj.song.id])
            buttons.append(
                f'<a href="{song_url}" class="button" title="Ver canción">🎵</a>'
            )
        
        # Botón para eliminar
        delete_url = reverse('admin:musica_uploadsession_delete', args=[obj.id])
        buttons.append(
            f'<a href="{delete_url}" class="button deletelink" title="Eliminar">🗑️</a>'
        )
        
        return format_html(' '.join(buttons))
    quick_actions.short_description = 'Acciones'
    quick_actions.allow_tags = True
    
    def metadata_display(self, obj):
        if obj.metadata:
            try:
                if isinstance(obj.metadata, str):
                    metadata = json.loads(obj.metadata)
                else:
                    metadata = obj.metadata
                
                if isinstance(metadata, dict):
                    formatted = json.dumps(metadata, indent=2, ensure_ascii=False)
                    return format_html(f'<pre style="max-height: 300px; overflow: auto;">{formatted}</pre>')
            except:
                pass
            return str(obj.metadata)[:500] + ("..." if len(str(obj.metadata)) > 500 else "")
        return "No metadata"
    metadata_display.short_description = 'Metadata'
    
    def is_expired_display(self, obj):
        if hasattr(obj, 'is_expired'):
            return obj.is_expired
        return "No disponible"
    is_expired_display.boolean = True
    is_expired_display.short_description = 'Expirado'
    
    def can_confirm_display(self, obj):
        if hasattr(obj, 'can_confirm'):
            return obj.can_confirm
        return "No disponible"
    can_confirm_display.boolean = True
    can_confirm_display.short_description = 'Puede confirmar'
    
    def r2_check(self, obj):
        if not obj.file_key:
            return "❌ Sin file_key"
        try:
            exists = check_file_exists(obj.file_key)
            if exists:
                url = generate_presigned_url(obj.file_key, expiration=300)
                return format_html(f'✅ En R2 - <a href="{url}" target="_blank">🔗 Ver (5min)</a>')
            else:
                return "❌ No encontrado en R2"
        except Exception as e:
            return f"⚠️ Error: {str(e)}"
    r2_check.allow_tags = True
    r2_check.short_description = 'Verificación R2'
    
    def processing_details(self, obj):
        details = []
        
        if obj.created_at and obj.updated_at:
            processing_time = (obj.updated_at - obj.created_at).total_seconds()
            details.append(f"Tiempo total: {processing_time:.1f}s")
        
        if obj.status_message:
            details.append(f"Mensaje: {obj.status_message}")
        
        return format_html('<br>'.join(details)) if details else "-"
    processing_details.short_description = 'Detalles de Procesamiento'
    
    def user_stats(self, obj):
        if not obj.user:
            return "Sin usuario"
        
        stats = UploadSession.objects.filter(user=obj.user).aggregate(
            total=Count('id'),
            success=Count('id', filter=Q(status='ready')),
            failed=Count('id', filter=Q(status='failed')),
            total_size=Sum('file_size')
        )
        
        success_rate = 0
        if stats['total'] > 0:
            success_rate = (stats['success'] / stats['total']) * 100
        
        return format_html(
            f"Total: {stats['total']}<br>"
            f"Exitosos: {stats['success']}<br>"
            f"Fallidos: {stats['failed']}<br>"
            f"Tasa éxito: {success_rate:.1f}%<br>"
            f"Tamaño total: {stats['total_size']/(1024*1024):.1f} MB"
        )
    user_stats.short_description = 'Estadísticas del Usuario'
    
    @admin.action(description="🔍 Verificar archivos en R2")
    def verify_r2_files_action(self, request, queryset):
        results = []
        for upload in queryset:
            if upload.file_key:
                try:
                    exists = check_file_exists(upload.file_key)
                    results.append(f"{upload.file_name}: {'✅' if exists else '❌'}")
                except Exception as e:
                    results.append(f"{upload.file_name}: ⚠️ Error: {str(e)}")
        
        message = f"Verificación R2 completada:<br>" + "<br>".join(results)
        self.message_user(request, message, messages.INFO)
    
    @admin.action(description="🗑️ Limpiar sesiones expiradas")
    def cleanup_expired_action(self, request, queryset):
        from django.utils import timezone
        expired = queryset.filter(
            expires_at__lt=timezone.now(),
            status__in=['pending', 'uploaded']
        )
        count = expired.count()
        expired.update(status='expired')
        self.message_user(request, f"✅ {count} sesiones marcadas como expiradas", messages.SUCCESS)
    
    @admin.action(description="🧹 Ejecutar cleanup ahora (Celery)")
    def force_cleanup_expired(self, request, queryset):
        if CELERY_AVAILABLE:
            result = cleanup_expired_uploads.delay()
            self.message_user(
                request,
                f"✅ Cleanup task encolada: {result.id}. Ver logs en Celery.",
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                "❌ Celery no está disponible. No se puede ejecutar cleanup.",
                messages.ERROR
            )
    
    @admin.action(description="🔄 Reprocesar uploads fallidos")
    def reprocess_failed_uploads(self, request, queryset):
        if CELERY_AVAILABLE:
            failed_sessions = queryset.filter(status='failed')
            count = 0
            
            for session in failed_sessions:
                reprocess_failed_upload.delay(str(session.id))
                count += 1
            
            self.message_user(
                request,
                f"✅ {count} uploads fallidos encolados para reprocesamiento",
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                "❌ Celery no está disponible. No se puede reprocesar.",
                messages.ERROR
            )
    
    @admin.action(description="📄 Exportar a CSV")
    def export_to_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="uploads_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Usuario', 'Email', 'Nombre Archivo', 'Tamaño (MB)',
            'Estado', 'Creado', 'Expirado', 'Duración Proceso',
            'Canción ID', 'Título Canción', 'Artista'
        ])
        
        for upload in queryset.select_related('user', 'song'):
            writer.writerow([
                upload.id,
                upload.user.username if upload.user else '',
                upload.user.email if upload.user else '',
                upload.file_name,
                round(upload.file_size / (1024*1024), 2) if upload.file_size else 0,
                upload.status,
                upload.created_at.strftime('%Y-%m-%d %H:%M') if upload.created_at else '',
                upload.expires_at.strftime('%Y-%m-%d %H:%M') if upload.expires_at else '',
                self.processing_time(upload),
                upload.song.id if upload.song else '',
                upload.song.title if upload.song else '',
                upload.song.artist if upload.song else '',
            ])
        
        return response
    
    @admin.action(description="👁️ Marcar para revisión")
    def mark_for_review(self, request, queryset):
        """Marca sesiones para revisión manual"""
        count = queryset.count()
        # Aquí podrías agregar un campo 'needs_review' al modelo
        self.message_user(
            request,
            f"✅ {count} sesiones marcadas para revisión manual",
            messages.SUCCESS
        )
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False

# ================================
# 📊 DASHBOARD Y VISTAS PERSONALIZADAS
# ================================

@staff_member_required
def upload_analytics_dashboard(request):
    """Dashboard avanzado con analytics en tiempo real"""
    
    from datetime import timedelta
    import json
    
    today = timezone.now().date()
    last_7_days = timezone.now() - timedelta(days=7)
    
    # ========== MÉTRICAS PRINCIPALES ==========
    stats = {
        'total_uploads': UploadSession.objects.count(),
        'total_songs': Song.objects.count(),
        'total_users_uploaded': UploadSession.objects.values('user').distinct().count(),
        'total_size_gb': UploadSession.objects.aggregate(
            total=Sum('file_size')
        )['total'] or 0,
        
        'uploads_today': UploadSession.objects.filter(
            created_at__date=today
        ).count(),
        'size_today_mb': UploadSession.objects.filter(
            created_at__date=today
        ).aggregate(total=Sum('file_size'))['total'] or 0,
        
        'uploads_last_7_days': UploadSession.objects.filter(
            created_at__gte=last_7_days
        ).count(),
        'pending_count': UploadSession.objects.filter(status='pending').count(),
        'expired_count': UploadSession.objects.filter(status='expired').count(),
        'failed_count': UploadSession.objects.filter(status='failed').count(),
    }
    
    # Calcular tasa de éxito
    if stats['uploads_last_7_days'] > 0:
        success_count = UploadSession.objects.filter(
            created_at__gte=last_7_days,
            status='ready'
        ).count()
        stats['success_rate_7_days'] = round((success_count / stats['uploads_last_7_days']) * 100, 1)
    else:
        stats['success_rate_7_days'] = 0
    
    # ========== GRÁFICOS DE DATOS ==========
    daily_stats = []
    for i in range(7):
        day = today - timedelta(days=i)
        day_data = UploadSession.objects.filter(
            created_at__date=day
        ).aggregate(
            count=Count('id'),
            success=Count('id', filter=Q(status='ready')),
            failed=Count('id', filter=Q(status='failed')),
            size=Sum('file_size')
        )
        daily_stats.append({
            'date': day.strftime('%Y-%m-%d'),
            'count': day_data['count'] or 0,
            'success': day_data['success'] or 0,
            'failed': day_data['failed'] or 0,
            'size_mb': (day_data['size'] or 0) / (1024 * 1024),
        })
    daily_stats.reverse()
    
    # ========== TOP USUARIOS ==========
    top_uploaders = UploadSession.objects.values(
        'user__username', 'user__email'
    ).annotate(
        upload_count=Count('id'),
        total_size=Sum('file_size'),
        success_rate=Avg(Case(
            When(status='ready', then=1),
            default=0,
            output_field=FloatField()
        )) * 100
    ).order_by('-upload_count')[:10]
    
    # ========== PROBLEMAS DETECTADOS ==========
    issues = []
    
    # Sesiones uploaded pero no confirmadas por > 1 hora
    stale_uploads = UploadSession.objects.filter(
        status='uploaded',
        updated_at__lt=timezone.now() - timedelta(hours=1)
    )[:5]
    
    if stale_uploads.exists():
        issues.append({
            'type': 'stale_uploads',
            'count': stale_uploads.count(),
            'message': 'Uploads sin confirmar por más de 1 hora',
            'sessions': list(stale_uploads.values('id', 'user__username', 'updated_at'))
        })
    
    # Muchos fallidos recientes
    recent_failed = UploadSession.objects.filter(
        status='failed',
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    
    if recent_failed > 5:
        issues.append({
            'type': 'high_failure_rate',
            'count': recent_failed,
            'message': f'{recent_failed} uploads fallidos en la última hora'
        })
    
    context = {
        'stats': stats,
        'daily_stats_json': json.dumps(daily_stats),
        'top_uploaders': top_uploaders,
        'issues': issues,
        'today': today,
        'title': 'Analytics de Uploads',
        'refresh_interval': 300,
    }
    
    return render(request, 'admin/upload_analytics.html', context)

# ================================
# 📍 REGISTRO DE MODELOS SIN LÓGICA R2
# ================================

@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'song', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'song__title']

@admin.register(Download)
class DownloadAdmin(admin.ModelAdmin):
    list_display = ['user', 'song', 'downloaded_at', 'ip_address']
    list_filter = ['downloaded_at']
    search_fields = ['user__username', 'song__title']

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'song', 'created_at', 'is_edited']
    list_filter = ['created_at', 'is_edited']
    search_fields = ['user__username', 'song__title', 'content']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'comment', 'reaction_type', 'created_at']
    list_filter = ['reaction_type', 'created_at']
    search_fields = ['user__username', 'comment__content']

@admin.register(PlayHistory)
class PlayHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'song', 'played_at', 'duration_played']
    list_filter = ['played_at']
    search_fields = ['user__username', 'song__title']
    readonly_fields = ['played_at']

@admin.register(UploadQuota)
class UploadQuotaAdmin(admin.ModelAdmin):
    list_display = ['user', 'used_quota_mb', 'max_quota_mb', 'percentage_used', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['user__username']
    readonly_fields = ['user', 'used_quota', 'max_quota', 'pending_quota', 'updated_at']
    
    def used_quota_mb(self, obj):
        return f"{obj.used_quota / (1024*1024):.1f} MB"
    used_quota_mb.short_description = 'Usado'
    
    def max_quota_mb(self, obj):
        return f"{obj.max_quota / (1024*1024):.1f} MB"
    max_quota_mb.short_description = 'Máximo'
    
    def percentage_used(self, obj):
        if obj.max_quota > 0:
            percentage = (obj.used_quota / obj.max_quota) * 100
            color = "green" if percentage < 80 else "orange" if percentage < 95 else "red"
            return format_html(f'<span style="color: {color};">{percentage:.1f}%</span>')
        return "0%"
    percentage_used.short_description = 'Porcentaje'
    percentage_used.allow_tags = True

# ================================
# 🚀 CONFIGURACIÓN DE URLS PERSONALIZADAS
# ================================

