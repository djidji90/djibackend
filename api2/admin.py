# api2/admin.py - VERSIÓN COMPLETAMENTE CORREGIDA
from django.contrib import admin
from django import forms
from django.contrib import messages
from .models import Song, MusicEvent, UserProfile, Like, Download, Comment, PlayHistory, CommentReaction
from .r2_utils import upload_file_to_r2, delete_file_from_r2, check_file_exists, generate_presigned_url
from django.core.files.uploadedfile import UploadedFile
import uuid
import os

# =============================================
# FORMULARIOS PERSONALIZADOS
# =============================================

class SongAdminForm(forms.ModelForm):
    audio_file = forms.FileField(
        required=False,
        label="Archivo de Audio",
        help_text="Sube el archivo MP3 que se guardará en R2. Formatos: MP3, WAV, OGG"
    )
    
    image_file = forms.ImageField(
        required=False,
        label="Imagen de Portada",
        help_text="Sube la imagen que se guardará en R2. Formatos: JPG, PNG, WEBP"
    )
    
    class Meta:
        model = Song
        fields = '__all__'
    
    def clean_audio_file(self):
        audio_file = self.cleaned_data.get('audio_file')
        if audio_file:
            # Validar extensión
            valid_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac']
            ext = os.path.splitext(audio_file.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError(f"Formato no soportado. Use: {', '.join(valid_extensions)}")
            
            # Validar tamaño (50MB máximo)
            if audio_file.size > 50 * 1024 * 1024:
                raise forms.ValidationError("El archivo es demasiado grande. Máximo 50MB.")
        
        return audio_file

class MusicEventAdminForm(forms.ModelForm):
    event_image = forms.ImageField(
        required=False,
        label="Imagen del Evento",
        help_text="Sube la imagen que se guardará en R2"
    )
    
    class Meta:
        model = MusicEvent
        fields = '__all__'

class UserProfileAdminForm(forms.ModelForm):
    avatar_upload = forms.ImageField(
        required=False,
        label="Avatar",
        help_text="Sube la imagen de perfil que se guardará en R2"
    )
    
    class Meta:
        model = UserProfile
        fields = '__all__'

# =============================================
# ADMIN PARA CANCIONES - COMPLETAMENTE CORREGIDO
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
    actions = ['upload_missing_audio', 'verify_r2_files']
    
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
    
    # ========== MÉTODOS DE VISUALIZACIÓN ==========
    def has_audio(self, obj):
        """Verifica si el archivo de audio existe en R2"""
        if not obj.file_key:
            return False
        return check_file_exists(obj.file_key)
    has_audio.boolean = True
    has_audio.short_description = '🎵 Audio en R2'
    
    def has_image(self, obj):
        """Verifica si la imagen existe en R2"""
        if not obj.image_key:
            return False
        return check_file_exists(obj.image_key)
    has_image.boolean = True
    has_image.short_description = '🖼️ Imagen en R2'
    
    def audio_url(self, obj):
        """Genera URL temporal para el audio"""
        if obj.file_key and self.has_audio(obj):
            url = generate_presigned_url(obj.file_key, expiration=3600)
            return f'<a href="{url}" target="_blank">🔗 Escuchar</a>' if url else "No disponible"
        return "Sin archivo"
    audio_url.allow_tags = True
    audio_url.short_description = 'URL Audio'
    
    def image_url(self, obj):
        """Genera URL temporal para la imagen"""
        if obj.image_key and self.has_image(obj):
            url = generate_presigned_url(obj.image_key, expiration=3600)
            return f'<a href="{url}" target="_blank">🔗 Ver imagen</a>' if url else "No disponible"
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'
    
    # ========== ACCIONES ADMIN ==========
    def upload_missing_audio(self, request, queryset):
        """Acción para subir archivos faltantes a R2"""
        success_count = 0
        error_count = 0
        
        for song in queryset:
            if not self.has_audio(song) and song.file_key:
                self.message_user(
                    request, 
                    f"⚠️ {song.title}: No se puede subir automáticamente. Use el formulario de edición.",
                    messages.WARNING
                )
                error_count += 1
            elif self.has_audio(song):
                self.message_user(
                    request,
                    f"✅ {song.title}: Ya tiene audio en R2",
                    messages.SUCCESS
                )
                success_count += 1
        
        self.message_user(
            request,
            f"📊 Resumen: {success_count} verificadas, {error_count} necesitan acción manual",
            messages.INFO
        )
    upload_missing_audio.short_description = "📤 Verificar y subir archivos faltantes a R2"
    
    def verify_r2_files(self, request, queryset):
        """Verificar estado de archivos en R2"""
        for song in queryset:
            audio_status = "✅" if self.has_audio(song) else "❌"
            image_status = "✅" if self.has_image(song) else "❌"
            
            self.message_user(
                request,
                f"🎵 {song.title}: Audio={audio_status}, Imagen={image_status}",
                messages.INFO
            )
    verify_r2_files.short_description = "🔍 Verificar estado de archivos en R2"
    
    # ========== MÉTODO PRINCIPAL CORREGIDO ==========
    def save_model(self, request, obj, form, change):
        """
        Maneja la subida de archivos a R2 - VERSIÓN CORREGIDA DEFINITIVA
        """
        # Obtener archivos del formulario
        audio_file = form.cleaned_data.get('audio_file')
        image_file = form.cleaned_data.get('image_file')
        
        upload_results = {
            'audio': {'success': False, 'message': ''},
            'image': {'success': False, 'message': ''}
        }
        
        # ✅ GENERAR file_key ANTES de guardar si hay archivo de audio
        if audio_file and isinstance(audio_file, UploadedFile):
            if not obj.file_key or not change:
                # Generar nueva key única
                file_extension = audio_file.name.split('.')[-1].lower() if '.' in audio_file.name else 'mp3'
                obj.file_key = f"songs/audio/{uuid.uuid4().hex[:16]}.{file_extension}"
            
            print(f"🎵 Preparando subida de audio: {obj.file_key}")
        
        # ✅ GENERAR image_key ANTES de guardar si hay imagen
        if image_file and isinstance(image_file, UploadedFile):
            if not obj.image_key or not change:
                # Generar nueva key única
                file_extension = image_file.name.split('.')[-1].lower() if '.' in image_file.name else 'jpg'
                obj.image_key = f"songs/images/{uuid.uuid4().hex[:16]}.{file_extension}"
            
            print(f"🖼️ Preparando subida de imagen: {obj.image_key}")
        
        # ✅ GUARDAR OBJETO PRIMERO (con las keys generadas)
        super().save_model(request, obj, form, change)
        
        # ✅ SUBIR ARCHIVOS A R2 DESPUÉS de guardar el objeto
        if audio_file and isinstance(audio_file, UploadedFile):
            try:
                # Leer y subir archivo
                audio_file.open('rb')
                file_content = audio_file.read()
                audio_file.close()
                
                # Subir a R2
                success = upload_file_to_r2(audio_file, obj.file_key)
                
                if success:
                    # Verificar que realmente se subió
                    if check_file_exists(obj.file_key):
                        upload_results['audio'] = {
                            'success': True, 
                            'message': f'✅ Audio subido: {obj.file_key}'
                        }
                        messages.success(request, f"Audio subido exitosamente: {obj.file_key}")
                    else:
                        upload_results['audio'] = {
                            'success': False,
                            'message': f'❌ Audio no encontrado en R2 después de subir: {obj.file_key}'
                        }
                        messages.error(request, f"Error: Audio no aparece en R2: {obj.file_key}")
                else:
                    upload_results['audio'] = {
                        'success': False,
                        'message': f'❌ Error en upload_file_to_r2 para: {obj.file_key}'
                    }
                    messages.error(request, f"Error subiendo audio: {obj.file_key}")
                    
            except Exception as e:
                upload_results['audio'] = {
                    'success': False,
                    'message': f'💥 Excepción subiendo audio: {str(e)}'
                }
                messages.error(request, f"Excepción subiendo audio: {e}")
        
        if image_file and isinstance(image_file, UploadedFile):
            try:
                # Leer y subir imagen
                image_file.open('rb')
                file_content = image_file.read()
                image_file.close()
                
                # Subir a R2
                success = upload_file_to_r2(image_file, obj.image_key)
                
                if success:
                    # Verificar que realmente se subió
                    if check_file_exists(obj.image_key):
                        upload_results['image'] = {
                            'success': True,
                            'message': f'✅ Imagen subida: {obj.image_key}'
                        }
                        messages.success(request, f"Imagen subida exitosamente: {obj.image_key}")
                    else:
                        upload_results['image'] = {
                            'success': False,
                            'message': f'❌ Imagen no encontrada en R2 después de subir: {obj.image_key}'
                        }
                        messages.error(request, f"Error: Imagen no aparece en R2: {obj.image_key}")
                else:
                    upload_results['image'] = {
                        'success': False,
                        'message': f'❌ Error en upload_file_to_r2 para: {obj.image_key}'
                    }
                    messages.error(request, f"Error subiendo imagen: {obj.image_key}")
                    
            except Exception as e:
                upload_results['image'] = {
                    'success': False,
                    'message': f'💥 Excepción subiendo imagen: {str(e)}'
                }
                messages.error(request, f"Excepción subiendo imagen: {e}")
        
        # Resumen final en consola
        print("\n" + "="*50)
        print("📊 RESUMEN DE SUBIDAS A R2:")
        print(f"🎵 Audio: {upload_results['audio']['message']}")
        print(f"🖼️ Imagen: {upload_results['image']['message']}")
        print("="*50)
    
    def delete_model(self, request, obj):
        """
        Eliminar archivos de R2 al borrar la canción
        """
        deleted_files = []
        
        # Eliminar audio de R2
        if obj.file_key and check_file_exists(obj.file_key):
            if delete_file_from_r2(obj.file_key):
                deleted_files.append(f"audio:{obj.file_key}")
                messages.success(request, f"Audio eliminado de R2: {obj.file_key}")
            else:
                messages.error(request, f"Error eliminando audio de R2: {obj.file_key}")
        
        # Eliminar imagen de R2
        if obj.image_key and check_file_exists(obj.image_key):
            if delete_file_from_r2(obj.image_key):
                deleted_files.append(f"imagen:{obj.image_key}")
                messages.success(request, f"Imagen eliminada de R2: {obj.image_key}")
            else:
                messages.error(request, f"Error eliminando imagen de R2: {obj.image_key}")
        
        # Eliminar objeto de la base de datos
        super().delete_model(request, obj)
        
        if deleted_files:
            print(f"🗑️ Archivos eliminados de R2: {', '.join(deleted_files)}")

# =============================================
# ADMIN PARA EVENTOS MUSICALES (CORREGIDO)
# =============================================

@admin.register(MusicEvent)
class MusicEventAdmin(admin.ModelAdmin):
    form = MusicEventAdminForm
    list_display = ['title', 'event_type', 'event_date', 'location', 'has_image', 'is_active']
    list_filter = ['event_type', 'event_date', 'is_active', 'is_featured']
    search_fields = ['title', 'location', 'venue']
    readonly_fields = ['image_key', 'image_url', 'created_at']
    
    def has_image(self, obj):
        return bool(obj.image_key and check_file_exists(obj.image_key))
    has_image.boolean = True
    has_image.short_description = '🖼️ Imagen en R2'
    
    def image_url(self, obj):
        if obj.image_key and self.has_image(obj):
            url = generate_presigned_url(obj.image_key, expiration=3600)
            return f'<a href="{url}" target="_blank">🔗 Ver imagen</a>' if url else "No disponible"
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'
    
    def save_model(self, request, obj, form, change):
        event_image = form.cleaned_data.get('event_image')
        
        # Generar key antes de guardar
        if event_image and isinstance(event_image, UploadedFile):
            if not obj.image_key or not change:
                file_extension = event_image.name.split('.')[-1].lower() if '.' in event_image.name else 'jpg'
                obj.image_key = f"events/{uuid.uuid4().hex[:16]}.{file_extension}"
        
        super().save_model(request, obj, form, change)
        
        # Subir imagen después de guardar
        if event_image and isinstance(event_image, UploadedFile):
            try:
                event_image.open('rb')
                success = upload_file_to_r2(event_image, obj.image_key)
                event_image.close()
                
                if success and check_file_exists(obj.image_key):
                    messages.success(request, f"Imagen de evento subida: {obj.image_key}")
                else:
                    messages.error(request, f"Error subiendo imagen de evento: {obj.image_key}")
            except Exception as e:
                messages.error(request, f"Excepción subiendo imagen: {e}")

# =============================================
# MODELOS SIN LÓGICA DE ARCHIVOS R2
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

# UserProfile admin removido temporalmente si causa problemas