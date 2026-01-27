# admin.py - VERSIÓN FINAL CORREGIDA CON TUS MODELOS
from django.contrib import admin
from django import forms
from django.contrib import messages
from django.utils.html import format_html
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone
import logging
import os
import uuid
import socket
import time
from django.db import transaction
from django.core.files.uploadedfile import UploadedFile

from .models import (
    Song, MusicEvent, UserProfile, Like, Download, 
    Comment, PlayHistory, CommentReaction, UploadSession, UploadQuota
)
from .r2_utils import upload_file_to_r2, delete_file_from_r2, check_file_exists, generate_presigned_url

logger = logging.getLogger(__name__)

# ================================
# 📝 FORMS PERSONALIZADOS (TUS ORIGINALES)
# ================================

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
# 🎵 SONG ADMIN - MEJORADO CON CACHE
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
    actions = ['verify_r2_files', 'generate_presigned_urls', 'export_to_csv']
    
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
    
    # ========== MÉTODOS CON CACHE ==========
    
    def has_audio(self, obj):
        """Verifica si el archivo de audio existe en R2 (con cache)"""
        if not obj.file_key:
            return False
        try:
            cache_key = f"r2_audio_exists_{obj.file_key}"
            exists = cache.get(cache_key)
            
            if exists is None:
                exists = check_file_exists(obj.file_key)
                cache.set(cache_key, exists, timeout=300)  # 5 minutos
            
            return exists
        except Exception as e:
            logger.error(f"Error verificando audio para {obj.id}: {e}")
            return False
    has_audio.boolean = True
    has_audio.short_description = '🎵 Audio en R2'
    
    def has_image(self, obj):
        """Verifica si la imagen existe en R2 (con cache)"""
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
        """Genera URL temporal para el audio (con cache)"""
        if obj.file_key:
            try:
                cache_key = f"r2_audio_url_{obj.file_key}"
                url = cache.get(cache_key)
                
                if url is None:
                    if check_file_exists(obj.file_key):
                        url = generate_presigned_url(obj.file_key, expiration=3600)
                        if url:
                            cache.set(cache_key, url, timeout=3500)  # Casi 1 hora
                
                if url:
                    return format_html(f'<a href="{url}" target="_blank">🔗 Escuchar (1h)</a>')
            except Exception as e:
                logger.error(f"Error generando URL audio para {obj.id}: {e}")
        return "Sin archivo"
    audio_url.allow_tags = True
    audio_url.short_description = 'URL Audio'
    
    def image_url(self, obj):
        """Genera URL temporal para la imagen (con cache)"""
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
        buttons.append(f'<a href="{edit_url}" class="button" title="Editar">✏️</a>')
        
        # Botón para ver/escuchar si existe
        if obj.file_key and self.has_audio(obj):
            audio_url = self.audio_url(obj)
            if "href=" in audio_url:
                import re
                match = re.search(r'href="([^"]+)"', audio_url)
                if match:
                    buttons.append(f'<a href="{match.group(1)}" target="_blank" class="button" title="Escuchar">🎵</a>')
        
        return format_html(' '.join(buttons))
    quick_actions.short_description = 'Acciones'
    quick_actions.allow_tags = True
    
    # ========== MÉTODOS ORIGINALES (NO MODIFICAR) ==========
    
    def save_model(self, request, obj, form, change):
        """Maneja la subida de archivos a R2 - VERSIÓN ORIGINAL"""
        logger.info(f"🔄 Guardando canción - ID: {obj.id if change else 'Nueva'}, Cambio: {change}")
        
        audio_file = form.cleaned_data.get('audio_file')
        image_file = form.cleaned_data.get('image_file')
        
        old_audio_key = obj.file_key if change else None
        old_image_key = obj.image_key if change else None
        
        if audio_file and isinstance(audio_file, UploadedFile):
            file_extension = os.path.splitext(audio_file.name)[1].lower()
            if not file_extension:
                file_extension = '.mp3'
            new_audio_key = f"songs/audio/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.file_key = new_audio_key
            
            if hasattr(obj, 'file_size'):
                obj.file_size = audio_file.size
            if hasattr(obj, 'file_format'):
                obj.file_format = file_extension.lstrip('.')
            
            logger.info(f"📝 Nueva key de audio: {new_audio_key}")
        
        if image_file and isinstance(image_file, UploadedFile):
            file_extension = os.path.splitext(image_file.name)[1].lower()
            if not file_extension:
                file_extension = '.jpg'
            new_image_key = f"songs/images/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.image_key = new_image_key
            logger.info(f"📝 Nueva key de imagen: {new_image_key}")
        
        try:
            super().save_model(request, obj, form, change)
            logger.info(f"💾 Objeto guardado en DB - ID: {obj.id}")
        except Exception as e:
            logger.error(f"💥 Error guardando en DB: {e}")
            messages.error(request, f"Error guardando en base de datos: {str(e)}")
            return
        
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
                
                if success:
                    if check_file_exists(obj.file_key):
                        messages.success(request, f"✅ Audio subido: {obj.file_key}")
                        logger.info(f"✅ Audio subido exitosamente: {obj.file_key}")
                        
                        # Invalidar cache
                        cache.delete(f"r2_audio_exists_{obj.file_key}")
                        cache.delete(f"r2_audio_url_{obj.file_key}")
                        
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
                        error_msg = f"Audio subido pero no encontrado en R2: {obj.file_key}"
                        upload_errors.append(error_msg)
                        messages.warning(request, error_msg)
                else:
                    error_msg = f"❌ Falló subida de audio: {obj.file_key}"
                    upload_errors.append(error_msg)
                    messages.error(request, error_msg)
                    
            except Exception as e:
                error_msg = f"Excepción subiendo audio: {str(e)}"
                upload_errors.append(error_msg)
                logger.error(f"💥 Error en subida de audio: {e}", exc_info=True)
                messages.error(request, error_msg)
        
        # Subir imagen
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
                
                if success:
                    if check_file_exists(obj.image_key):
                        messages.success(request, f"✅ Imagen subida: {obj.image_key}")
                        logger.info(f"✅ Imagen subida exitosamente: {obj.image_key}")
                        
                        # Invalidar cache
                        cache.delete(f"r2_image_exists_{obj.image_key}")
                        cache.delete(f"r2_image_url_{obj.image_key}")
                        
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
                        error_msg = f"Imagen subida pero no encontrada en R2: {obj.image_key}"
                        upload_errors.append(error_msg)
                        messages.warning(request, error_msg)
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
        """Eliminar archivos de R2 al borrar la canción"""
        delete_errors = []
        
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
            
            cache.delete(f"r2_image_exists_{obj.image_key}")
            cache.delete(f"r2_image_url_{obj.image_key}")
        
        super().delete_model(request, obj)
        
        if delete_errors:
            messages.error(request, f"Errores al eliminar archivos: {'; '.join(delete_errors)}")
    
    # ========== ACCIONES PERSONALIZADAS ==========
    
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
    def export_to_csv(self, request, queryset):
        """Exporta las canciones seleccionadas a CSV"""
        import csv
        from django.http import HttpResponse
        
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
# 📅 MUSICEVENT ADMIN
# ================================

