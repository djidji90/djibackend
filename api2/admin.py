# api2/admin.py - VERSIÓN CORREGIDA DEFINITIVA COMPATIBLE
from django.contrib import admin
from django import forms
from django.contrib import messages
from .models import Song, MusicEvent, UserProfile, Like, Download, Comment, PlayHistory, CommentReaction
from .r2_utils import upload_file_to_r2, delete_file_from_r2, check_file_exists, generate_presigned_url
from django.core.files.uploadedfile import UploadedFile
import uuid
from django.utils import timezone
import os
import logging
import time
import socket
from django.db import transaction

# Al inicio de imports, agrega:
from .models import UploadSession, UploadQuota  # Agregar estos

logger = logging.getLogger(__name__)

# =============================================
# FORMULARIOS PERSONALIZADOS - MEJORADOS
# =============================================

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
            # Validar extensión actualizada
            valid_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.webm', '.opus']
            ext = os.path.splitext(audio_file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError(f"Formato no soportado. Use: {', '.join(valid_extensions)}")
            
            # Validar tamaño aumentado a 100MB (como en el serializer)
            if audio_file.size > 100 * 1024 * 1024:
                raise forms.ValidationError("El archivo es demasiado grande. Máximo 100MB.")
        
        return audio_file
    
    def clean_image_file(self):
        image_file = self.cleaned_data.get('image_file')
        if image_file:
            # Validar extensión de imagen
            valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
            ext = os.path.splitext(image_file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError(f"Formato de imagen no soportado. Use: {', '.join(valid_extensions)}")
            
            # Validar tamaño aumentado a 10MB
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

# =============================================
# ADMIN PARA SONG - VERSIÓN CORREGIDA DEFINITIVA
# =============================================

@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    form = SongAdminForm
    list_display = [
        'title', 'artist', 'genre', 'uploaded_by', 
        'has_audio', 'has_image', 'is_public', 'created_at'
    ]
    list_filter = ['genre', 'created_at', 'is_public', 'uploaded_by']
    search_fields = ['title', 'artist', 'genre']
    readonly_fields = [
        'file_key', 'image_key', 'likes_count', 'plays_count', 
        'downloads_count', 'audio_url', 'image_url', 'created_at', 'updated_at'
    ]
    actions = ['verify_r2_files', 'generate_presigned_urls']

    fieldsets = (
        ('Información Básica', {
            'fields': (
                'title', 'artist', 'genre', 'duration', 
                'uploaded_by', 'is_public'
            )
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

    def has_audio(self, obj):
        """Verifica si el archivo de audio existe en R2"""
        if not obj.file_key:
            return False
        try:
            return check_file_exists(obj.file_key)
        except Exception as e:
            logger.error(f"Error verificando audio para {obj.id}: {e}")
            return False
    has_audio.boolean = True
    has_audio.short_description = '🎵 Audio en R2'

    def has_image(self, obj):
        """Verifica si la imagen existe en R2"""
        if not obj.image_key:
            return False
        try:
            return check_file_exists(obj.image_key)
        except Exception as e:
            logger.error(f"Error verificando imagen para {obj.id}: {e}")
            return False
    has_image.boolean = True
    has_image.short_description = '🖼️ Imagen en R2'

    def audio_url(self, obj):
        """Genera URL temporal para el audio"""
        if obj.file_key:
            try:
                if check_file_exists(obj.file_key):
                    url = generate_presigned_url(obj.file_key, expiration=3600)
                    return f'<a href="{url}" target="_blank">🔗 Escuchar (1h)</a>' if url else "No disponible"
            except Exception as e:
                logger.error(f"Error generando URL audio para {obj.id}: {e}")
        return "Sin archivo"
    audio_url.allow_tags = True
    audio_url.short_description = 'URL Audio'

    def image_url(self, obj):
        """Genera URL temporal para la imagen"""
        if obj.image_key:
            try:
                if check_file_exists(obj.image_key):
                    url = generate_presigned_url(obj.image_key, expiration=3600)
                    return f'<a href="{url}" target="_blank">🔗 Ver imagen (1h)</a>' if url else "No disponible"
            except Exception as e:
                logger.error(f"Error generando URL imagen para {obj.id}: {e}")
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'

    def save_model(self, request, obj, form, change):
        """
        Maneja la subida de archivos a R2 - VERSIÓN MEJORADA
        """
        logger.info(f"🔄 Guardando canción - ID: {obj.id if change else 'Nueva'}, Cambio: {change}")
        
        # Obtener archivos del formulario
        audio_file = form.cleaned_data.get('audio_file')
        image_file = form.cleaned_data.get('image_file')
        
        # Guardar keys antiguas para limpieza si es update
        old_audio_key = obj.file_key if change else None
        old_image_key = obj.image_key if change else None
        
        # ✅ GENERAR NUEVAS KEYS SI HAY ARCHIVOS NUEVOS
        if audio_file and isinstance(audio_file, UploadedFile):
            # Generar nueva key única
            file_extension = os.path.splitext(audio_file.name)[1].lower()
            if not file_extension:
                file_extension = '.mp3'
            
            new_audio_key = f"songs/audio/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.file_key = new_audio_key
            
            # Guardar metadata adicional si los campos existen
            if hasattr(obj, 'file_size'):
                obj.file_size = audio_file.size
            if hasattr(obj, 'file_format'):
                obj.file_format = file_extension.lstrip('.')
            
            logger.info(f"📝 Nueva key de audio: {new_audio_key}")
        
        if image_file and isinstance(image_file, UploadedFile):
            # Generar nueva key única
            file_extension = os.path.splitext(image_file.name)[1].lower()
            if not file_extension:
                file_extension = '.jpg'
            
            new_image_key = f"songs/images/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.image_key = new_image_key
            logger.info(f"📝 Nueva key de imagen: {new_image_key}")
        
        # ✅ GUARDAR OBJETO PRIMERO
        try:
            super().save_model(request, obj, form, change)
            logger.info(f"💾 Objeto guardado en DB - ID: {obj.id}")
        except Exception as e:
            logger.error(f"💥 Error guardando en DB: {e}")
            messages.error(request, f"Error guardando en base de datos: {str(e)}")
            return
        
        # ✅ SUBIR ARCHIVOS A R2 DESPUÉS DE GUARDAR
        upload_errors = []
        
        # Subir audio
        if audio_file and isinstance(audio_file, UploadedFile):
            try:
                # Asegurar que el archivo esté al inicio
                if hasattr(audio_file, 'seek'):
                    audio_file.seek(0)
                
                # Subir a R2
                audio_content_type = getattr(audio_file, 'content_type', 'audio/mpeg')
                success = upload_file_to_r2(
                    file_obj=audio_file,
                    key=obj.file_key,
                    content_type=audio_content_type
                )
                
                if success:
                    # Verificar que se subió correctamente
                    if check_file_exists(obj.file_key):
                        messages.success(request, f"✅ Audio subido: {obj.file_key}")
                        logger.info(f"✅ Audio subido exitosamente: {obj.file_key}")
                        
                        # Eliminar archivo antiguo si existe y es diferente
                        if old_audio_key and old_audio_key != obj.file_key:
                            try:
                                if check_file_exists(old_audio_key):
                                    delete_file_from_r2(old_audio_key)
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
                # Asegurar que el archivo esté al inicio
                if hasattr(image_file, 'seek'):
                    image_file.seek(0)
                
                # Subir a R2
                image_content_type = getattr(image_file, 'content_type', 'image/jpeg')
                success = upload_file_to_r2(
                    file_obj=image_file,
                    key=obj.image_key,
                    content_type=image_content_type
                )
                
                if success:
                    # Verificar que se subió correctamente
                    if check_file_exists(obj.image_key):
                        messages.success(request, f"✅ Imagen subida: {obj.image_key}")
                        logger.info(f"✅ Imagen subida exitosamente: {obj.image_key}")
                        
                        # Eliminar imagen antigua si existe y es diferente
                        if old_image_key and old_image_key != obj.image_key:
                            try:
                                if check_file_exists(old_image_key):
                                    delete_file_from_r2(old_image_key)
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
        
        # Si hay errores de upload, mostrar resumen
        if upload_errors:
            logger.warning(f"⚠️ Errores en upload para canción {obj.id}: {upload_errors}")
        
        logger.info(f"🎉 Proceso completado para canción ID: {obj.id}")

    def delete_model(self, request, obj):
        """
        Eliminar archivos de R2 al borrar la canción - MEJORADO
        """
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
        
        # Eliminar objeto de la base de datos
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
                'image_key': song.image_key
            })
        
        # Mostrar resultados
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
                'image_url': image_url
            })
        
        # Mostrar URLs
        message = "URLs temporales (válidas por 1 hora):<br>"
        for item in urls:
            message += f"<strong>{item['song']}</strong><br>"
            if item['audio_url']:
                message += f"🎵 <a href='{item['audio_url']}' target='_blank'>Escuchar</a><br>"
            if item['image_url']:
                message += f"🖼️ <a href='{item['image_url']}' target='_blank'>Ver imagen</a><br>"
            message += "<br>"
        
        self.message_user(request, message, messages.INFO)

# =============================================
# ADMIN PARA MUSICEVENT - CORREGIDO
# =============================================

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
            return check_file_exists(obj.image_key)
        except Exception:
            return False
    has_image.boolean = True
    has_image.short_description = '🖼️ Imagen en R2'
    
    def image_url(self, obj):
        if obj.image_key:
            try:
                if check_file_exists(obj.image_key):
                    url = generate_presigned_url(obj.image_key, expiration=3600)
                    return f'<a href="{url}" target="_blank">🔗 Ver imagen (1h)</a>' if url else "No disponible"
            except Exception:
                pass
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'
    
    def save_model(self, request, obj, form, change):
        """
        Maneja la subida de imágenes de eventos a R2 con timeout controlado
        """
        import socket
        from django.db import transaction
        
        # Configurar timeout para operaciones de red (evita timeout de Railway)
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(60)  # 60 segundos máximo
        
        event_image = form.cleaned_data.get('event_image')
        old_image_key = obj.image_key if change else None
        
        # DEBUG: Log inicial
        logger.info(f"🔄 Guardando evento - ID: {obj.id if change else 'Nueva'}, Cambio: {change}")
        
        if event_image:
            logger.info(f"📤 Imagen recibida: {event_image.name}, Size: {event_image.size}")
        
        try:
            # Usar transacción atómica
            with transaction.atomic():
                # Generar key única ANTES de guardar
                if event_image and isinstance(event_image, UploadedFile):
                    file_extension = os.path.splitext(event_image.name)[1].lower()
                    if not file_extension or file_extension not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                        file_extension = '.jpg'  # Default seguro
                    
                    # Generar nombre único con timestamp para evitar colisiones
                    import time
                    timestamp = int(time.time())
                    unique_id = f"{timestamp}_{uuid.uuid4().hex[:8]}"
                    new_image_key = f"events/{unique_id}{file_extension}"
                    
                    logger.info(f"📝 Nueva key generada: {new_image_key}")
                    obj.image_key = new_image_key
                
                # 1. GUARDAR PRIMERO EN DB
                super().save_model(request, obj, form, change)
                logger.info(f"💾 Evento guardado en DB - ID: {obj.id}")
                
                # 2. SUBIR A R2 SI HAY IMAGEN (después de guardar DB)
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
            messages.error(
                request, 
                f"Error guardando evento: {str(e)}"
            )
            
        finally:
            # Restaurar timeout original
            socket.setdefaulttimeout(original_timeout)

    def _upload_event_image(self, request, event_image, obj, old_image_key):
        """
        Método separado para subir imagen con manejo de errores robusto
        """
        MAX_RETRIES = 2
        retry_count = 0
        
        while retry_count <= MAX_RETRIES:
            try:
                # Asegurar que el archivo está al inicio
                if hasattr(event_image, 'seek'):
                    event_image.seek(0)
                
                # Obtener content_type
                image_content_type = getattr(event_image, 'content_type', 'image/jpeg')
                
                # Validar tamaño antes de subir (opcional pero recomendado)
                max_size = 10 * 1024 * 1024  # 10MB
                if hasattr(event_image, 'size') and event_image.size > max_size:
                    messages.error(request, f"❌ Imagen demasiado grande. Máximo: {max_size/(1024*1024)}MB")
                    return
                
                logger.info(f"⬆️ Subiendo imagen a R2: {obj.image_key} ({retry_count+1}/{MAX_RETRIES+1} intento)")
                
                # Subir a R2 con timeout específico
                success = upload_file_to_r2(
                    file_obj=event_image,
                    key=obj.image_key,
                    content_type=image_content_type
                )
                
                if success:
                    # Verificar que se subió correctamente
                    time.sleep(1)  # Pequeña pausa para que R2 procese
                    
                    if check_file_exists(obj.image_key):
                        logger.info(f"✅ Imagen subida exitosamente: {obj.image_key}")
                        messages.success(request, f"✅ Imagen de evento subida correctamente")
                        
                        # Limpiar imagen antigua si existe y es diferente
                        self._cleanup_old_image(old_image_key, obj.image_key)
                        
                        # Actualizar tamaño en DB si el campo existe
                        if hasattr(obj, 'image_size') and hasattr(event_image, 'size'):
                            obj.image_size = event_image.size
                            obj.save(update_fields=['image_size'])
                        
                        return  # Éxito, salir
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
                        time.sleep(2)  # Esperar antes de reintentar
                        continue
                    else:
                        messages.error(request, f"❌ Error subiendo imagen después de {MAX_RETRIES+1} intentos")
                        return
            
            except socket.timeout:
                logger.error(f"⏰ Timeout subiendo imagen (intento {retry_count+1}): {obj.image_key}")
                
                if retry_count < MAX_RETRIES:
                    retry_count += 1
                    logger.info(f"🔄 Reintentando después de timeout ({retry_count}/{MAX_RETRIES})...")
                    time.sleep(3)  # Esperar más después de timeout
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
        """
        Elimina imagen antigua de R2 de manera segura
        """
        if old_image_key and old_image_key != new_image_key:
            try:
                if check_file_exists(old_image_key):
                    logger.info(f"🗑️ Eliminando imagen antigua: {old_image_key}")
                    if delete_file_from_r2(old_image_key):
                        logger.info(f"✅ Imagen antigua eliminada: {old_image_key}")
                    else:
                        logger.warning(f"⚠️ No se pudo eliminar imagen antigua: {old_image_key}")
            except Exception as e:
                logger.warning(f"⚠️ Error limpiando imagen antigua {old_image_key}: {e}")
    # =============================================
    # ADMIN PARA USERPROFILE - CORREGIDO
    # =============================================

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
            return check_file_exists(obj.avatar_key)
        except Exception:
            return False
    has_avatar.boolean = True
    has_avatar.short_description = '👤 Avatar en R2'
    
    def avatar_url(self, obj):
        if obj.avatar_key:
            try:
                if check_file_exists(obj.avatar_key):
                    url = generate_presigned_url(obj.avatar_key, expiration=3600)
                    return f'<a href="{url}" target="_blank">🔗 Ver avatar (1h)</a>' if url else "No disponible"
            except Exception:
                pass
        return "Sin avatar"
    avatar_url.allow_tags = True
    avatar_url.short_description = 'URL Avatar'
    
    def save_model(self, request, obj, form, change):
        avatar_upload = form.cleaned_data.get('avatar_upload')
        old_avatar_key = obj.avatar_key if change else None
        
        # Generar key antes de guardar
        if avatar_upload and isinstance(avatar_upload, UploadedFile):
            # Generar nueva key única
            file_extension = os.path.splitext(avatar_upload.name)[1].lower()
            if not file_extension:
                file_extension = '.jpg'
            
            new_avatar_key = f"avatars/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.avatar_key = new_avatar_key
        
        super().save_model(request, obj, form, change)
        
        # Subir avatar después de guardar
        if avatar_upload and isinstance(avatar_upload, UploadedFile):
            try:
                # Asegurar seek(0)
                if hasattr(avatar_upload, 'seek'):
                    avatar_upload.seek(0)
                
                # Usar content_type correctamente
                avatar_content_type = getattr(avatar_upload, 'content_type', 'image/jpeg')
                success = upload_file_to_r2(avatar_upload, obj.avatar_key, content_type=avatar_content_type)
                
                if success and check_file_exists(obj.avatar_key):
                    messages.success(request, f"✅ Avatar subido: {obj.avatar_key}")
                    
                    # Eliminar avatar antiguo si existe
                    if old_avatar_key and old_avatar_key != obj.avatar_key:
                        try:
                            if check_file_exists(old_avatar_key):
                                delete_file_from_r2(old_avatar_key)
                        except Exception:
                            pass
                else:
                    messages.error(request, f"❌ Error subiendo avatar: {obj.avatar_key}")
            except Exception as e:
                messages.error(request, f"Excepción subiendo avatar: {e}")

# =============================================
# MODELOS SIN LÓGICA DE ARCHIVOS R2 (igual)
# =============================================

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


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'user', 'file_name', 'file_size_mb', 
        'status_display', 'expires_in', 'created_at'
    ]
    list_filter = ['status', 'created_at', 'expires_at']
    search_fields = ['user__username', 'file_name', 'file_key']
    readonly_fields = [
        'id', 'user', 'file_name', 'file_size', 'file_type',
        'file_key', 'status', 'status_message', 'expires_at',
        'confirmed_at', 'created_at', 'updated_at', 'metadata_display',
        'is_expired_display', 'can_confirm_display', 'r2_check'
    ]
    actions = ['verify_r2_files_action', 'cleanup_expired_action']
    
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
        ('Metadata', {
            'fields': ('metadata_display',),
            'classes': ('collapse',)
        }),
    )

    def id_short(self, obj):
        """Muestra ID corto"""
        return str(obj.id)[:8]
    id_short.short_description = 'ID'

    def file_size_mb(self, obj):
        """Muestra tamaño en MB"""
        if obj.file_size:
            return f"{obj.file_size / (1024*1024):.1f} MB"
        return "-"
    file_size_mb.short_description = 'Tamaño'

    def status_display(self, obj):
        """Muestra estado con colores"""
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
        """Muestra tiempo hasta expiración"""
        if obj.expires_at:
            from django.utils import timezone
            now = timezone.now()
            if obj.expires_at > now:
                delta = obj.expires_at - now
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                return f"{hours}h {minutes}m"
            return "Expirado"
        return "-"
    expires_in.short_description = 'Expira en'

    def metadata_display(self, obj):
        """Muestra metadata formateada"""
        if obj.metadata:
            import json
            try:
                metadata = json.loads(obj.metadata) if isinstance(obj.metadata, str) else obj.metadata
                formatted = json.dumps(metadata, indent=2, ensure_ascii=False)
                return formatted
            except:
                return str(obj.metadata)
        return "No metadata"
    metadata_display.short_description = 'Metadata'

    def is_expired_display(self, obj):
        """Muestra si está expirado"""
        return obj.is_expired if hasattr(obj, 'is_expired') else "No disponible"
    is_expired_display.boolean = True
    is_expired_display.short_description = 'Expirado'

    def can_confirm_display(self, obj):
        """Muestra si puede confirmarse"""
        return obj.can_confirm if hasattr(obj, 'can_confirm') else "No disponible"
    can_confirm_display.boolean = True
    can_confirm_display.short_description = 'Puede confirmar'

    def r2_check(self, obj):
        """Verifica archivo en R2"""
        if not obj.file_key:
            return "❌ Sin file_key"
        
        try:
            from .r2_utils import check_file_exists
            exists = check_file_exists(obj.file_key)
            if exists:
                # Generar URL temporal
                from .r2_utils import generate_presigned_url
                url = generate_presigned_url(obj.file_key, expiration=300)  # 5 minutos
                return f'✅ En R2 - <a href="{url}" target="_blank">🔗 Ver (5min)</a>'
            else:
                return "❌ No encontrado en R2"
        except Exception as e:
            return f"⚠️ Error: {str(e)}"
    r2_check.allow_tags = True
    r2_check.short_description = 'Verificación R2'

    @admin.action(description="🔍 Verificar archivos en R2")
    def verify_r2_files_action(self, request, queryset):
        """Verifica archivos en R2 para sesiones seleccionadas"""
        results = []
        for upload in queryset:
            if upload.file_key:
                try:
                    from .r2_utils import check_file_exists
                    exists = check_file_exists(upload.file_key)
                    results.append(f"{upload.file_name}: {'✅' if exists else '❌'}")
                except Exception as e:
                    results.append(f"{upload.file_name}: ⚠️ Error: {str(e)}")
        
        message = f"Verificación R2 completada:<br>" + "<br>".join(results)
        self.message_user(request, message, messages.INFO)

    @admin.action(description="🗑️ Limpiar sesiones expiradas")
    def cleanup_expired_action(self, request, queryset):
        """Marca sesiones expiradas como expired"""
        from django.utils import timezone
        
        expired = queryset.filter(
            expires_at__lt=timezone.now(),
            status__in=['pending', 'uploaded']
        )
        
        count = expired.count()
        expired.update(status='expired')
        
        self.message_user(
            request, 
            f"✅ {count} sesiones marcadas como expiradas", 
            messages.SUCCESS
        )
    
    def has_add_permission(self, request):
        """No permitir agregar manualmente"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Solo lectura"""
        return False
    
