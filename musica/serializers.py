# users/serializers.py
"""
Serializers para la app de usuarios.
"""
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

# ✅ IMPORTACIONES CORREGIDAS
from .models import CustomUser, UserVisit


class RegisterSerializer(serializers.ModelSerializer):
    """
    Serializer para registro de nuevos usuarios con todos los campos del frontend.
    """
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = CustomUser
        fields = [
            "username",
            "email",
            "password",
            "password2",
            "first_name",
            "last_name",
            "city",
            "neighborhood",
            "phone",
            "country",
            "gender",
            "birth_date",
            "terms_accepted",
        ]

    def validate(self, attrs):
        # Verificar que las contraseñas coincidan
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError(
                {"password": "Las contraseñas no coinciden."}
            )

        # Validar que el email es obligatorio
        if not attrs.get("email"):
            raise serializers.ValidationError(
                {"email": "El correo electrónico es obligatorio."}
            )

        # 🆕 Validar términos aceptados
        if not attrs.get("terms_accepted"):
            raise serializers.ValidationError(
                {"terms_accepted": "Debes aceptar los términos y condiciones."}
            )

        # 🆕 Validar fecha de nacimiento (solo si se proporciona)
        birth_date = attrs.get("birth_date")
        if birth_date and birth_date > timezone.now().date():
            raise serializers.ValidationError(
                {"birth_date": "La fecha de nacimiento no puede ser futura."}
            )

        # 🆕 Validar género (solo si se proporciona)
        gender = attrs.get("gender")
        if gender and gender not in ['M', 'F', 'O']:
            raise serializers.ValidationError(
                {"gender": "Género inválido. Debe ser M, F u O."}
            )

        # ✅ El país ya no se valida, puede ser cualquier texto
        # La conversión a código se hará en create()

        return attrs

    def get_country_code(self, country_name):
        """
        Convierte el nombre del país a código interno para lógica de negocio.
        """
        if not country_name:
            return None
            
        country_map = {
            # Guinea Ecuatorial y variantes
            'guinea ecuatorial': 'GQ',
            'guinea ecuatorial (malabo)': 'GQ',
            'guinea': 'GQ',
            'gq': 'GQ',
            
            # España y variantes
            'españa': 'ES',
            'espana': 'ES',
            'spain': 'ES',
            'es': 'ES',
            
            # Francia
            'francia': 'FR',
            'france': 'FR',
            'fr': 'FR',
            
            # Estados Unidos
            'estados unidos': 'US',
            'eeuu': 'US',
            'usa': 'US',
            'united states': 'US',
            'us': 'US',
            
            # Italia
            'italia': 'IT',
            'italy': 'IT',
            'it': 'IT',
            
            # Portugal
            'portugal': 'PT',
            'pt': 'PT',
            
            # Camerún
            'camerún': 'CM',
            'cameroon': 'CM',
            'cm': 'CM',
            
            # Gabón
            'gabón': 'GA',
            'gabon': 'GA',
            'ga': 'GA',
            
            # Congo
            'congo': 'CG',
            'cg': 'CG',
            
            # Reino Unido
            'reino unido': 'GB',
            'uk': 'GB',
            'united kingdom': 'GB',
            'gb': 'GB',
            
            # Alemania
            'alemania': 'DE',
            'germany': 'DE',
            'de': 'DE',
        }
        
        country_lower = country_name.lower().strip()
        
        # Buscar coincidencia exacta o parcial
        for key, code in country_map.items():
            if key in country_lower or country_lower == key:
                return code
        
        # Si no se encuentra, devolver OTHER
        return 'OTHER'

    def create(self, validated_data):
        # Eliminar la confirmación de contraseña
        validated_data.pop("password2")
        
        # Asegurar que terms_accepted sea booleano
        validated_data['terms_accepted'] = bool(validated_data.get('terms_accepted', False))
        
        # 🆕 Convertir país a código interno (para lógica de negocio)
        country_name = validated_data.get('country')
        if country_name:
            # Guardar el código internamente (si el modelo tiene country_code)
            # Si no, puedes almacenarlo en otro campo o simplemente ignorarlo
            country_code = self.get_country_code(country_name)
            # Si tu modelo tiene campo country_code, descomenta la siguiente línea:
            # validated_data['country_code'] = country_code
        
        # Crear el usuario con los datos validados
        user = CustomUser.objects.create_user(**validated_data)
        
        # Si se aceptaron términos, guardar la fecha
        if user.terms_accepted:
            user.terms_accepted_at = timezone.now()
            user.save(update_fields=['terms_accepted_at'])
        
        return user

    def to_representation(self, instance):
        """Personaliza la respuesta para incluir los tokens JWT y datos completos."""
        refresh = RefreshToken.for_user(instance)
        return {
            "user": {
                "id": instance.id,
                "username": instance.username,
                "email": instance.email,
                "first_name": instance.first_name,
                "last_name": instance.last_name,
                "city": instance.city,
                "neighborhood": instance.neighborhood,
                "phone": instance.phone,
                "country": instance.country,  # Texto original
                "gender": instance.gender,
                "birth_date": instance.birth_date,
                "terms_accepted": instance.terms_accepted,
                "is_verified": instance.is_verified,
                "default_currency": instance.default_currency,  # Usa el código interno
                # 🆕 Campos SEO en respuesta de registro
                "slug": instance.slug,
                "is_public": instance.is_public,
                "profile_url": instance.get_absolute_url(),
            },
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
        }


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer básico de usuario con campos extendidos.
    """
    full_name = serializers.SerializerMethodField()
    default_currency = serializers.SerializerMethodField()
    profile_url = serializers.SerializerMethodField()  # 🆕 URL pública del perfil
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'phone', 'city', 'neighborhood', 'country', 'gender', 'birth_date',
            'terms_accepted', 'default_currency', 'is_verified', 'can_withdraw', 
            'verified_at', 'is_active', 'date_joined', 'last_login',
            # 🆕 Campos SEO
            'slug', 'is_public', 'profile_url', 'updated_at'
        ]
        read_only_fields = ['id', 'is_verified', 'verified_at', 'date_joined', 'last_login', 'slug', 'updated_at']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_default_currency(self, obj):
        return obj.default_currency
    
    def get_profile_url(self, obj):
        """URL pública del perfil para SEO"""
        return obj.get_absolute_url()


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para perfil de usuario (detallado) con campos extendidos.
    """
    full_name = serializers.SerializerMethodField()
    wallet_balance = serializers.SerializerMethodField()
    profile_url = serializers.SerializerMethodField()  # 🆕 URL pública
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'full_name', 'first_name', 'last_name',
            'phone', 'city', 'neighborhood', 'country', 'gender', 'birth_date',
            'terms_accepted', 'default_currency', 'is_verified', 'can_withdraw', 
            'wallet_balance', 'is_active', 'date_joined',
            # 🆕 Campos SEO
            'slug', 'is_public', 'profile_url', 'updated_at'
        ]
        read_only_fields = ['id', 'is_verified', 'date_joined', 'slug', 'updated_at']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_profile_url(self, obj):
        """URL pública del perfil para SEO"""
        return obj.get_absolute_url()
    
    def get_wallet_balance(self, obj):
        try:
            from wallet.models import Wallet
            wallet = Wallet.objects.get(user=obj)
            return {
                'available': float(wallet.available_balance),
                'pending': float(wallet.pending_balance),
                'currency': wallet.currency
            }
        except:
            return None


