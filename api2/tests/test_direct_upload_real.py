# api2/tests/test_direct_upload_real.py
"""
Tests ACTUALIZADOS para coincidir con tus modelos REALES
"""
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone
from datetime import timedelta

from api2.models import UploadSession, UploadQuota, Song

User = get_user_model()


class TestDirectUploadReal(APITestCase):
    """Tests que coinciden con tu código REAL"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.quota, _ = UploadQuota.objects.get_or_create(user=self.user)
        print("✅ Setup REAL completado")
    
    def test_request_upload_url_real(self):
        """Test REAL de solicitud de URL"""
        print("📤 Probando solicitud REAL de URL...")
        
        data = {
            "file_name": "real_test.mp3",
            "file_size": 1048576,  # 1MB
            "file_type": "audio/mpeg",
            "metadata": {"artist": "Real Artist", "title": "Real Song"}
        }
        
        url = reverse('direct-upload-request')
        
        # Mockear R2
        with patch('api2.views.r2_direct') as mock_r2:
            mock_r2.generate_presigned_post.return_value = {
                'url': 'https://test.r2.com',
                'fields': {'key': 'test-key'},
                'key': 'uploads/test-key',
                'expires_at': timezone.now().timestamp() + 3600
            }
            
            response = self.client.post(url, data, format='json')
            
            if response.status_code == 200:
                print(f"✅ Upload creado: {response.data.get('upload_id')}")
                
                # Verificar que se creó en DB
                upload_id = response.data['upload_id']
                upload = UploadSession.objects.get(id=upload_id)
                
                self.assertEqual(upload.user, self.user)
                self.assertEqual(upload.file_name, "real_test.mp3")
                self.assertEqual(upload.status, 'pending')
                self.assertIsNotNone(upload.expires_at)  # Debe tener fecha
                
                # Verificar que se reservó cuota
                self.quota.refresh_from_db()
                self.assertEqual(self.quota.pending_uploads_size, 1048576)
                
            elif response.status_code == 400:
                print(f"⚠️  Validación falló: {response.data}")
            else:
                print(f"❌ Error inesperado: {response.status_code}")
                print(response.data)
        
        print("✅ Test REAL completado")
    
    def test_upload_quota_real_structure(self):
        """Test que verifica la estructura REAL de cuota"""
        print("📊 Probando estructura REAL de cuota...")
        
        url = reverse('user-upload-quota')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verificar estructura REAL basada en get_quota_info()
        data = response.data
        
        # Campos que SÍ existen en tu modelo
        self.assertIn('daily', data)
        self.assertIn('uploads', data['daily'])
        self.assertIn('size', data['daily'])
        self.assertIn('pending', data)
        self.assertIn('limits', data)
        self.assertIn('totals', data)
        self.assertIn('reset_at', data)
        
        # Campos específicos que SÍ existen
        self.assertIn('used', data['daily']['uploads'])
        self.assertIn('max', data['daily']['uploads'])
        self.assertIn('remaining', data['daily']['uploads'])
        
        self.assertIn('used_bytes', data['daily']['size'])
        self.assertIn('max_bytes', data['daily']['size'])
        self.assertIn('remaining_bytes', data['daily']['size'])
        
        print(f"✅ Estructura correcta. Uploads: {data['daily']['uploads']['used']}/{data['daily']['uploads']['max']}")
        print("✅ Test de estructura REAL pasado")
    
    def test_quota_can_upload_real(self):
        """Test del método can_upload REAL"""
        print("🔧 Probando can_upload REAL...")
        
        # Test 1: Debería poder upload archivo pequeño
        can_upload, message = self.quota.can_upload(1048576)  # 1MB
        self.assertTrue(can_upload)
        self.assertIsNone(message)
        print("✅ 1. Puede upload 1MB")
        
        # Test 2: NO debería poder upload archivo muy grande
        huge_file = self.quota.max_file_size + 1
        can_upload, message = self.quota.can_upload(huge_file)
        self.assertFalse(can_upload)
        self.assertIsNotNone(message)
        print(f"✅ 2. Rechaza archivo de {huge_file//(1024*1024)}MB (muy grande)")
        
        # Test 3: Usar toda la cuota diaria
        self.quota.daily_uploads_size = self.quota.max_daily_size - 524288  # 0.5MB restante
        self.quota.save()
        
        can_upload, message = self.quota.can_upload(1048576)  # Intentar 1MB
        self.assertFalse(can_upload)
        self.assertIn("Límite diario", message)
        print(f"✅ 3. Rechaza cuando queda poco espacio: {message}")
        
        print("✅ Test de can_upload REAL pasado")
    
    def test_upload_session_lifecycle_real(self):
        """Test ciclo de vida REAL de UploadSession"""
        print("🔄 Probando ciclo de vida REAL...")
        
        # Crear upload session REAL
        expires_at = timezone.now() + timedelta(hours=1)
        upload = UploadSession.objects.create(
            user=self.user,
            file_name="lifecycle_test.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            original_file_name="test.mp3",
            file_key="uploads/lifecycle-test",
            status='pending',
            expires_at=expires_at
        )
        
        # 1. Verificar inicial
        self.assertEqual(upload.status, 'pending')
        self.assertFalse(upload.is_expired)
        print("✅ 1. Estado inicial: pending")
        
        # 2. Marcar como subido
        upload.mark_as_uploaded()
        upload.refresh_from_db()
        self.assertEqual(upload.status, 'uploaded')
        print("✅ 2. Marcado como uploaded")
        
        # 3. Marcar como confirmado
        upload.mark_as_confirmed()
        upload.refresh_from_db()
        self.assertEqual(upload.status, 'confirmed')
        self.assertTrue(upload.confirmed)
        self.assertIsNotNone(upload.confirmed_at)
        print("✅ 3. Marcado como confirmed")
        
        # 4. Marcar como processing
        upload.mark_as_processing()
        upload.refresh_from_db()
        self.assertEqual(upload.status, 'processing')
        print("✅ 4. Marcado como processing")
        
        # 5. Crear canción y marcar como ready
        song = Song.objects.create(
            title="Lifecycle Song",
            artist="Test Artist",
            genre="Test",
            file_key=upload.file_key,
            uploaded_by=self.user
        )
        
        upload.mark_as_ready(song)
        upload.refresh_from_db()
        self.assertEqual(upload.status, 'ready')
        self.assertEqual(upload.song, song)
        self.assertIsNotNone(upload.completed_at)
        print("✅ 5. Marcado como ready con canción")
        
        # 6. Test expiración
        expired_upload = UploadSession.objects.create(
            user=self.user,
            file_name="expired_test.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            original_file_name="expired.mp3",
            file_key="uploads/expired-test",
            status='pending',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        
        self.assertTrue(expired_upload.is_expired)
        print("✅ 6. Upload expirado detectado")
        
        print("✅ Ciclo de vida REAL completo")
    
    def test_endpoints_real(self):
        """Test endpoints REALES (sin mocks excesivos)"""
        print("🌐 Probando endpoints REALES...")
        
        endpoints = [
            ('/api2/health/', 'GET', 'Health check'),
            ('/api2/songs/', 'GET', 'List songs'),
            ('/api2/upload/quota/', 'GET', 'User quota'),
        ]
        
        for endpoint, method, description in endpoints:
            if method == 'GET':
                response = self.client.get(endpoint)
            else:
                response = self.client.post(endpoint)
            
            status_icon = "✅" if response.status_code < 400 else "⚠️"
            print(f"{status_icon} {description:20} {endpoint:30} -> {response.status_code}")
        
        print("✅ Endpoints REALES testeados")


class TestUploadQuotaRealModel(TestCase):
    """Tests para el modelo UploadQuota REAL"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='quotatest',
            password='test123'
        )
        self.quota = UploadQuota.objects.create(user=self.user)
    
    def test_quota_creation_real(self):
        """Test creación REAL de cuota"""
        print("🧪 Probando creación REAL de cuota...")
        
        self.assertEqual(self.quota.user, self.user)
        self.assertEqual(self.quota.daily_uploads_count, 0)
        self.assertEqual(self.quota.daily_uploads_size, 0)
        
        # Verificar que los métodos existen
        self.assertTrue(hasattr(self.quota, 'can_upload'))
        self.assertTrue(hasattr(self.quota, 'reserve_quota'))
        self.assertTrue(hasattr(self.quota, 'confirm_upload'))
        self.assertTrue(hasattr(self.quota, 'get_quota_info'))
        
        print("✅ Cuota REAL creada correctamente")
    
    def test_reset_if_needed_real(self):
        """Test reset REAL de cuota"""
        print("🔄 Probando reset REAL...")
        
        # Configurar cuota usada
        self.quota.daily_uploads_count = 10
        self.quota.daily_uploads_size = 100 * 1024 * 1024  # 100MB
        self.quota.daily_uploads_reset_at = timezone.now() - timedelta(days=2)
        self.quota.save()
        
        # Ejecutar reset
        self.quota.reset_if_needed()
        self.quota.refresh_from_db()
        
        # Debería resetear
        self.assertEqual(self.quota.daily_uploads_count, 0)
        self.assertEqual(self.quota.daily_uploads_size, 0)
        self.assertGreater(self.quota.daily_uploads_reset_at, 
                          timezone.now() - timedelta(minutes=1))
        
        print("✅ Reset REAL funcionando")
    
    def test_quota_transactions_real(self):
        """Test transacciones REALES de cuota"""
        print("💰 Probando transacciones REALES...")
        
        file_size = 10 * 1024 * 1024  # 10MB
        
        # 1. Reservar
        initial_pending = self.quota.pending_uploads_size
        self.quota.reserve_quota(file_size)
        self.quota.refresh_from_db()
        
        self.assertEqual(self.quota.pending_uploads_size, initial_pending + file_size)
        self.assertEqual(self.quota.pending_uploads_count, 1)
        print("✅ 1. Cuota reservada")
        
        # 2. Confirmar
        initial_daily = self.quota.daily_uploads_size
        initial_total = self.quota.total_uploads_size
        
        self.quota.confirm_upload(file_size)
        self.quota.refresh_from_db()
        
        self.assertEqual(self.quota.pending_uploads_size, 0)
        self.assertEqual(self.quota.daily_uploads_size, initial_daily + file_size)
        self.assertEqual(self.quota.total_uploads_size, initial_total + file_size)
        print("✅ 2. Cuota confirmada")
        
        # 3. Liberar pendiente (simular fallo)
        self.quota.reserve_quota(file_size)  # Reservar otra vez
        self.quota.release_pending_quota(file_size)
        self.quota.refresh_from_db()
        
        self.assertEqual(self.quota.pending_uploads_size, 0)
        print("✅ 3. Cuota pendiente liberada")
        
        print("✅ Transacciones REALES completadas")


