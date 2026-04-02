# notifications/urls.py
"""
URLs para el sistema de notificaciones.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Notificaciones
    path('', views.NotificationListView.as_view(), name='notification-list'),
    path('<uuid:pk>/', views.NotificationDetailView.as_view(), name='notification-detail'),
    path('mark-read/', views.NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('unread-count/', views.UnreadCountView.as_view(), name='notification-unread-count'),
    path('grouped/', views.NotificationGroupedView.as_view(), name='notification-grouped'),
    
    # Preferencias
    path('preferences/', views.NotificationPreferencesView.as_view(), name='notification-preferences'),
    path('preferences/update/', views.NotificationPreferenceUpdateView.as_view(), name='notification-preference-update'),
    
    # Dispositivos push
    path('devices/', views.PushDeviceView.as_view(), name='push-device-list'),
    path('devices/<int:pk>/', views.PushDeviceDetailView.as_view(), name='push-device-detail'),
]