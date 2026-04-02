# notifications/serializers.py
"""
Serializers para el sistema de notificaciones.
"""
from rest_framework import serializers
from django.utils import timezone
from django.utils.timesince import timesince
from .models import Notification, NotificationPreference, PushDevice


class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer para notificaciones.
    """
    type_display = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'type_display', 'title', 'message',
            'metadata', 'read', 'read_at', 'created_at', 'time_ago'
        ]
        read_only_fields = fields
    
    def get_type_display(self, obj):
        return dict(Notification.NOTIFICATION_TYPES).get(obj.type, obj.type)
    
    def get_time_ago(self, obj):
        now = timezone.now()
        return timesince(obj.created_at, now)


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """
    Serializer para preferencias de notificaciones.
    """
    class Meta:
        model = NotificationPreference
        fields = [
            'email_enabled', 'push_enabled', 'in_app_enabled',
            'quiet_hours_start', 'quiet_hours_end', 'preferences',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class PushDeviceSerializer(serializers.ModelSerializer):
    """
    Serializer para dispositivos push.
    """
    class Meta:
        model = PushDevice
        fields = ['id', 'device_type', 'token', 'is_active', 'user_agent', 'metadata', 'created_at', 'last_used']
        read_only_fields = ['id', 'created_at', 'last_used']


class MarkReadSerializer(serializers.Serializer):
    """
    Serializer para marcar notificaciones como leídas.
    """
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="IDs de notificaciones a marcar"
    )
    mark_all = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Marcar todas las notificaciones como leídas"
    )
    
    def validate(self, data):
        if not data.get('mark_all') and not data.get('notification_ids'):
            raise serializers.ValidationError(
                "Debe especificar notification_ids o mark_all=true"
            )
        return data


class PreferenceUpdateSerializer(serializers.Serializer):
    """
    Serializer para actualizar preferencias individuales.
    """
    channel = serializers.ChoiceField(choices=['email', 'push', 'in_app'])
    notification_type = serializers.ChoiceField(choices=Notification.NOTIFICATION_TYPES)
    enabled = serializers.BooleanField()


class PushDeviceRegisterSerializer(serializers.Serializer):
    """
    Serializer para registrar dispositivo push.
    """
    device_type = serializers.ChoiceField(choices=PushDevice.DEVICE_TYPES)
    token = serializers.CharField(max_length=255)
    user_agent = serializers.CharField(required=False, allow_blank=True)
    subscription_info = serializers.JSONField(required=False, help_text="Para web push")