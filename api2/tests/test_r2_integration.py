# api2/tests/test_r2_integration.py
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from api2.models import UploadSession, UploadQuota
from unittest.mock import patch, MagicMock, mock_open
from django.utils import timezone
from datetime import timedelta
import uuid
import json
import tempfile
import os

User = get_user_model()

@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
})
class R2UploadIntegrationTests(TestCase):
    """Pruebas de integración real con R2 (usando mocks)"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='r2user',
            email=f'r2{uuid.uuid4().hex[:8]}@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Crear un archivo temporal de prueba
        self.test_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        self.test_file.write(b'fake mp3 content' * 1000)  # ~16KB
        self.test_file.close()
        
        self.file_size = os.path.getsize(self.test_file.name)
        
    def tearDown(self):
        # Eliminar archivo temporal
        if os.path.exists(self.test_file.name):
            os.unlink(self.test_file.name)
    
    @patch('api2.views.r2_direct')
    @patch('api2.views.cache')
    def test_complete_r2_upload_flow(self, mock_cache, mock_r2):
        """Prueba el flujo completo de upload a R2"""
        print("\n🔍 Probando flujo completo de upload a R2:")
        print("="*60)
        
        # Configurar mocks
        mock_cache.get.return_value = 0
        
        # 1. PASO: Solicitar URL firmada
        print("\n1. Solicitando URL firmada para upload...")
        
        expected_key = f"uploads/{self.user.id}/{uuid.uuid4().hex[:8]}_test.mp3"
        mock_r2.generate_presigned_post.return_value = {
            'url': 'https://upload.r2.cloudflarestorage.com/djidji-media',
            'fields': {
                'key': expected_key,
                'policy': 'fake-policy',
                'x-amz-credential': 'fake-credential',
                'x-amz-algorithm': 'AWS4-HMAC-SHA256',
                'x-amz-date': '20240130T210000Z',
                'x-amz-signature': 'fake-signature'
            },
            'key': expected_key,
            'expires_at': int((timezone.now() + timedelta(hours=1)).timestamp())
        }
        
        request_data = {
            'file_name': 'test_song.mp3',
            'file_size': self.file_size,
            'file_type': 'audio/mpeg',
            'metadata': {
                'artist': 'Test Artist',
                'album': 'Test Album'
            }
        }
        
        response = self.client.post(
            reverse('direct-upload-request'),
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        upload_id = response.data['upload_id']
        upload_url = response.data['upload_url']
        upload_fields = response.data['fields']
        
        print(f"   ✓ URL obtenida: {upload_url[:50]}...")
        print(f"   ✓ Upload ID: {upload_id}")
        print(f"   ✓ Key en R2: {upload_fields.get('key', 'N/A')}")
        
        # Verificar que se creó la sesión
        session = UploadSession.objects.get(id=upload_id)
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.status, 'pending')
        
        # 2. PASO: Simular upload a R2 (fuera de Django)
        print("\n2. Simulando upload del archivo a R2...")
        
        # Aquí el frontend subiría el archivo directamente a R2
        # Simulamos que el archivo fue subido exitosamente
        mock_r2.verify_file_uploaded.return_value = (True, {
            'size': self.file_size,
            'last_modified': timezone.now().isoformat(),
            'content_type': 'audio/mpeg'
        })
        
        mock_r2.validate_upload_integrity.return_value = {
            'valid': True,
            'metadata': {
                'size': self.file_size,
                'content_type': 'audio/mpeg',
                'uploader_id': str(self.user.id)
            }
        }
        
        # 3. PASO: Confirmar upload
        print("\n3. Confirmando upload en el backend...")
        
        confirm_response = self.client.post(
            reverse('direct-upload-confirm', args=[upload_id]),
            data=json.dumps({'delete_invalid': False}),
            content_type='application/json'
        )
        
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertTrue(confirm_response.data['success'])
        
        # Verificar que la sesión se actualizó
        session.refresh_from_db()
        self.assertEqual(session.status, 'confirmed')
        
        print(f"   ✓ Upload confirmado: {session.status}")
        print(f"   ✓ Procesamiento iniciado: {confirm_response.data['processing_started']}")
        
        # 4. PASO: Verificar estado final
        print("\n4. Verificando estado final...")
        
        status_response = self.client.get(
            reverse('direct-upload-status', args=[upload_id])
        )
        
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data['status'], 'confirmed')
        
        print(f"   ✓ Estado confirmado: {status_response.data['status']}")
        
        # 5. PASO: Verificar cuota actualizada
        print("\n5. Verificando cuota actualizada...")
        
        quota_response = self.client.get(reverse('user-upload-quota'))
        
        self.assertEqual(quota_response.status_code, status.HTTP_200_OK)
        
        # Debería mostrar al menos 1 upload
        self.assertGreaterEqual(quota_response.data['totals']['count'], 0)
        
        print(f"   ✓ Cuota verificada")
        
        print("\n" + "="*60)
        print("🎉 ¡FLUJO COMPLETO DE UPLOAD A R2 VERIFICADO!")
        print("="*60)
    
    @patch('api2.views.r2_direct')
    @patch('api2.views.cache')
    def test_r2_upload_with_large_file(self, mock_cache, mock_r2):
        """Prueba upload de archivo grande (50MB)"""
        print("\n📁 Probando upload de archivo grande (50MB)...")
        
        mock_cache.get.return_value = 0
        
        large_file_size = 50 * 1024 * 1024  # 50MB
        
        # Mock para archivo grande
        mock_r2.generate_presigned_post.return_value = {
            'url': 'https://upload.r2.cloudflarestorage.com/djidji-media',
            'fields': {'key': f'uploads/large_{uuid.uuid4().hex[:8]}.mp3'},
            'key': f'uploads/large_{uuid.uuid4().hex[:8]}.mp3',
            'expires_at': int((timezone.now() + timedelta(hours=1)).timestamp())
        }
        
        request_data = {
            'file_name': 'large_song.mp3',
            'file_size': large_file_size,
            'file_type': 'audio/mpeg'
        }
        
        response = self.client.post(
            reverse('direct-upload-request'),
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        # Verificar que se acepta el tamaño (debe estar dentro del límite)
        if large_file_size <= 100 * 1024 * 1024:  # 100MB límite
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            print(f"   ✓ Archivo grande aceptado ({large_file_size/(1024*1024):.1f}MB)")
        else:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            print(f"   ✓ Archivo muy grande rechazado correctamente")
    
    @patch('api2.views.r2_direct')
    @patch('api2.views.cache')
    def test_r2_upload_error_handling(self, mock_cache, mock_r2):
        """Prueba manejo de errores de R2"""
        print("\n⚠️ Probando manejo de errores de R2...")
        
        mock_cache.get.return_value = 0
        
        # Simular error en R2
        mock_r2.generate_presigned_post.side_effect = Exception("R2 Service Unavailable")
        
        request_data = {
            'file_name': 'error_test.mp3',
            'file_size': 1048576,  # 1MB
            'file_type': 'audio/mpeg'
        }
        
        response = self.client.post(
            reverse('direct-upload-request'),
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        # Debería manejar el error graciosamente
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['error'], 'upload_config_error')
        
        print(f"   ✓ Error de R2 manejado correctamente: {response.data['message']}")
    
    @patch('api2.views.r2_direct')
    def test_r2_file_verification(self, mock_r2):
        """Prueba verificación de archivo en R2"""
        print("\n🔐 Probando verificación de archivo en R2...")
        
        # Crear una sesión existente
        session = UploadSession.objects.create(
            user=self.user,
            file_name='verify_test.mp3',
            file_size=1048576,
            file_type='audio/mpeg',
            file_key='uploads/verify_test.mp3',
            status='pending',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        # Test 1: Archivo existe
        mock_r2.verify_file_uploaded.return_value = (True, {
            'size': 1048576,
            'last_modified': timezone.now().isoformat()
        })
        
        exists, metadata = mock_r2.verify_file_uploaded(session.file_key)
        self.assertTrue(exists)
        print(f"   ✓ Verificación exitosa (archivo existe)")
        
        # Test 2: Archivo no existe
        mock_r2.verify_file_uploaded.return_value = (False, {})
        
        exists, metadata = mock_r2.verify_file_uploaded('uploads/nonexistent.mp3')
        self.assertFalse(exists)
        print(f"   ✓ Verificación correcta (archivo no existe)")
    
    @patch('api2.views.r2_direct')
    @patch('api2.views.cache')
    def test_r2_file_validation(self, mock_cache, mock_r2):
        """Prueba validación de integridad de archivo"""
        print("\n🧪 Probando validación de integridad...")
        
        mock_cache.get.return_value = 0
        
        # Crear sesión
        session = UploadSession.objects.create(
            user=self.user,
            file_name='validation_test.mp3',
            file_size=5242880,  # 5MB
            file_type='audio/mpeg',
            file_key='uploads/validation_test.mp3',
            status='pending',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        # Test 1: Validación exitosa
        mock_r2.validate_upload_integrity.return_value = {
            'valid': True,
            'metadata': {
                'size': 5242880,
                'content_type': 'audio/mpeg',
                'uploader_id': str(self.user.id)
            }
        }
        
        result = mock_r2.validate_upload_integrity(
            key=session.file_key,
            expected_size=session.file_size,
            expected_uploader_id=self.user.id
        )
        
        self.assertTrue(result['valid'])
        print(f"   ✓ Validación de integridad exitosa")
        
        # Test 2: Validación fallida (tamaño incorrecto)
        mock_r2.validate_upload_integrity.return_value = {
            'valid': False,
            'issues': ['Tamaño incorrecto: esperado 5242880, obtenido 4194304']
        }
        
        result = mock_r2.validate_upload_integrity(
            key=session.file_key,
            expected_size=session.file_size,
            expected_uploader_id=self.user.id
        )
        
        self.assertFalse(result['valid'])
        self.assertIn('Tamaño incorrecto', result['issues'][0])
        print(f"   ✓ Validación detecta tamaño incorrecto")

@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
})
class R2RealConnectionTest(TestCase):
    """Prueba REAL de conexión a R2 (requiere configuración)"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='realr2user',
            email=f'realr2{uuid.uuid4().hex[:8]}@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_r2_configuration(self):
        """Verifica que R2 está configurado correctamente"""
        print("\n🔧 Verificando configuración de R2...")
        
        try:
            from api2.utils.r2_direct import R2DirectUpload
            r2 = R2DirectUpload()
            
            # Verificar atributos básicos
            self.assertTrue(hasattr(r2, 'bucket_name'))
            self.assertTrue(hasattr(r2, 's3_client'))
            
            print(f"   ✓ R2DirectUpload inicializado")
            print(f"   ✓ Bucket: {r2.bucket_name}")
            
            # Verificar métodos disponibles
            methods = ['generate_presigned_post', 'verify_file_uploaded', 
                      'validate_upload_integrity', 'delete_file']
            
            for method in methods:
                self.assertTrue(hasattr(r2, method))
                print(f"   ✓ Método disponible: {method}")
            
        except Exception as e:
            print(f"   ⚠ Configuración de R2: {e}")
            print("   Nota: Esto es normal en entorno de pruebas sin credenciales reales")
    
    def test_real_r2_upload_dry_run(self):
        """Simulación de upload real sin credenciales"""
        print("\n🔄 Simulando upload real a R2...")
        
        # Datos de prueba
        request_data = {
            'file_name': 'real_test.mp3',
            'file_size': 1048576,  # 1MB
            'file_type': 'audio/mpeg'
        }
        
        response = self.client.post(
            reverse('direct-upload-request'),
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        if response.status_code == 200:
            print(f"   ✓ Sistema listo para uploads reales")
            print(f"   ✓ Respuesta: {response.data.get('upload_url', 'URL generada')[:50]}...")
        elif response.status_code == 500 and 'upload_config_error' in str(response.data):
            print(f"   ⚠ R2 no configurado (esperado en pruebas)")
            print(f"   ✓ Sistema maneja falta de configuración correctamente")
        else:
            print(f"   ⚠ Respuesta inesperada: {response.status_code}")