class PublicArtistSerializer(serializers.ModelSerializer):
    """Serializer SEGURO para datos públicos de artistas."""
    full_name = serializers.SerializerMethodField()
    profile_url = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    songs_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'slug', 'full_name', 'first_name', 'last_name',
            'city', 'neighborhood', 'country', 'is_verified', 'is_public',
            'date_joined', 'profile_url', 'avatar_url', 'songs_count',
        ]
    
    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        return obj.username
    
    def get_profile_url(self, obj):
        return f"/perfil/{obj.slug or obj.username}/"
    
    def get_avatar_url(self, obj):
        try:
            profile = obj.profile
            if profile and profile.avatar_key:
                return f"https://cdn.djidjimusic.com/{profile.avatar_key}"
        except:
            pass
        return None
    
    def get_songs_count(self, obj):
        try:
            from api2.models import Song
            return Song.objects.filter(uploaded_by=obj, is_public=True).count()
        except:
            return 0


class ArtistProfileSerializer(serializers.ModelSerializer):
    """
    Serializer COMPLETO para perfil de artista.
    NO incluye bio/location/website (están en UserProfile).
    """
    full_name = serializers.SerializerMethodField()
    profile_url = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    songs = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'slug', 'full_name', 'first_name', 'last_name',
            'city', 'neighborhood', 'country',
            'is_verified', 'is_public', 'date_joined',
            'profile_url', 'avatar_url', 'songs', 'stats'
        ]
    
    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        return obj.username
    
    def get_profile_url(self, obj):
        return f"/perfil/{obj.slug or obj.username}/"
    
    def get_avatar_url(self, obj):
        try:
            profile = obj.profile
            if profile and profile.avatar_key:
                return f"https://cdn.djidjimusic.com/{profile.avatar_key}"
        except:
            pass
        return None
    
    def get_songs(self, obj):
        try:
            from api2.models import Song
            
            songs = Song.objects.filter(
                uploaded_by=obj,
                is_public=True
            ).order_by('-created_at')[:50]
            
            return [
                {
                    'id': song.id,
                    'title': song.title,
                    'artist': song.artist,
                    'genre': song.genre,
                    'duration': song.duration,
                    'plays_count': song.plays_count,
                    'likes_count': song.likes_count,
                    'downloads_count': song.downloads_count,
                    'category': song.category,
                    'price': float(song.price),
                    'price_display': song.formatted_price,
                    'is_purchasable': song.is_purchasable,
                    'created_at': song.created_at.isoformat() if song.created_at else None,
                    'file_key': song.file_key,
                    'image_key': song.image_key,
                }
                for song in songs
            ]
        except Exception:
            return []
    
    def get_stats(self, obj):
        try:
            from api2.models import Song, Like, PlayHistory, Download
            
            songs = Song.objects.filter(uploaded_by=obj)
            song_ids = list(songs.values_list('id', flat=True))
            
            return {
                'total_songs': len(song_ids),
                'total_plays': PlayHistory.objects.filter(song_id__in=song_ids).count() if song_ids else 0,
                'total_likes': Like.objects.filter(song_id__in=song_ids).count() if song_ids else 0,
                'total_downloads': Download.objects.filter(song_id__in=song_ids, is_confirmed=True).count() if song_ids else 0,
            }
        except Exception:
            return {'total_songs': 0, 'total_plays': 0, 'total_likes': 0, 'total_downloads': 0}
