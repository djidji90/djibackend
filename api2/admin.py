# api2/admin.py - VERSIÓN CORREGIDA
from django.contrib import admin
from django import forms
from .models import Song, MusicEvent, UserProfile, Like, Download, Comment, PlayHistory, CommentReaction
from .r2_utils import upload_file_to_r2, delete_file_from_r2, check_file_exists
from django.core.files.uploadedfile import UploadedFile

# FORMULARIOS PERSONALIZADOS
class SongAdminForm(forms.ModelForm):
    # Campos temporales solo para el admin - usar forms.FileField correctamente
    audio_file = forms.FileField(
        required=False,
        label="Archivo de Audio",
        help_text="Sube el archivo MP3 que se guardará en R2"
    )
    
    image_file = forms.ImageField(
        required=False,
        label="Imagen de Portada",
        help_text="Sube la imagen que se guardará en R2"
    )
    
    class Meta:
        model = Song
        fields = '__all__'

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

# ADMIN CONFIGURADO CORRECTAMENTE
@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    form = SongAdminForm
    list_display = ['title', 'artist', 'genre', 'uploaded_by', 'created_at', 'is_public']
    list_filter = ['genre', 'created_at', 'is_public']
    search_fields = ['title', 'artist']
    readonly_fields = ['file_key', 'image_key', 'likes_count', 'plays_count', 'downloads_count']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('title', 'artist', 'genre', 'duration')
        }),
        ('Archivos - SUBIR AQUÍ', {
            'fields': ('audio_file', 'image_file'),
            'description': 'Sube los archivos reales que se guardarán en R2'
        }),
        ('Claves R2 (Automáticas)', {
            'fields': ('file_key', 'image_key'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'is_public', 'likes_count', 'plays_count', 'downloads_count')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """
        Maneja la subida de archivos a R2 cuando se guarda desde el Admin
        """
        # 1. Guardar el objeto primero para obtener un ID y generar keys
        super().save_model(request, obj, form, change)
        
        # 2. Subir archivo de audio si se proporcionó
        audio_file = form.cleaned_data.get('audio_file')
        if audio_file and isinstance(audio_file, UploadedFile):
            print(f"📤 Subiendo archivo de audio a R2: {obj.file_key}")
            
            # Leer el archivo y subirlo a R2
            audio_file.open('rb')
            success = upload_file_to_r2(audio_file, obj.file_key)
            audio_file.close()
            
            if success:
                print("✅ Archivo de audio subido exitosamente a R2")
                # Verificar que realmente se subió
                if check_file_exists(obj.file_key):
                    print("✅ Verificación: Archivo existe en R2")
                else:
                    print("❌ Verificación: Archivo NO existe en R2")
            else:
                print("❌ Error subiendo archivo de audio a R2")
        
        # 3. Subir imagen si se proporcionó
        image_file = form.cleaned_data.get('image_file')
        if image_file and isinstance(image_file, UploadedFile):
            print(f"📤 Subiendo imagen a R2: {obj.image_key}")
            
            image_file.open('rb')
            success = upload_file_to_r2(image_file, obj.image_key)
            image_file.close()
            
            if success:
                print("✅ Imagen subida exitosamente a R2")
                if check_file_exists(obj.image_key):
                    print("✅ Verificación: Imagen existe en R2")
                else:
                    print("❌ Verificación: Imagen NO existe en R2")
            else:
                print("❌ Error subiendo imagen a R2")

@admin.register(MusicEvent)
class MusicEventAdmin(admin.ModelAdmin):
    form = MusicEventAdminForm
    list_display = ['title', 'event_type', 'event_date', 'location', 'is_active', 'is_featured']
    list_filter = ['event_type', 'event_date', 'is_active', 'is_featured']
    search_fields = ['title', 'location', 'venue']
    readonly_fields = ['image_key']
    
    fieldsets = (
        ('Información del Evento', {
            'fields': ('title', 'description', 'event_type', 'event_date', 'location', 'venue')
        }),
        ('Archivos - SUBIR IMAGEN', {
            'fields': ('event_image',),
            'description': 'Sube la imagen del evento que se guardará en R2'
        }),
        ('Clave R2 (Automática)', {
            'fields': ('image_key',),
            'classes': ('collapse',)
        }),
        ('Información de Tickets', {
            'fields': ('ticket_url', 'price')
        }),
        ('Estado', {
            'fields': ('is_active', 'is_featured')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """
        Maneja la subida de imagen del evento a R2
        """
        # Generar key para la imagen si no existe
        if not obj.image_key:
            import uuid
            obj.image_key = f"events/{uuid.uuid4().hex[:12]}.jpg"
        
        super().save_model(request, obj, form, change)
        
        event_image = form.cleaned_data.get('event_image')
        if event_image and isinstance(event_image, UploadedFile):
            print(f"📤 Subiendo imagen de evento a R2: {obj.image_key}")
            
            event_image.open('rb')
            success = upload_file_to_r2(event_image, obj.image_key)
            event_image.close()
            
            if success:
                print("✅ Imagen de evento subida exitosamente a R2")
                if check_file_exists(obj.image_key):
                    print("✅ Verificación: Imagen de evento existe en R2")
            else:
                print("❌ Error subiendo imagen de evento a R2")

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = ['user', 'location', 'songs_uploaded', 'created_at']
    search_fields = ['user__username', 'location']
    readonly_fields = ['avatar_key']
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('user', 'bio', 'location', 'website')
        }),
        ('Archivos - SUBIR AVATAR', {
            'fields': ('avatar_upload',),
            'description': 'Sube la imagen de avatar que se guardará en R2'
        }),
        ('Clave R2 (Automática)', {
            'fields': ('avatar_key',),
            'classes': ('collapse',)
        }),
        ('Preferencias', {
            'fields': ('favorite_genres', 'notifications_enabled')
        }),
        ('Estadísticas', {
            'fields': ('songs_uploaded', 'total_listening_time')
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """
        Maneja la subida de avatar a R2
        """
        # Generar key para el avatar si no existe
        if not obj.avatar_key:
            import uuid
            obj.avatar_key = f"avatars/{uuid.uuid4().hex[:12]}.jpg"
        
        super().save_model(request, obj, form, change)
        
        avatar_upload = form.cleaned_data.get('avatar_upload')
        if avatar_upload and isinstance(avatar_upload, UploadedFile):
            print(f"📤 Subiendo avatar a R2: {obj.avatar_key}")
            
            avatar_upload.open('rb')
            success = upload_file_to_r2(avatar_upload, obj.avatar_key)
            avatar_upload.close()
            
            if success:
                print("✅ Avatar subido exitosamente a R2")
                if check_file_exists(obj.avatar_key):
                    print("✅ Verificación: Avatar existe en R2")
            else:
                print("❌ Error subiendo avatar a R2")

# REGISTRAR MODELOS SIN LÓGICA ESPECIAL DE ARCHIVOS
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