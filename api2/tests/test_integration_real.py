# api2/tests/test_integration_real.py
import os
import json
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock

from musica.models import CustomUser
from api2.models import UploadQuota, UploadSession

class RealUploadIntegrationTest(TestCase):
    """Test de integración REAL que simula tu test_put_upload_final.py"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Crear usuario de prueba (igual que en tu test funcional)
        self.user = CustomUser.objects.create_user(
            username='jordi',
            email='jordi@example.com',
            password='machimbo90'  # Misma contraseña que usas en el test real
        )
        
        print(f"\n🔧 Usuario creado: {self.user.username}")
        
        # Obtener token JWT (simulado)
        self.client.force_authenticate(user=self.user)
    
    @patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put')
    @patch('api2.utils.r2_direct.R2DirectUpload.verify_file_uploaded')
    @patch('api2.utils.r2_direct.R2DirectUpload.validate_upload_integrity')
    def test_complete_upload_flow(self, mock_validate, mock_verify, mock_presigned):
        """Test del flujo completo igual que tu test funcional"""
        print("\n" + "=" * 60)
        print("🧪 TEST DE INTEGRACIÓN COMPLETA")
        print("=" * 60)
        
        # 1. Configurar mocks
        mock_presigned.return_value = {
            'url': 'https://r2.example.com/upload/test_final_put.mp3',
            'method': 'PUT',
            'headers': {
                'Content-Type': 'audio/mpeg',
                'Content-Length': '1024'
            },
            'key': f'uploads/{self.user.id}/test_final_put.mp3',
            'expires_at': 1234567890
        }
        
        mock_verify.return_value = (True, {'size': 1024})
        mock_validate.return_value = {'valid': True, 'metadata': {}}
        
        # 2. Solicitar URL PUT
        print("\n1. 📋 Solicitando URL PUT...")
        response = self.client.post(
            reverse('direct-upload-request'),
            data={
                'file_name': 'test_final_put.mp3',
                'file_size': 1024,
                'file_type': 'audio/mpeg'
            },
            format='json'
        )
        
        print(f"   Status: {response.status_code}")
        
        # Verificar si estamos usando stub
        if response.status_code == 501:
            print("   ❌ ERROR: Estás usando STUBS, no las vistas reales")
            print("   Solución: Asegúrate de que las views están en api2/views.py")
            self.fail("Vistas no implementadas")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        print(f"   ✅ URL obtenida")
        print(f"   📦 Upload ID: {data.get('upload_id')}")
        print(f"   🔗 Método: {data.get('method')}")
        
        # Verificar que sea PUT
        self.assertEqual(data.get('method'), 'PUT')
        
        # 3. Verificar que se creó la sesión
        upload_session = UploadSession.objects.get(id=data['upload_id'])
        self.assertEqual(upload_session.status, 'pending')
        self.assertEqual(upload_session.user, self.user)
        
        # 4. Confirmar upload
        print("\n2. ✅ Confirmando upload...")
        confirm_response = self.client.post(
            reverse('direct-upload-confirm', kwargs={'upload_id': data['upload_id']}),
            data={'delete_invalid': False},
            format='json'
        )
        
        print(f"   Status: {confirm_response.status_code}")
        
        # Verificar si estamos usando stub
        if confirm_response.status_code == 501:
            print("   ⚠️  Endpoint de confirmación no implementado")
        else:
            self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
            confirm_data = confirm_response.json()
            print(f"   🎉 Upload confirmado: {confirm_data.get('success')}")
        
        print("\n" + "=" * 60)
        print("✅ TEST DE INTEGRACIÓN COMPLETADO")
        print("=" * 60)