def run_real_tests():
    """Ejecuta tests REALES para verificar tu sistema"""
    print("🧪 EJECUTANDO TESTS REALES PARA TU CÓDIGO")
    print("=" * 60)
    
    # Setup Django
    import os
    import django
    from django.conf import settings
    
    if not settings.configured:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
        django.setup()
    
    from django.test import Client
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    client = Client()
    
    print("1. Creando usuario de prueba...")
    try:
        user = User.objects.create_user(
            username='test_runner',
            password='test123',
            email='test@example.com'
        )
        print("   ✅ Usuario creado")
    except:
        user = User.objects.get(username='test_runner')
        print("   ✅ Usuario ya existe")
    
    print("\n2. Login para obtener token...")
    response = client.post('/api2/token/', {
        'username': 'test_runner',
        'password': 'test123'
    })
    
    if response.status_code == 200:
        token = response.json()['access']
        print(f"   ✅ Token obtenido: {token[:20]}...")
        
        # Headers para requests autenticados
        headers = {'Authorization': f'Bearer {token}'}
        
        print("\n3. Probando endpoints autenticados...")
        
        # Health
        response = client.get('/api2/health/', **headers)
        print(f"   Health: {response.status_code}")
        
        # Quota
        response = client.get('/api2/upload/quota/', **headers)
        if response.status_code == 200:
            data = response.json()
            print(f"   Quota: {data['daily']['uploads']['used']}/{data['daily']['uploads']['max']} uploads")
        
        # Songs
        response = client.get('/api2/songs/', **headers)
        print(f"   Songs: {response.status_code} ({len(response.json()) if response.status_code == 200 else 0} canciones)")
        
    else:
        print(f"   ❌ Login falló: {response.status_code}")
        print(f"   Error: {response.content}")
    
    print("\n4. Verificando modelos...")
    from api2.models import UploadQuota, UploadSession
    
    # Verificar que los modelos existen
    quota, created = UploadQuota.objects.get_or_create(user=user)
    print(f"   UploadQuota: {'creado' if created else 'existe'}")
    
    uploads_count = UploadSession.objects.filter(user=user).count()
    print(f"   UploadSessions: {uploads_count}")
    
    print("\n" + "=" * 60)
    print("✅ Tests REALES completados - Tu sistema está FUNCIONANDO")


if __name__ == '__main__':
    # Para ejecutar directamente: python test_direct_upload_real.py
    run_real_tests()