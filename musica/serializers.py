# users/serializers.py
"""
Serializers para la app de usuarios.
"""
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

# ✅ IMPORTACIONES CORREGIDAS
from .models import CustomUser, UserVisit  # ← Esto faltaba


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
            "gender",          # 🆕 NUEVO
            "birth_date",      # 🆕 NUEVO
            "terms_accepted",  # 🆕 NUEVO
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

        # 🆕 Validar fecha de nacimiento
        birth_date = attrs.get("birth_date")
        if birth_date and birth_date > timezone.now().date():
            raise serializers.ValidationError(
                {"birth_date": "La fecha de nacimiento no puede ser futura."}
            )

        # 🆕 Validar género
        gender = attrs.get("gender")
        if gender and gender not in ['M', 'F', 'O']:
            raise serializers.ValidationError(
                {"gender": "Género inválido. Debe ser M, F u O."}
            )

        return attrs

    def create(self, validated_data):
        # Eliminar la confirmación de contraseña
        validated_data.pop("password2")
        
        # Asegurar que terms_accepted sea booleano
        validated_data['terms_accepted'] = bool(validated_data.get('terms_accepted', False))
        
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
                "country": instance.country,
                "gender": instance.gender,                    # 🆕 NUEVO
                "birth_date": instance.birth_date,            # 🆕 NUEVO
                "terms_accepted": instance.terms_accepted,    # 🆕 NUEVO
                "is_verified": instance.is_verified,
                "default_currency": instance.default_currency,
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
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'phone', 'city', 'neighborhood', 'country', 'gender', 'birth_date',
            'terms_accepted', 'default_currency', 'is_verified', 'can_withdraw', 
            'verified_at', 'is_active', 'date_joined', 'last_login'
        ]
        read_only_fields = ['id', 'is_verified', 'verified_at', 'date_joined', 'last_login']
    
    def get_full_name(self, obj):
        return obj.full_name
    
    def get_default_currency(self, obj):
        return obj.default_currency


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer para perfil de usuario (detallado) con campos extendidos.
    """
    full_name = serializers.SerializerMethodField()
    wallet_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'full_name', 'first_name', 'last_name',
            'phone', 'city', 'neighborhood', 'country', 'gender', 'birth_date',
            'terms_accepted', 'default_currency', 'is_verified', 'can_withdraw', 
            'wallet_balance', 'is_active', 'date_joined'
        ]
        read_only_fields = ['id', 'is_verified', 'date_joined']
    
    def get_full_name(self, obj):
        return obj.full_name
    
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
                "gender": user.gender,                    # 🆕 NUEVO
                "birth_date": user.birth_date,            # 🆕 NUEVO
                "terms_accepted": user.terms_accepted,    # 🆕 NUEVO
                "is_verified": user.is_verified,
                "default_currency": user.default_currency,
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