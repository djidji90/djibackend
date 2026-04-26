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
    Comment, PlayHistory, CommentReaction, UploadSession, UploadQuota,
    # Playlists curadas
    CuratedPlaylist, CuratedPlaylistSong, CuratedPlaylistSave, CuratedPlaylistAnalytics,
)
from .r2_utils import upload_file_to_r2, delete_file_from_r2, check_file_exists, generate_presigned_url


logger = logging.getLogger(__name__)

# ================================
# 📝 FORMS PERSONALIZADOS
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
# 🎵 SONG ADMIN - CORREGIDO
# ================================

# musica/admin.py - SECCIÓN SONG ADMIN CORREGIDA

@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    form = SongAdminForm
    list_display = [
        'title', 'artist', 'genre', 'uploaded_by',
        'category',                       # ✅ NUEVO
        'price_display',                  # ✅ NUEVO
        'has_audio', 'has_image', 
        'downloads_count',
        'confirmed_downloads',
        'pending_downloads',
        'is_purchasable',                 # ✅ NUEVO
        'is_public', 'created_at',
        'quick_actions'
    ]
    
    list_filter = [
        'genre', 
        'created_at', 
        'is_public', 
        'uploaded_by',
        'category',                       # ✅ NUEVO
        'is_purchasable',                 # ✅ NUEVO
    ]
    
    search_fields = [
        'title', 
        'artist', 
        'genre',
        'uploaded_by__username'
    ]
    
    # ✅ CORREGIDO: Agregar campos de wallet a readonly_fields
    readonly_fields = [
        'file_key', 
        'image_key', 
        'likes_count', 
        'plays_count',
        'downloads_count',
        'confirmed_downloads_detail',
        'pending_downloads_detail',
        'audio_url', 
        'image_url', 
        'created_at', 
        'updated_at',
        # ✅ NUEVOS CAMPOS DE WALLET
        'sales_count',
        'total_revenue',
        'last_purchased_at',
        'price_display',
        'artist_share_display',
    ]
    
    # ✅ SI USAS list_editable, debe estar en list_display
    # list_editable = ('is_public', 'is_purchasable', 'category')  # Opcional
    
    actions = [
        'verify_r2_files', 
        'generate_presigned_urls', 
        'export_to_csv',
        'fix_downloads_count',
        # ✅ NUEVAS ACCIONES
        'mark_as_purchasable',
        'mark_as_not_purchasable',
        'set_category_standard',
    ]

    fieldsets = (
        ('Información Básica', {
            'fields': ('title', 'artist', 'genre', 'duration', 'uploaded_by', 'is_public')
        }),
        # ✅ NUEVA SECCIÓN DE MONETIZACIÓN
        ('Monetización (Precios definidos por plataforma)', {
            'fields': ('category', 'is_purchasable', 'price_display', 'artist_share_display',
                       'sales_count', 'total_revenue', 'last_purchased_at'),
            'description': '💰 Los precios son fijos según categoría: Estándar=500 XAF, Éxito=750 XAF, Premium=1000 XAF, Clásico=300 XAF'
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
        ('Estadísticas de Descargas', {
            'fields': (
                'downloads_count', 
                'confirmed_downloads_detail',
                'pending_downloads_detail'
            ),
            'description': '📊 Descargas confirmadas vs pendientes'
        }),
        ('Otras Estadísticas', {
            'fields': ('likes_count', 'plays_count'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    # ========== MÉTODOS EXISTENTES ==========
    
    def has_audio(self, obj):
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
        if obj.file_key:
            try:
                if check_file_exists(obj.file_key):
                    url = generate_presigned_url(obj.file_key, expiration=3600)
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
                if check_file_exists(obj.image_key):
                    url = generate_presigned_url(obj.image_key, expiration=3600)
                    if url:
                        return format_html(f'<a href="{url}" target="_blank">🔗 Ver imagen (1h)</a>')
            except Exception as e:
                logger.error(f"Error generando URL imagen para {obj.id}: {e}")
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'

    def quick_actions(self, obj):
        buttons = []
        
        # ✅ CORREGIDO: Usa el nombre correcto de la app
        # Si tu app se llama 'api2', usa 'api2'
        # Si tu app se llama 'musica', usa 'musica'
        edit_url = reverse('admin:api2_song_change', args=[obj.id])
        buttons.append(f'<a href="{edit_url}" class="button" title="Editar">✏️</a>')

        if obj.file_key:
            try:
                if check_file_exists(obj.file_key):
                    url = generate_presigned_url(obj.file_key, expiration=300)
                    buttons.append(f'<a href="{url}" target="_blank" class="button" title="Escuchar">🎵</a>')
            except:
                pass

        return format_html(' '.join(buttons))
    quick_actions.short_description = 'Acciones'
    quick_actions.allow_tags = True

    # ========== NUEVOS MÉTODOS DE PRECIO ==========
    
    def price_display(self, obj):
        """Mostrar precio según categoría"""
        if hasattr(obj, 'formatted_price'):
            return obj.formatted_price
        return f"{obj.price:,.0f} XAF" if hasattr(obj, 'price') else "0 XAF"
    price_display.short_description = 'Precio'
    
    def artist_share_display(self, obj):
        """Mostrar lo que recibe el artista"""
        if hasattr(obj, 'artist_share'):
            return f"{obj.artist_share:,.0f} XAF (80%)"
        return "0 XAF"
    artist_share_display.short_description = 'Artista recibe'

    # ========== NUEVOS MÉTODOS PARA DESCARGAS ==========
    
    def confirmed_downloads(self, obj):
        from api2.models import Download
        count = Download.objects.filter(song=obj, is_confirmed=True).count()
        return format_html('<span style="color: green;">✅ {}</span>', count)
    confirmed_downloads.short_description = 'Confirmadas'
    
    def pending_downloads(self, obj):
        from api2.models import Download
        count = Download.objects.filter(song=obj, is_confirmed=False).count()
        if count > 0:
            return format_html('<span style="color: orange;">⏳ {}</span>', count)
        return count
    pending_downloads.short_description = 'Pendientes'
    
    def confirmed_downloads_detail(self, obj):
        from api2.models import Download
        downloads = Download.objects.filter(
            song=obj, 
            is_confirmed=True
        ).select_related('user').order_by('-downloaded_at')[:5]
        
        if not downloads:
            return "No hay descargas confirmadas"
        
        items = []
        for d in downloads:
            items.append(f"• {d.user.username} - {d.downloaded_at.strftime('%Y-%m-%d %H:%M')}")
        return format_html('<br>'.join(items))
    confirmed_downloads_detail.short_description = 'Últimas confirmadas'
    
    def pending_downloads_detail(self, obj):
        from api2.models import Download
        downloads = Download.objects.filter(
            song=obj, 
            is_confirmed=False
        ).select_related('user').order_by('-downloaded_at')[:5]
        
        if not downloads:
            return "No hay descargas pendientes"
        
        items = []
        for d in downloads:
            items.append(f"• {d.user.username} - {d.downloaded_at.strftime('%Y-%m-%d %H:%M')}")
        return format_html('<span style="color: orange;">⏳</span> ' + '<br>'.join(items))
    pending_downloads_detail.short_description = 'Pendientes'

    # ========== NUEVAS ACCIONES ==========
    
    @admin.action(description="🔧 Corregir contador de descargas")
    def fix_downloads_count(self, request, queryset):
        from django.db import transaction
        from api2.models import Download
        
        with transaction.atomic():
            fixed = 0
            errors = 0
            
            for song in queryset:
                try:
                    real_count = Download.objects.filter(
                        song=song, 
                        is_confirmed=True
                    ).count()
                    
                    if song.downloads_count != real_count:
                        song.downloads_count = real_count
                        song.save(update_fields=['downloads_count'])
                        fixed += 1
                        logger.info(f"Corregida canción {song.id}: {song.downloads_count} → {real_count}")
                except Exception as e:
                    errors += 1
                    logger.error(f"Error corrigiendo canción {song.id}: {e}")
            
            message = f"✅ {fixed} canciones corregidas"
            if errors:
                message += f", ❌ {errors} errores"
            self.message_user(request, message, level='SUCCESS' if errors == 0 else 'WARNING')
    
    # ✅ NUEVAS ACCIONES DE WALLET
    @admin.action(description="✅ Marcar como disponibles para compra")
    def mark_as_purchasable(self, request, queryset):
        updated = queryset.update(is_purchasable=True)
        self.message_user(request, f'{updated} canciones marcadas como disponibles para compra.')
    
    @admin.action(description="❌ Marcar como NO disponibles para compra")
    def mark_as_not_purchasable(self, request, queryset):
        updated = queryset.update(is_purchasable=False)
        self.message_user(request, f'{updated} canciones marcadas como NO disponibles.')
    
    @admin.action(description="🏷️ Establecer categoría estándar")
    def set_category_standard(self, request, queryset):
        updated = queryset.update(category='standard')
        self.message_user(request, f'{updated} canciones establecidas como estándar.')

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
                    if url:
                        return format_html(f'<a href="{url}" target="_blank">🔗 Ver imagen (1h)</a>')
            except Exception:
                pass
        return "Sin imagen"
    image_url.allow_tags = True
    image_url.short_description = 'URL Imagen'

    def save_model(self, request, obj, form, change):
        """Maneja la subida de imágenes de eventos a R2 - COMPLETO"""
        logger.info(f"🔄 Guardando evento - ID: {obj.id if change else 'Nueva'}, Cambio: {change}")
        
        event_image = form.cleaned_data.get('event_image')
        old_image_key = obj.image_key if change else None
        
        # Generar nueva key si hay imagen
        if event_image and isinstance(event_image, UploadedFile):
            file_extension = os.path.splitext(event_image.name)[1].lower()
            if not file_extension:
                file_extension = '.jpg'
            new_image_key = f"events/images/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.image_key = new_image_key
            logger.info(f"📝 Nueva key de imagen de evento: {new_image_key}")
        
        try:
            super().save_model(request, obj, form, change)
            logger.info(f"💾 Evento guardado en DB - ID: {obj.id}")
        except Exception as e:
            logger.error(f"💥 Error guardando evento en DB: {e}")
            messages.error(request, f"Error guardando en base de datos: {str(e)}")
            return
        
        # Subir imagen si existe
        if event_image and isinstance(event_image, UploadedFile):
            try:
                if hasattr(event_image, 'seek'):
                    event_image.seek(0)
                
                image_content_type = getattr(event_image, 'content_type', 'image/jpeg')
                success = upload_file_to_r2(
                    file_obj=event_image,
                    key=obj.image_key,
                    content_type=image_content_type
                )
                
                if success:
                    if check_file_exists(obj.image_key):
                        messages.success(request, f"✅ Imagen de evento subida: {obj.image_key}")
                        logger.info(f"✅ Imagen de evento subida exitosamente: {obj.image_key}")
                        
                        # Eliminar imagen antigua si existe y es diferente
                        if old_image_key and old_image_key != obj.image_key:
                            try:
                                if check_file_exists(old_image_key):
                                    delete_file_from_r2(old_image_key)
                                    logger.info(f"🗑️ Imagen antigua de evento eliminada: {old_image_key}")
                            except Exception as delete_error:
                                logger.warning(f"No se pudo eliminar imagen antigua: {delete_error}")
                    else:
                        messages.warning(request, f"Imagen subida pero no encontrada en R2: {obj.image_key}")
                else:
                    messages.error(request, f"❌ Falló subida de imagen: {obj.image_key}")
                
            except Exception as e:
                logger.error(f"💥 Error en subida de imagen de evento: {e}", exc_info=True)
                messages.error(request, f"Error subiendo imagen: {str(e)}")
        
        logger.info(f"🎉 Proceso completado para evento ID: {obj.id}")

# ================================
# 👤 USERPROFILE ADMIN - COMPLETO Y CORREGIDO
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
                    if url:
                        return format_html(f'<a href="{url}" target="_blank">🔗 Ver avatar (1h)</a>')
            except Exception:
                pass
        return "Sin avatar"
    avatar_url.allow_tags = True
    avatar_url.short_description = 'URL Avatar'

    def save_model(self, request, obj, form, change):
        """Maneja la subida de avatares a R2 - COMPLETO"""
        logger.info(f"🔄 Guardando perfil - User: {obj.user.username}, Cambio: {change}")
        
        avatar_upload = form.cleaned_data.get('avatar_upload')
        old_avatar_key = obj.avatar_key if change else None
        
        # Generar key antes de guardar
        if avatar_upload and isinstance(avatar_upload, UploadedFile):
            # Validar tamaño máximo
            if avatar_upload.size > 5 * 1024 * 1024:
                messages.error(request, "La imagen es demasiado grande. Máximo 5MB.")
                return
            
            file_extension = os.path.splitext(avatar_upload.name)[1].lower()
            if not file_extension:
                file_extension = '.jpg'
            new_avatar_key = f"avatars/{uuid.uuid4().hex[:16]}{file_extension}"
            obj.avatar_key = new_avatar_key
            logger.info(f"📝 Nueva key de avatar: {new_avatar_key}")
        
        try:
            super().save_model(request, obj, form, change)
            logger.info(f"💾 Perfil guardado en DB - User: {obj.user.username}")
        except Exception as e:
            logger.error(f"💥 Error guardando perfil en DB: {e}")
            messages.error(request, f"Error guardando en base de datos: {str(e)}")
            return
        
        # Subir avatar si existe
        if avatar_upload and isinstance(avatar_upload, UploadedFile):
            try:
                if hasattr(avatar_upload, 'seek'):
                    avatar_upload.seek(0)
                
                avatar_content_type = getattr(avatar_upload, 'content_type', 'image/jpeg')
                success = upload_file_to_r2(
                    file_obj=avatar_upload,
                    key=obj.avatar_key,
                    content_type=avatar_content_type
                )
                
                if success:
                    if check_file_exists(obj.avatar_key):
                        messages.success(request, f"✅ Avatar subido: {obj.avatar_key}")
                        logger.info(f"✅ Avatar subido exitosamente: {obj.avatar_key}")
                        
                        # Eliminar avatar antiguo si existe y es diferente
                        if old_avatar_key and old_avatar_key != obj.avatar_key:
                            try:
                                if check_file_exists(old_avatar_key):
                                    delete_file_from_r2(old_avatar_key)
                                    logger.info(f"🗑️ Avatar antiguo eliminado: {old_avatar_key}")
                            except Exception as delete_error:
                                logger.warning(f"No se pudo eliminar avatar antiguo: {delete_error}")
                    else:
                        messages.warning(request, f"Avatar subido pero no encontrado en R2: {obj.avatar_key}")
                else:
                    messages.error(request, f"❌ Falló subida de avatar: {obj.avatar_key}")
                
            except Exception as e:
                logger.error(f"💥 Error en subida de avatar: {e}", exc_info=True)
                messages.error(request, f"Error subiendo avatar: {str(e)}")
        
        logger.info(f"🎉 Proceso completado para perfil: {obj.user.username}")

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
        """Botones de acción rápida - CORREGIDO CON NOMBRES API2"""
        buttons = []

        # Botón para editar - CORREGIDO: usa 'api2' no 'musica'
        edit_url = reverse('admin:api2_uploadsession_change', args=[obj.id])
        buttons.append(f'<a href="{edit_url}" class="button" title="Editar">✏️</a>')

        # Botón para verificar R2 si tiene file_key
        if obj.file_key:
            try:
                if check_file_exists(obj.file_key):
                    url = generate_presigned_url(obj.file_key, expiration=300)
                    buttons.append(f'<a href="{url}" target="_blank" class="button" title="Ver archivo">🔍</a>')
            except:
                pass

        # Botón para ver canción si existe - CORREGIDO: usa 'api2' no 'musica'
        if obj.song:
            song_url = reverse('admin:api2_song_change', args=[obj.song.id])
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
# 📊 UPLOADQUOTA ADMIN - CORREGIDO
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
            if hasattr(obj, 'get_quota_info'):
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
                
                html += '<div class="quota-info">'
                
                # Límites Diarios
                html += '<div class="quota-section">'
                html += '<div class="quota-title">📅 Límites Diarios</div>'
                
                # Uploads diarios
                daily_uploads_percentage = (obj.daily_uploads_count / obj.max_daily_uploads * 100) if obj.max_daily_uploads > 0 else 0
                uploads_color = "danger" if daily_uploads_percentage >= 90 else "warning" if daily_uploads_percentage >= 70 else ""
                html += f'<div class="quota-item"><strong>Uploads:</strong> {obj.daily_uploads_count}/{obj.max_daily_uploads} <span class="{uploads_color}">({daily_uploads_percentage:.1f}%)</span></div>'
                html += f'<div class="progress-bar"><div class="progress-fill" style="width: {min(daily_uploads_percentage, 100)}%"></div></div>'
                
                # Tamaño diario
                daily_size_percentage = (obj.daily_uploads_size / obj.max_daily_size * 100) if obj.max_daily_size > 0 else 0
                size_color = "danger" if daily_size_percentage >= 90 else "warning" if daily_size_percentage >= 70 else ""
                daily_size_mb = obj.daily_uploads_size / (1024 * 1024)
                max_daily_mb = obj.max_daily_size / (1024 * 1024)
                html += f'<div class="quota-item"><strong>Tamaño:</strong> {daily_size_mb:.1f}/{max_daily_mb:.0f} MB <span class="{size_color}">({daily_size_percentage:.1f}%)</span></div>'
                html += f'<div class="progress-bar"><div class="progress-fill" style="width: {min(daily_size_percentage, 100)}%"></div></div>'
                
                if obj.daily_uploads_reset_at:
                    reset_time = timezone.localtime(obj.daily_uploads_reset_at + timezone.timedelta(days=1))
                    html += f'<div class="quota-item"><small>Resetea: {reset_time.strftime("%Y-%m-%d %H:%M")}</small></div>'
                
                html += '</div>'
                
                # Uploads Pendientes
                html += '<div class="quota-section">'
                html += '<div class="quota-title">⏳ Uploads Pendientes</div>'
                html += f'<div class="quota-item">Cantidad: {obj.pending_uploads_count}</div>'
                html += f'<div class="quota-item">Tamaño: {obj.pending_uploads_size/(1024*1024):.1f} MB</div>'
                html += '</div>'
                
                # Totales
                html += '<div class="quota-section">'
                html += '<div class="quota-title">💾 Totales</div>'
                html += f'<div class="quota-item">Uploads totales: {obj.total_uploads_count}</div>'
                html += f'<div class="quota-item">Almacenamiento usado: {obj.total_uploads_size/(1024*1024*1024):.1f} GB</div>'
                html += f'<div class="quota-item">Límite por archivo: {obj.max_file_size/(1024*1024):.0f} MB</div>'
                html += f'<div class="quota-item">Almacenamiento total: {obj.max_total_storage/(1024*1024*1024):.0f} GB</div>'
                html += '</div>'
                
                html += '</div>'
                
                return format_html(html)
            else:
                return "Método get_quota_info no disponible"
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
    list_display = [
        'user', 
        'song', 
        'downloaded_at', 
        'is_confirmed',           # 🆕 Nuevo campo
        'ip_address',
        'download_token_short'     # 🆕 Token abreviado
    ]
    
    list_filter = [
        'downloaded_at', 
        'is_confirmed',            # 🆕 Filtro por confirmación
    ]
    
    search_fields = [
        'user__username', 
        'user__email',
        'song__title', 
        'song__artist',
        'download_token'            # 🆕 Buscar por token
    ]
    
    # ✅ CORREGIDO: Solo campos que EXISTEN en tu modelo
    readonly_fields = [
        'download_token',
        'downloaded_at',            # Cambiado de created_at a downloaded_at
        'ip_address',
        'user_agent'
    ]
    
    date_hierarchy = 'downloaded_at'
    
    fieldsets = (
        ('Relaciones', {
            'fields': ('user', 'song')
        }),
        ('Estado de Confirmación', {
            'fields': ('is_confirmed', 'download_token'),
            'classes': ('wide',),
            'description': '✅ Confirmada = descarga contabilizada'
        }),
        ('Metadatos', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Fecha', {
            'fields': ('downloaded_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = [
        'mark_as_confirmed',
        'mark_as_unconfirmed',
        'export_to_csv'
    ]
    
    def get_queryset(self, request):
        """Optimizar queryset con select_related"""
        return super().get_queryset(request).select_related('user', 'song')
    
    def download_token_short(self, obj):
        """Mostrar solo primeros caracteres del token"""
        if obj.download_token:
            return f"{obj.download_token[:8]}..."
        return '-'
    download_token_short.short_description = 'Token'
    
    def get_readonly_fields(self, request, obj=None):
        """Hacer is_confirmed readonly si ya está confirmado"""
        if obj and obj.is_confirmed:
            return self.readonly_fields + ['is_confirmed']
        return self.readonly_fields
    
    # ========== ACCIONES ADMIN ==========
    
    @admin.action(description="✅ Marcar como confirmadas")
    def mark_as_confirmed(self, request, queryset):
        """Marca descargas como confirmadas y actualiza contadores"""
        from django.db.models import F
        from django.db import transaction
        from api2.models import Song  # Ajusta el import según tu estructura
        
        with transaction.atomic():
            # Filtrar no confirmadas
            to_confirm = queryset.filter(is_confirmed=False)
            count = to_confirm.count()
            
            if count == 0:
                self.message_user(
                    request, 
                    "Todas las descargas seleccionadas ya están confirmadas",
                    level='WARNING'
                )
                return
            
            # Actualizar descargas
            to_confirm.update(is_confirmed=True)
            
            # Actualizar contadores de canciones
            for download in to_confirm:
                Song.objects.filter(id=download.song_id).update(
                    downloads_count=F('downloads_count') + 1
                )
            
            self.message_user(
                request, 
                f"✅ {count} descarga(s) confirmada(s) correctamente",
                level='SUCCESS'
            )
    
    @admin.action(description="❌ Marcar como no confirmadas")
    def mark_as_unconfirmed(self, request, queryset):
        """Marca descargas como no confirmadas"""
        from django.db.models import F
        from django.db import transaction
        from api2.models import Song
        
        with transaction.atomic():
            # Filtrar confirmadas
            to_unconfirm = queryset.filter(is_confirmed=True)
            count = to_unconfirm.count()
            
            if count == 0:
                self.message_user(
                    request, 
                    "Ninguna descarga seleccionada está confirmada",
                    level='WARNING'
                )
                return
            
            # Actualizar descargas
            to_unconfirm.update(is_confirmed=False)
            
            # Actualizar contadores de canciones (restar)
            for download in to_unconfirm:
                # Asegurar que no baje de 0
                song = Song.objects.get(id=download.song_id)
                new_count = max(0, song.downloads_count - 1)
                Song.objects.filter(id=download.song_id).update(
                    downloads_count=new_count
                )
            
            self.message_user(
                request, 
                f"❌ {count} descarga(s) marcadas como no confirmadas",
                level='SUCCESS'
            )
    
    @admin.action(description="📄 Exportar a CSV")
    def export_to_csv(self, request, queryset):
        """Exporta las descargas a CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="downloads_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Usuario', 
            'Canción', 
            'Artista',
            'Fecha', 
            'Confirmada',
            'IP',
            'Token'
        ])
        
        for d in queryset.select_related('user', 'song'):
            writer.writerow([
                d.user.username,
                d.song.title,
                d.song.artist,
                d.downloaded_at.strftime('%Y-%m-%d %H:%M'),
                'Sí' if d.is_confirmed else 'No',
                d.ip_address or '',
                d.download_token or ''
            ])
        
        return response
    
    def get_actions(self, request):
        """Personalizar acciones disponibles"""
        actions = super().get_actions(request)
        
        if not request.user.is_superuser:
            # Usuarios no superadmin no pueden marcar como no confirmadas
            if 'mark_as_unconfirmed' in actions:
                del actions['mark_as_unconfirmed']
        
        return actions

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
# 🔧 CONFIGURACIÓN ADICIONAL
# ================================

# Personalizar el título del admin
admin.site.site_header = 'Djidi Music - Administración'
admin.site.site_title = 'Djidi Music Admin'
admin.site.index_title = 'Panel de Administración'


# ============================================================
# AGREGAR AL FINAL DE api2/admin.py (después de PlayHistoryAdmin)
# Antes de la sección "CONFIGURACIÓN ADICIONAL"
# ============================================================

# ============================================================
# INLINE: Canciones dentro de una playlist
# ============================================================

class CuratedPlaylistSongInline(admin.TabularInline):
    model               = CuratedPlaylistSong
    extra               = 0
    min_num             = 0
    max_num             = 100
    ordering            = ('position',)
    fields              = ('position', 'song', 'score', 'added_by', 'valid_until', 'added_at')
    readonly_fields     = ('added_at',)
    autocomplete_fields = ['song']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('song', 'added_by')


# ============================================================
# INLINE: Analytics (solo lectura)
# ============================================================

class CuratedPlaylistAnalyticsInline(admin.TabularInline):
    model           = CuratedPlaylistAnalytics
    extra           = 0
    max_num         = 0
    can_delete      = False
    ordering        = ('-date',)
    fields          = ('date', 'total_streams', 'unique_listeners',
                       'avg_completion_rate', 'shares_count', 'saves_count')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


# ============================================================
# ADMIN: CuratedPlaylist
# ============================================================

@admin.register(CuratedPlaylist)
class CuratedPlaylistAdmin(admin.ModelAdmin):

    # ----------------------------------------------------------
    # Listado
    # ----------------------------------------------------------
    list_display = (
        'name',
        'playlist_type_badge',
        'algorithm_badge',
        'song_count',
        'streams_display',
        'saves_count',
        'featured',
        'is_active',
        'outdated_badge',
        'priority',
    )
    list_display_links = ('name',)
    list_editable      = ('featured', 'is_active', 'priority')
    list_filter        = (
        'playlist_type',
        'algorithm',
        'update_frequency',
        'is_active',
        'featured',
    )
    search_fields  = ('name', 'slug', 'description')
    ordering       = ('-priority', '-created_at')
    list_per_page  = 25

    # ----------------------------------------------------------
    # Formulario de edición
    # ----------------------------------------------------------
    fieldsets = (
        ('Información básica', {
            'fields': ('name', 'slug', 'description', 'cover_image'),
        }),
        ('Configuración', {
            'fields': (
                ('playlist_type', 'update_frequency'),
                ('algorithm', 'priority'),
                ('min_songs', 'max_songs'),
                ('target_genres', 'target_country'),
            ),
        }),
        ('Visibilidad', {
            'fields': (('is_active', 'featured'),),
        }),
        ('Estadísticas (solo lectura)', {
            'classes': ('collapse',),
            'fields': (
                ('song_count', 'total_streams'),
                ('unique_listeners', 'saves_count'),
                ('last_calculated_at', 'created_by'),
                ('created_at', 'updated_at'),
            ),
        }),
    )

    readonly_fields = (
        'slug',
        'song_count',
        'total_streams',
        'unique_listeners',
        'saves_count',
        'last_calculated_at',
        'created_at',
        'updated_at',
    )

    inlines = [CuratedPlaylistSongInline, CuratedPlaylistAnalyticsInline]

    # ----------------------------------------------------------
    # Acciones masivas
    # ----------------------------------------------------------
    actions = [
        'activate_playlists',
        'deactivate_playlists',
        'mark_as_featured',
        'unmark_featured',
        'run_update_algorithm',
        'reset_stats',
    ]

    @admin.action(description='✅ Activar playlists seleccionadas')
    def activate_playlists(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} playlist(s) activada(s).', messages.SUCCESS)

    @admin.action(description='⛔ Desactivar playlists seleccionadas')
    def deactivate_playlists(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} playlist(s) desactivada(s).', messages.WARNING)

    @admin.action(description='⭐ Marcar como destacadas')
    def mark_as_featured(self, request, queryset):
        updated = queryset.update(featured=True)
        self.message_user(request, f'{updated} playlist(s) destacada(s).', messages.SUCCESS)

    @admin.action(description='☆ Quitar destacado')
    def unmark_featured(self, request, queryset):
        updated = queryset.update(featured=False)
        self.message_user(request, f'{updated} playlist(s) quitadas de destacadas.', messages.SUCCESS)

    @admin.action(description='🔄 Ejecutar algoritmo de actualización')
    def run_update_algorithm(self, request, queryset):
        from django.core.management import call_command

        updated = 0
        skipped = 0

        for playlist in queryset:
            if playlist.algorithm == 'manual':
                skipped += 1
                continue
            try:
                call_command('update_playlists', slug=playlist.slug, force=True)
                updated += 1
            except Exception as e:
                self.message_user(request, f'Error en "{playlist.name}": {e}', messages.ERROR)

        if updated:
            self.message_user(request, f'{updated} playlist(s) actualizadas.', messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f'{skipped} playlist(s) manual(es) omitidas (sin algoritmo).',
                messages.WARNING,
            )

    @admin.action(description='🗑️ Resetear estadísticas (streams, saves)')
    def reset_stats(self, request, queryset):
        updated = queryset.update(total_streams=0, unique_listeners=0, saves_count=0)
        self.message_user(
            request,
            f'Estadísticas reseteadas en {updated} playlist(s).',
            messages.WARNING,
        )

    # ----------------------------------------------------------
    # Columnas personalizadas
    # ----------------------------------------------------------

    @admin.display(description='Tipo')
    def playlist_type_badge(self, obj):
        colors = {
            'temporal':   '#3b82f6',
            'generica':   '#10b981',
            'nicho':      '#8b5cf6',
            'mood':       '#f59e0b',
            'promocional':'#ef4444',
        }
        color = colors.get(obj.playlist_type, '#6b7280')
        label = obj.get_playlist_type_display()
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:12px;font-size:11px">{}</span>',
            color, label,
        )

    @admin.display(description='Algoritmo')
    def algorithm_badge(self, obj):
        icons = {
            'manual':       '✋',
            'trending':     '🔥',
            'new_releases': '🆕',
            'top_genre':    '🎵',
            'hybrid':       '⚡',
        }
        icon = icons.get(obj.algorithm, '❓')
        return format_html(
            '<span title="{}">{} {}</span>',
            obj.get_algorithm_display(), icon, obj.algorithm,
        )

    @admin.display(description='Streams')
    def streams_display(self, obj):
        if obj.total_streams >= 1000:
            return format_html('<b>{:.1f}k</b>', obj.total_streams / 1000)
        return obj.total_streams

    @admin.display(description='Estado actualización')
    def outdated_badge(self, obj):
        if obj.update_frequency == 'never':
            return format_html('<span style="color:#6b7280">— manual</span>')
        if obj.is_outdated:
            return format_html(
                '<span style="color:#ef4444;font-weight:bold">⚠ Desactualizada</span>'
            )
        return format_html('<span style="color:#10b981">✓ Al día</span>')

    # ----------------------------------------------------------
    # Guardar: asignar created_by automáticamente
    # ----------------------------------------------------------
    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    # ----------------------------------------------------------
    # URLs extra: trigger manual de update y clear songs
    # ----------------------------------------------------------
    def get_urls(self):
        from django.urls import path as dj_path
        urls  = super().get_urls()
        extra = [
            dj_path(
                '<int:playlist_id>/update-now/',
                self.admin_site.admin_view(self._update_now),
                name='curatedplaylist_update_now',
            ),
            dj_path(
                '<int:playlist_id>/clear-songs/',
                self.admin_site.admin_view(self._clear_songs),
                name='curatedplaylist_clear_songs',
            ),
        ]
        return extra + urls

    def _update_now(self, request, playlist_id):
        from django.core.management import call_command
        from django.http import HttpResponseRedirect

        try:
            playlist = CuratedPlaylist.objects.get(pk=playlist_id)
            if playlist.algorithm == 'manual':
                self.message_user(
                    request,
                    'Playlist manual — no tiene algoritmo que ejecutar.',
                    messages.WARNING,
                )
            else:
                call_command('update_playlists', slug=playlist.slug, force=True)
                self.message_user(
                    request, f'"{playlist.name}" actualizada correctamente.', messages.SUCCESS
                )
        except CuratedPlaylist.DoesNotExist:
            self.message_user(request, 'Playlist no encontrada.', messages.ERROR)
        except Exception as e:
            self.message_user(request, f'Error: {e}', messages.ERROR)

        return HttpResponseRedirect(
            reverse('admin:api2_curatedplaylist_change', args=[playlist_id])
        )

    def _clear_songs(self, request, playlist_id):
        from django.http import HttpResponseRedirect

        try:
            playlist = CuratedPlaylist.objects.get(pk=playlist_id)
            count, _ = CuratedPlaylistSong.objects.filter(playlist=playlist).delete()
            CuratedPlaylist.objects.filter(pk=playlist_id).update(song_count=0)
            self.message_user(
                request,
                f'{count} canción(es) eliminadas de "{playlist.name}".',
                messages.SUCCESS,
            )
        except CuratedPlaylist.DoesNotExist:
            self.message_user(request, 'Playlist no encontrada.', messages.ERROR)
        except Exception as e:
            self.message_user(request, f'Error: {e}', messages.ERROR)

        return HttpResponseRedirect(
            reverse('admin:api2_curatedplaylist_change', args=[playlist_id])
        )

    # ----------------------------------------------------------
    # Botones extra en el formulario de detalle
    # ----------------------------------------------------------
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['update_now_url'] = reverse(
            'admin:curatedplaylist_update_now', args=[object_id]
        )
        extra_context['clear_songs_url'] = reverse(
            'admin:curatedplaylist_clear_songs', args=[object_id]
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


# ============================================================
# ADMIN: CuratedPlaylistSong (edición directa)
# ============================================================

@admin.register(CuratedPlaylistSong)
class CuratedPlaylistSongAdmin(admin.ModelAdmin):
    list_display        = ('playlist', 'song_title', 'song_artist', 'position', 'score', 'added_at')
    list_display_links  = ('song_title',)
    list_filter         = ('playlist',)
    search_fields       = ('song__title', 'song__artist', 'playlist__name')
    ordering            = ('playlist', 'position')
    autocomplete_fields = ['song', 'playlist']
    list_per_page       = 50
    list_select_related = ('playlist', 'song')

    @admin.display(description='Título', ordering='song__title')
    def song_title(self, obj):
        return obj.song.title

    @admin.display(description='Artista', ordering='song__artist')
    def song_artist(self, obj):
        return obj.song.artist

    actions = ['move_to_top', 'move_to_bottom']

    @admin.action(description='⬆️ Mover al inicio')
    def move_to_top(self, request, queryset):
        for i, item in enumerate(queryset.order_by('position')):
            CuratedPlaylistSong.objects.filter(pk=item.pk).update(position=i)
        self.message_user(
            request, f'{queryset.count()} canción(es) movidas al inicio.', messages.SUCCESS
        )

    @admin.action(description='⬇️ Mover al final')
    def move_to_bottom(self, request, queryset):
        for item in queryset:
            max_pos = CuratedPlaylistSong.objects.filter(
                playlist=item.playlist
            ).count()
            CuratedPlaylistSong.objects.filter(pk=item.pk).update(position=max_pos + 100)
        self.message_user(
            request, f'{queryset.count()} canción(es) movidas al final.', messages.SUCCESS
        )


# ============================================================
# ADMIN: CuratedPlaylistSave (solo lectura)
# ============================================================

@admin.register(CuratedPlaylistSave)
class CuratedPlaylistSaveAdmin(admin.ModelAdmin):
    list_display    = ('user', 'playlist', 'created_at')
    list_filter     = ('playlist',)
    search_fields   = ('user__username', 'playlist__name')
    ordering        = ('-created_at',)
    readonly_fields = ('user', 'playlist', 'created_at')
    list_per_page   = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ============================================================
# ADMIN: CuratedPlaylistAnalytics (solo lectura)
# ============================================================

@admin.register(CuratedPlaylistAnalytics)
class CuratedPlaylistAnalyticsAdmin(admin.ModelAdmin):
    list_display    = (
        'playlist', 'date', 'total_streams',
        'unique_listeners', 'avg_completion_rate', 'saves_count',
    )
    list_filter     = ('playlist', 'date')
    search_fields   = ('playlist__name',)
    ordering        = ('-date',)
    date_hierarchy  = 'date'
    readonly_fields = (
        'playlist', 'date', 'total_streams', 'unique_listeners',
        'avg_completion_rate', 'shares_count', 'saves_count',
    )
    list_per_page   = 60

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Solo superuser puede borrar registros de analytics
        return request.user.is_superuser

# ================================
# 🚀 ¡LISTO PARA PRODUCCIÓN!
# ================================