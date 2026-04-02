from django.contrib import admin

# Register your models here.
# notifications/admin.py
"""
Panel de administración para notificaciones.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Notification, NotificationPreference, PushDevice


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title_preview', 'type_badge', 'read', 'created_at', 'sent_at']
    list_filter = ['type', 'read', 'created_at']
    search_fields = ['user__email', 'user__username', 'title', 'message']
    readonly_fields = ['id', 'created_at', 'sent_at', 'channels']
    
    fieldsets = (
        ('Información', {
            'fields': ('user', 'type', 'title', 'message')
        }),
        ('Metadatos', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('read', 'read_at', 'sent_at', 'channels')
        }),
        ('Auditoría', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def title_preview(self, obj):
        return obj.title[:50]
    title_preview.short_description = 'Título'
    
    def type_badge(self, obj):
        colors = {
            'purchase': '#28a745',
            'hold_released': '#17a2b8',
            'new_comment': '#fd7e14',
            'low_balance': '#dc3545',
        }
        color = colors.get(obj.type, '#6c757d')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{}</span>',
            color,
            obj.get_type_display()
        )
    type_badge.short_description = 'Tipo'
    
    actions = ['mark_as_read', 'resend_notifications']
    
    @admin.action(description='Marcar como leídas')
    def mark_as_read(self, request, queryset):
        updated = queryset.update(read=True, read_at=timezone.now())
        self.message_user(request, f'{updated} notificaciones marcadas como leídas')
    
    @admin.action(description='Reenviar notificaciones')
    def resend_notifications(self, request, queryset):
        from .tasks import send_notification_task
        count = 0
        for notification in queryset:
            send_notification_task.delay(notification.id)
            count += 1
        self.message_user(request, f'{count} notificaciones encoladas para reenvío')


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_enabled', 'push_enabled', 'in_app_enabled', 'updated_at']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PushDevice)
class PushDeviceAdmin(admin.ModelAdmin):
    list_display = ['user', 'device_type', 'token_preview', 'is_active', 'last_used']
    list_filter = ['device_type', 'is_active', 'created_at']
    search_fields = ['user__email', 'user__username', 'token']
    readonly_fields = ['created_at', 'last_used']
    
    def token_preview(self, obj):
        if len(obj.token) > 30:
            return obj.token[:30] + '...'
        return obj.token
    token_preview.short_description = 'Token'
    
    actions = ['activate_devices', 'deactivate_devices']
    
    @admin.action(description='Activar dispositivos')
    def activate_devices(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} dispositivos activados')
    
    @admin.action(description='Desactivar dispositivos')
    def deactivate_devices(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} dispositivos desactivados')