# Crea un archivo api2/admin_dashboard.py o agrega al final de admin.py:

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Count, Sum
from .models import UploadSession, UploadQuota, Song

@staff_member_required
def upload_dashboard(request):
    """Dashboard personalizado para uploads"""
    
    # Estadísticas generales
    stats = {
        'total_uploads': UploadSession.objects.count(),
        'uploads_today': UploadSession.objects.filter(
            created_at__date=timezone.now().date()
        ).count(),
        'active_uploads': UploadSession.objects.filter(
            status__in=['pending', 'uploaded', 'processing']
        ).count(),
        'total_quota_used': UploadQuota.objects.aggregate(
            total=Sum('used_quota')
        )['total'] or 0,
    }
    
    # Uploads por estado
    status_stats = UploadSession.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status')
    
    # Top uploaders
    top_uploaders = UploadSession.objects.values(
        'user__username'
    ).annotate(
        count=Count('id'),
        total_size=Sum('file_size')
    ).order_by('-count')[:10]
    
    # Archivos recientes
    recent_uploads = UploadSession.objects.select_related(
        'user', 'song'
    ).order_by('-created_at')[:20]
    
    context = {
        'stats': stats,
        'status_stats': list(status_stats),
        'top_uploaders': list(top_uploaders),
        'recent_uploads': recent_uploads,
        'title': 'Dashboard de Uploads'
    }
    
    return render(request, 'admin/upload_dashboard.html', context)

# Luego en tu urls.py del proyecto:
# from api2.admin_dashboard import upload_dashboard
# path('admin/upload-dashboard/', upload_dashboard, name='upload_dashboard')