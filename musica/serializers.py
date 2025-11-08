from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser, UserVisit

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
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
        ]

    def validate(self, attrs):
        # Verificar que las contraseñas coincidan
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})

        # Validar que el email es obligatorio (aunque ya es unique en el modelo)
        if not attrs.get("email"):
            raise serializers.ValidationError({"email": "El correo electrónico es obligatorio."})

        return attrs

    def create(self, validated_data):
        # Eliminar la confirmación de contraseña
        validated_data.pop("password2")
        
        # Crear el usuario con los datos validados
        user = CustomUser.objects.create_user(**validated_data)
        return user

    def to_representation(self, instance):
        """Personaliza la respuesta para incluir los tokens JWT."""
        refresh = RefreshToken.for_user(instance)
        return {
            "user": {
                "username": instance.username,
                "email": instance.email,
                "first_name": instance.first_name,
                "last_name": instance.last_name,
                "city": instance.city,
                "neighborhood": instance.neighborhood,
                "phone": instance.phone,
            },
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
        }

class UserVisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserVisit
        fields = '__all__'


