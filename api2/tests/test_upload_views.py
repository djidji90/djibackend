# api2/tests/test_upload_views.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock
import json

# Importa tu CustomUser en lugar del User de Django
from musica.models import CustomUser
from api2.models import UploadQuota, UploadSession

class DirectUploadTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Usa CustomUser en lugar de User
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # URLs para testing - USANDO LOS NOMBRES CORRECTOS
        self.request_url = reverse('direct-upload-request')  # ← Cambiado
        self.quota_url = reverse('user-upload-quota')  # ← Cambiado
        self.confirm_url_name = 'direct-upload-confirm'  # Para usar con reverse más tarde
        self.status_url_name = 'direct-upload-status'    # Para usar con reverse más tarde
        self.cancel_url_name = 'direct-upload-cancel'    # Para usar con reverse más tarde
    
    def test_get_quota(self):
        """Test obtener información de cuota"""
        print(f"Testing URL: {self.quota_url}")
        response = self.client.get(self.quota_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_quota', response.data)
        self.assertIn('used_quota', response.data)
        print("✅ Test de cuota pasado")
        print(f"Response data: {response.data}")
    
    @patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put')
    def test_request_upload_url(self, mock_presigned_put):
        """Test solicitar URL de upload PUT"""
        print(f"\nTesting URL: {self.request_url}")
        
        # Mock del servicio R2
        mock_presigned_put.return_value = {
            'url': 'https://r2.example.com/upload/test-key',
            'method': 'PUT',
            'headers': {
                'Content-Type': 'audio/mpeg',
                'Content-Length': '1048576'
            },
            'key': 'test-key',
            'expires_at': timezone.now().timestamp() + 3600
        }
        
        # Datos de prueba
        data = {
            'file_name': 'test_song.mp3',
            'file_size': 1048576,  # 1MB
            'file_type': 'audio/mpeg',
            'metadata': {
                'original_name': 'mi_cancion.mp3'
            }
        }
        
        response = self.client.post(
            self.request_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        print(f"Response status: {response.status_code}")
        
        # Si falla, muestra más detalles
        if response.status_code != 200:
            print(f"Error response: {response.data}")
        
        # Verificaciones
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['success'], True)
        self.assertEqual(response.data['method'], 'PUT')  # ✅ Debe ser PUT
        self.assertIn('upload_url', response.data)
        self.assertIn('headers', response.data)
        self.assertIn('Content-Type', response.data['headers'])
        print("✅ Test de solicitud de URL pasado")
    
    def test_request_upload_url_invalid_data(self):
        """Test con datos inválidos"""
        print(f"\nTesting invalid data on URL: {self.request_url}")
        
        data = {
            'file_name': '',  # Vacío
            'file_size': -100  # Tamaño negativo
        }
        
        response = self.client.post(
            self.request_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('errors', response.data)
        print("✅ Test de datos inválidos pasado")
    
    @patch('django.core.cache.cache.get')
    @patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put')
    def test_rate_limiting(self, mock_presigned_put, mock_cache_get):
        """Test del rate limiting por IP"""
        print(f"\nTesting rate limiting on URL: {self.request_url}")
        
        # Mock del servicio R2 (aunque no se usará debido al rate limit)
        mock_presigned_put.return_value = {
            'url': 'https://example.com',
            'method': 'PUT',
            'headers': {},
            'key': 'test',
            'expires_at': 1234567890
        }
        
        # Simular IP que ya hizo muchas solicitudes
        mock_cache_get.return_value = 51
        
        data = {
            'file_name': 'test.mp3',
            'file_size': 1048576,
            'file_type': 'audio/mpeg'
        }
        
        response = self.client.post(
            self.request_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('rate_limit_exceeded', response.data['error'])
        print("✅ Test de rate limiting pasado")
    
    @patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put')
    def test_quota_exceeded(self, mock_presigned_put):
        """Test cuando se excede la cuota"""
        print(f"\nTesting quota exceeded on URL: {self.request_url}")
        
        # Configurar cuota para que esté casi llena
        quota, created = UploadQuota.objects.get_or_create(user=self.user)
        quota.used_quota = quota.total_quota - 512000  # Deja solo 0.5MB libres
        quota.save()
        
        print(f"Quota setup: {quota.used_quota}/{quota.total_quota}")
        
        # Mock del servicio R2
        mock_presigned_put.return_value = {
            'url': 'https://r2.example.com/upload/test-key',
            'method': 'PUT',
            'headers': {
                'Content-Type': 'audio/mpeg',
                'Content-Length': '1048576'  # 1MB, mayor que lo disponible
            },
            'key': 'test-key',
            'expires_at': timezone.now().timestamp() + 3600
        }
        
        data = {
            'file_name': 'large_song.mp3',
            'file_size': 1048576,  # 1MB (más de lo disponible)
            'file_type': 'audio/mpeg'
        }
        
        response = self.client.post(
            self.request_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        print(f"Quota response status: {response.status_code}")
        
        # Debería fallar con error de cuota
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('quota_exceeded', response.data['error'])
        print("✅ Test de cuota excedida pasado")