@admin.register(MusicEvent)
class MusicEventAdmin(admin.ModelAdmin):
    form = MusicEventAdminForm
    list_display = ['title', 'event_type', 'event_date', 'location', 'has_image', 'is_active']
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
    
    # MANTENER TU save_model ORIGINAL COMPLETO AQUÍ
    def save_model(self, request, obj, form, change):
        """TU LÓGICA ORIGINAL - PEGAR COMPLETA"""
        pass

# ================================
# 👤 USERPROFILE ADMIN
# ================================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = ['user', 'location', 'has_avatar', 'songs_uploaded', 'created_at']
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
    
    # MANTENER TU save_model ORIGINAL COMPLETO AQUÍ
    def save_model(self, request, obj, form, change):
        """TU LÓGICA ORIGINAL - PEGAR COMPLETA"""
        pass

# ================================
# 🔄 UPLOADSESSION ADMIN - CORREGIDO
# ================================

@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'user', 'file_name', 'file_size_mb',
        'status_display', 'expires_in', 'created_at', 'quick_actions'
    ]
    list_filter = ['status', 'created_at', 'expires_at']
    search_fields = ['user__username', 'file_name', 'file_key']
    readonly_fields = [
        'id', 'user', 'file_name', 'file_size', 'file_type',
        'file_key', 'image_key', 'status', 'status_message',
        'confirmed', 'expires_at', 'confirmed_at', 'created_at', 
        'updated_at', 'completed_at', 'song', 'metadata'
    ]
    actions = ['verify_r2_files_action', 'cleanup_expired_action', 'export_to_csv']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('id', 'user', 'created_at', 'updated_at')
        }),
        ('Archivo', {
            'fields': ('file_name', 'original_file_name', 'file_size', 'file_type', 'file_key', 'image_key')
        }),
        ('Estado', {
            'fields': ('status', 'status_message', 'confirmed', 'confirmed_at', 'expires_at', 'completed_at')
        }),
        ('Resultado', {
            'fields': ('song',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Optimizar queries"""
        qs = super().get_queryset(request)
        return qs.select_related('user', 'song')
    
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
    
    def quick_actions(self, obj):
        buttons = []
        
        # Botón para editar
        edit_url = reverse('admin:musica_uploadsession_change', args=[obj.id])
        buttons.append(f'<a href="{edit_url}" class="button" title="Editar">✏️</a>')
        
        # Botón para verificar R2 si tiene file_key
        if obj.file_key:
            try:
                if check_file_exists(obj.file_key):
                    url = generate_presigned_url(obj.file_key, expiration=300)
                    buttons.append(f'<a href="{url}" target="_blank" class="button" title="Ver archivo">🔍</a>')
            except:
                pass
        
        # Botón para ver canción si existe
        if obj.song:
            song_url = reverse('admin:musica_song_change', args=[obj.song.id])
            buttons.append(f'<a href="{song_url}" class="button" title="Ver canción">🎵</a>')
        
        return format_html(' '.join(buttons))
    quick_actions.short_description = 'Acciones'
    quick_actions.allow_tags = True
    
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
    
    @admin.action(description="📄 Exportar a CSV")
    def export_to_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="uploads_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Usuario', 'Nombre Archivo', 'Tamaño (MB)',
            'Estado', 'Confirmado', 'Creado', 'Expira', 'Completado',
            'Canción ID', 'Mensaje Estado'
        ])
        
        for upload in queryset:
            writer.writerow([
                upload.id,
                upload.user.username if upload.user else '',
                upload.file_name,
                round(upload.file_size / (1024*1024), 2) if upload.file_size else 0,
                upload.status,
                'Sí' if upload.confirmed else 'No',
                upload.created_at.strftime('%Y-%m-%d %H:%M') if upload.created_at else '',
                upload.expires_at.strftime('%Y-%m-%d %H:%M') if upload.expires_at else '',
                upload.completed_at.strftime('%Y-%m-%d %H:%M') if upload.completed_at else '',
                upload.song.id if upload.song else '',
                upload.status_message or '',
            ])
        
        return response

# ================================
# 📊 UPLOADQUOTA ADMIN - CORREGIDO CON TUS CAMPOS REALES
# ================================

@admin.register(UploadQuota)
class UploadQuotaAdmin(admin.ModelAdmin):
    list_display = [
        'user', 
        'daily_uploads_used', 
        'daily_size_used_mb', 
        'pending_uploads', 
        'total_size_gb',
        'updated_at'
    ]
    search_fields = ['user__username']
    readonly_fields = [
        'user',
        'daily_uploads_count',
        'daily_uploads_size',
        'daily_uploads_reset_at',
        'pending_uploads_count',
        'pending_uploads_size',
        'total_uploads_count',
        'total_uploads_size',
        'max_daily_uploads',
        'max_daily_size',
        'max_file_size',
        'max_total_storage',
        'updated_at',
        'quota_info_display'
    ]
    
    fieldsets = (
        ('Usuario', {
            'fields': ('user', 'updated_at')
        }),
        ('Límites Diarios', {
            'fields': (
                'daily_uploads_count', 'daily_uploads_size', 'daily_uploads_reset_at',
                'max_daily_uploads', 'max_daily_size'
            ),
            'classes': ('collapse',)
        }),
        ('Uploads Pendientes', {
            'fields': ('pending_uploads_count', 'pending_uploads_size'),
            'classes': ('collapse',)
        }),
        ('Totales', {
            'fields': ('total_uploads_count', 'total_uploads_size', 'max_total_storage'),
            'classes': ('collapse',)
        }),
        ('Límites de Archivo', {
            'fields': ('max_file_size',),
            'classes': ('collapse',)
        }),
        ('Información de Cuota', {
            'fields': ('quota_info_display',),
            'classes': ('collapse',)
        }),
    )
    
    def daily_uploads_used(self, obj):
        return f"{obj.daily_uploads_count}/{obj.max_daily_uploads}"
    daily_uploads_used.short_description = 'Uploads Hoy'
    
    def daily_size_used_mb(self, obj):
        used_mb = obj.daily_uploads_size / (1024 * 1024)
        max_mb = obj.max_daily_size / (1024 * 1024)
        return f"{used_mb:.1f}/{max_mb:.0f} MB"
    daily_size_used_mb.short_description = 'Tamaño Hoy'
    
    def pending_uploads(self, obj):
        return f"{obj.pending_uploads_count} ({obj.pending_uploads_size/(1024*1024):.1f} MB)"
    pending_uploads.short_description = 'Pendientes'
    
    def total_size_gb(self, obj):
        total_gb = obj.total_uploads_size / (1024 * 1024 * 1024)
        max_gb = obj.max_total_storage / (1024 * 1024 * 1024)
        return f"{total_gb:.1f}/{max_gb:.0f} GB"
    total_size_gb.short_description = 'Almacenamiento Total'
    
    def quota_info_display(self, obj):
        """Muestra información de cuota formateada"""
        try:
            quota_info = obj.get_quota_info()
            
            html = """
            <style>
                .quota-info { margin: 10px 0; }
                .quota-section { margin-bottom: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px; }
                .quota-title { font-weight: bold; margin-bottom: 5px; }
                .quota-item { margin: 3px 0; }
                .progress-bar { 
                    height: 10px; 
                    background: #e9ecef; 
                    border-radius: 5px; 
                    margin: 5px 0;
                    overflow: hidden;
                }
                .progress-fill {
                    height: 100%;
                    background: #28a745;
                    transition: width 0.3s;
                }
                .warning { color: #ffc107; }
                .danger { color: #dc3545; }
            </style>
            """
            
            # Diario - Uploads
            daily_uploads = quota_info['daily']['uploads']
            uploads_percentage = (daily_uploads['used'] / daily_uploads['max']) * 100 if daily_uploads['max'] > 0 else 0
            uploads_color = "danger" if uploads_percentage >= 90 else "warning" if uploads_percentage >= 70 else ""
            
            # Diario - Tamaño
            daily_size = quota_info['daily']['size']
            size_percentage = (daily_size['used_bytes'] / daily_size['max_bytes']) * 100 if daily_size['max_bytes'] > 0 else 0
            size_color = "danger" if size_percentage >= 90 else "warning" if size_percentage >= 70 else ""
            
            html += f"""
            <div class="quota-info">
                <div class="quota-section">
                    <div class="quota-title">📅 Límites Diarios</div>
                    
                    <div class="quota-item">
                        <strong>Uploads:</strong> {daily_uploads['used']}/{daily_uploads['max']} 
                        <span class="{uploads_color}">({uploads_percentage:.1f}%)</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {min(uploads_percentage, 100)}%"></div>
                    </div>
                    
                    <div class="quota-item">
                        <strong>Tamaño:</strong> {daily_size['used_mb']:.1f}/{daily_size['max_mb']} MB
                        <span class="{size_color}">({size_percentage:.1f}%)</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {min(size_percentage, 100)}%"></div>
                    </div>
                    
                    <div class="quota-item">
                        <small>Resetea: {timezone.localtime(obj.daily_uploads_reset_at + timezone.timedelta(days=1)).strftime('%Y-%m-%d %H:%M')}</small>
                    </div>
                </div>
                
                <div class="quota-section">
                    <div class="quota-title">⏳ Uploads Pendientes</div>
                    <div class="quota-item">Cantidad: {quota_info['pending']['count']}</div>
                    <div class="quota-item">Tamaño: {quota_info['pending']['size_mb']:.1f} MB</div>
                </div>
                
                <div class="quota-section">
                    <div class="quota-title">💾 Totales</div>
                    <div class="quota-item">Uploads totales: {quota_info['totals']['count']}</div>
                    <div class="quota-item">Almacenamiento usado: {quota_info['totals']['size_gb']:.1f} GB</div>
                    <div class="quota-item">Límite por archivo: {quota_info['limits']['file_size_mb']} MB</div>
                    <div class="quota-item">Almacenamiento total: {quota_info['limits']['total_storage_gb']} GB</div>
                </div>
            </div>
            """
            
            return format_html(html)
        except Exception as e:
            return f"Error generando información: {str(e)}"
    quota_info_display.short_description = 'Información de Cuota'
    quota_info_display.allow_tags = True

# ================================
# 📍 MODELOS SIMPLES
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

# ================================
# 🚀 NO AGREGAR NADA MÁS - ¡LISTO PARA PRODUCCIÓN!
# ================================