class UserLoginSerializer(serializers.Serializer):
    """
    Serializer para login de usuarios.
    """
    username = serializers.CharField()
    password = serializers.CharField(
        style={'input_type': 'password'}, 
        write_only=True
    )
    
    def validate(self, data):
        from django.contrib.auth import authenticate
        
        username = data.get('username')
        password = data.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError("Credenciales inválidas")
            if not user.is_active:
                raise serializers.ValidationError("Usuario desactivado")
        else:
            raise serializers.ValidationError(
                "Debe proporcionar username y password"
            )
        
        data['user'] = user
        return data
    
    def to_representation(self, instance):
        """Devolver tokens JWT en login con todos los campos"""
        user = instance['user']
        refresh = RefreshToken.for_user(user)
        
        return {
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "city": user.city,
                "neighborhood": user.neighborhood,
                "phone": user.phone,
                "country": user.country,
                "gender": user.gender,
                "birth_date": user.birth_date,
                "terms_accepted": user.terms_accepted,
                "is_verified": user.is_verified,
                "default_currency": user.default_currency,
                # 🆕 Campos SEO en respuesta de login
                "slug": user.slug,
                "is_public": user.is_public,
                "profile_url": user.get_absolute_url(),
            },
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
        }


class UserVisitSerializer(serializers.ModelSerializer):
    """
    Serializer para visitas de usuarios.
    """
    class Meta:
        model = UserVisit
        fields = '__all__'
        read_only_fields = ['id', 'fecha_visita']


class UserVerificationSerializer(serializers.Serializer):
    """
    Serializer para verificación de usuario (admin).
    """
    user_id = serializers.IntegerField()
    verified = serializers.BooleanField()
    
    def validate_user_id(self, value):
        try:
            user = CustomUser.objects.get(id=value)
            self.context['user'] = user
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Usuario no encontrado")
        return value
    
    def create(self, validated_data):
        user = self.context['user']
        
        if validated_data['verified']:
            user.verify()
        else:
            user.unverify()
        
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer para cambio de contraseña.
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True, 
        validators=[validate_password]
    )
    new_password2 = serializers.CharField(required=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError(
                {"new_password": "Las contraseñas nuevas no coinciden."}
            )
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Contraseña actual incorrecta.")
        return value
    
    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user
    
    
# musica/serializers.py - AÑADIR AL FINAL DEL ARCHIVO

