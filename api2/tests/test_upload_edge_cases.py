# tests/test_upload_edge_cases.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from api2.models import UploadQuota, UploadSession
from unittest.mock import patch
import json
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class UploadEdgeCaseTests(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='edgeuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_upload_with_very_large_filename(self):
        """Prueba con nombre de archivo muy largo"""
        long_filename = 'a' * 500 + '.mp3'
        data = {
            'file_name': long_filename,
            'file_size': 1048576,
            'file_type': 'audio/mpeg'
        }
        
        url = reverse('direct-upload-request')
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        # Debería fallar por validación
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_upload_with_negative_file_size(self):
        """Prueba con tamaño de archivo negativo"""
        data = {
            'file_name': 'test.mp3',
            'file_size': -1000,  # Tamaño negativo
            'file_type': 'audio/mpeg'
        }
        
        url = reverse('direct-upload-request')
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_upload_with_zero_file_size(self):
        """Prueba con tamaño de archivo cero"""
        data = {
            'file_name': 'test.mp3',
            'file_size': 0,
            'file_type': 'audio/mpeg'
        }
        
        url = reverse('direct-upload-request')
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    @patch('api2.views.r2_direct')
    def test_upload_when_r2_service_down(self, mock_r2):
        """Prueba cuando el servicio R2 está caído"""
        mock_r2.generate_presigned_post.side_effect = Exception("R2 Service Unavailable")
        
        data = {
            'file_name': 'test.mp3',
            'file_size': 1048576,
            'file_type': 'audio/mpeg'
        }
        
        url = reverse('direct-upload-request')
        response = self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['error'], 'upload_config_error')
    
    def test_concurrent_upload_requests(self):
        """Simular solicitudes concurrentes para verificar race conditions"""
        # Esta prueba requiere herramientas adicionales como locust o threads
        # Por ahora verificamos la lógica básica
        
        data = {
            'file_name': 'test.mp3',
            'file_size': 1048576,
            'file_type': 'audio/mpeg'
        }
        
        url = reverse('direct-upload-request')
        
        # Primera solicitud
        response1 = self.client.post(url, data)
        
        # Segunda solicitud inmediata
        response2 = self.client.post(url, data)
        
        # Ambas deberían ser procesadas (dependiendo del rate limit)
        self.assertIn(response1.status_code, [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS])
    
    def test_expired_upload_confirmation(self):
        """Prueba confirmar upload expirado"""
        upload_session = UploadSession.objects.create(
            user=self.user,
            file_name='test.mp3',
            file_size=10485760,
            file_type='audio/mpeg',
            file_key='uploads/test_file.mp3',
            status='pending',
            expires_at=timezone.now() - timedelta(hours=1)  # Expired
        )
        
        url = reverse('direct-upload-confirm', args=[upload_session.id])
        response = self.client.post(url, {})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'cannot_confirm')