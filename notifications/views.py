from django.shortcuts import render

# Create your views here.
# notifications/views.py
"""
Vistas para el sistema de notificaciones.
"""
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from django.utils import timezone
from .models import Notification, NotificationPreference, PushDevice
from .serializers import (
    NotificationSerializer, NotificationPreferenceSerializer,
    PushDeviceSerializer, MarkReadSerializer, PreferenceUpdateSerializer,
    PushDeviceRegisterSerializer
)


class NotificationListView(generics.ListAPIView):
    """
    Listar notificaciones del usuario.
    GET /api/notifications/
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)
        
        read_filter = self.request.query_params.get('read')
        if read_filter is not None:
            if read_filter.lower() == 'true':
                queryset = queryset.filter(read=True)
            elif read_filter.lower() == 'false':
                queryset = queryset.filter(read=False)
        
        notification_type = self.request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(type=notification_type)
        
        limit = self.request.query_params.get('limit', 50)
        try:
            limit = int(limit)
            if limit > 200:
                limit = 200
            queryset = queryset[:limit]
        except ValueError:
            pass
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        unread_count = Notification.objects.filter(
            user=request.user,
            read=False
        ).count()
        
        return Response({
            'results': serializer.data,
            'unread_count': unread_count,
            'total': queryset.count()
        })


class NotificationDetailView(generics.RetrieveAPIView):
    """
    Obtener detalle de una notificación.
    GET /api/notifications/<id>/
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkReadView(APIView):
    """
    Marcar notificaciones como leídas.
    POST /api/notifications/mark-read/
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def post(self, request):
        serializer = MarkReadSerializer(data=request.data)
        
        if serializer.is_valid():
            mark_all = serializer.validated_data.get('mark_all', False)
            notification_ids = serializer.validated_data.get('notification_ids', [])
            
            if mark_all:
                updated = Notification.objects.filter(
                    user=request.user,
                    read=False
                ).update(read=True, read_at=timezone.now())
                message = f"{updated} notificaciones marcadas como leídas"
            else:
                updated = Notification.objects.filter(
                    user=request.user,
                    id__in=notification_ids,
                    read=False
                ).update(read=True, read_at=timezone.now())
                message = f"{updated} notificaciones marcadas como leídas"
            
            return Response({
                "message": message,
                "updated": updated,
                "unread_count": Notification.objects.filter(
                    user=request.user, read=False
                ).count()
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NotificationPreferencesView(generics.RetrieveUpdateAPIView):
    """
    Obtener y actualizar preferencias de notificaciones.
    GET/PUT /api/notifications/preferences/
    """
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get_object(self):
        prefs, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return prefs


class NotificationPreferenceUpdateView(APIView):
    """
    Actualizar preferencia específica.
    POST /api/notifications/preferences/update/
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def post(self, request):
        serializer = PreferenceUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
            prefs.set_preference(
                channel=serializer.validated_data['channel'],
                notification_type=serializer.validated_data['notification_type'],
                value=serializer.validated_data['enabled']
            )
            return Response({"status": "updated"})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PushDeviceView(generics.ListCreateAPIView):
    """
    Listar y registrar dispositivos push.
    GET/POST /api/notifications/devices/
    """
    serializer_class = PushDeviceSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get_queryset(self):
        return PushDevice.objects.filter(user=self.request.user, is_active=True)
    
    def create(self, request, *args, **kwargs):
        serializer = PushDeviceRegisterSerializer(data=request.data)
        
        if serializer.is_valid():
            device, created = PushDevice.objects.update_or_create(
                user=request.user,
                token=serializer.validated_data['token'],
                defaults={
                    'device_type': serializer.validated_data['device_type'],
                    'user_agent': serializer.validated_data.get('user_agent', ''),
                    'metadata': {
                        'subscription_info': serializer.validated_data.get('subscription_info', {})
                    },
                    'is_active': True
                }
            )
            
            return Response(
                PushDeviceSerializer(device).data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PushDeviceDetailView(generics.DestroyAPIView):
    """
    Eliminar un dispositivo push.
    DELETE /api/notifications/devices/<id>/
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get_queryset(self):
        return PushDevice.objects.filter(user=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        device = self.get_object()
        device.is_active = False
        device.save(update_fields=['is_active'])
        return Response(
            {"message": "Dispositivo desactivado"},
            status=status.HTTP_200_OK
        )


class UnreadCountView(APIView):
    """
    Obtener número de notificaciones no leídas.
    GET /api/notifications/unread-count/
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get(self, request):
        count = Notification.objects.filter(
            user=request.user,
            read=False
        ).count()
        return Response({"unread_count": count})


class NotificationGroupedView(APIView):
    """
    Agrupar notificaciones por tipo.
    GET /api/notifications/grouped/
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get(self, request):
        notifications = Notification.objects.filter(user=request.user)[:100]
        
        groups = {}
        for notif in notifications:
            type_key = notif.type
            if type_key not in groups:
                groups[type_key] = {
                    'type': notif.type,
                    'type_display': dict(Notification.NOTIFICATION_TYPES).get(type_key),
                    'count': 0,
                    'latest': None,
                    'latest_created_at': None
                }
            groups[type_key]['count'] += 1
            if not groups[type_key]['latest_created_at'] or notif.created_at > groups[type_key]['latest_created_at']:
                groups[type_key]['latest'] = NotificationSerializer(notif).data
                groups[type_key]['latest_created_at'] = notif.created_at
        
        result = []
        for group in groups.values():
            result.append({
                'type': group['type'],
                'type_display': group['type_display'],
                'count': group['count'],
                'latest': group['latest']
            })
        
        return Response(result)