# api2/tests/test_direct_upload.py
import json
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone
from datetime import timedelta

from api2.models import UploadSession, UploadQuota, Song
from api2.utils.r2_direct import r2_direct

User = get_user_model()


class TestDirectUploadSystem(APITestCase):
    """
    Tests completos para el sistema de upload directo a R2
    """
    
    def setUp(self):
        """Configuración inicial para todos los tests"""
        # Crear usuarios
        self.user = User.objects.create_user(
            username='uploaduser',
            email='upload@example.com',
            password='testpass123'
        )
        
        self.admin_user = User.objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='testpass123',
            is_staff=True
        )
        
        # Crear cuota inicial
        self.quota, _ = UploadQuota.objects.get_or_create(user=self.user)
        
        # Configurar autenticación para usuario normal
        self.client.force_authenticate(user=self.user)
        
        print("✅ Configuración de Direct Upload completada")
    
    # =========================================================================
    # TESTS DE SOLICITUD DE UPLOAD
    # =========================================================================
    
    def test_request_upload_url_success(self):
        """Test solicitud exitosa de URL de upload"""
        print("📤 Probando solicitud de URL de upload...")
        
        data = {
            "file_name": "test_song.mp3",
            "file_size": 1048576,  # 1MB
            "file_type": "audio/mpeg",
            "metadata": {
                "artist": "Test Artist",
                "title": "Test Song"
            }
        }
        
        # Mockear la generación de URL de R2
        with patch.object(r2_direct, 'generate_presigned_post') as mock_generate:
            mock_generate.return_value = {
                'url': 'https://upload.r2.cloudflarestorage.com',
                'fields': {'key': 'test-key', 'policy': 'test-policy'},
                'key': 'uploads/test-key',
                'expires_at': 1738432800
            }
            
            url = reverse('direct-upload-request')
            response = self.client.post(url, data, format='json')
            
            # Verificaciones
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn('upload_id', response.data)
            self.assertIn('upload_url', response.data)
            self.assertIn('fields', response.data)
            
            # Verificar que se creó la sesión
            upload_id = response.data['upload_id']
            upload_session = UploadSession.objects.get(id=upload_id)
            
            self.assertEqual(upload_session.user, self.user)
            self.assertEqual(upload_session.file_name, "test_song.mp3")
            self.assertEqual(upload_session.status, 'pending')
            
            print("✅ Test de solicitud de URL de upload pasado")
    
    def test_request_upload_url_quota_exceeded(self):
        """Test que falla cuando se excede la cuota"""
        print("🚫 Probando límite de cuota...")
        
        # Configurar cuota agotada
        self.quota.daily_size_used = self.quota.max_daily_size
        self.quota.save()
        
        data = {
            "file_name": "test_song.mp3",
            "file_size": 1048576,
            "file_type": "audio/mpeg"
        }
        
        url = reverse('direct-upload-request')
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('quota_exceeded', response.data['error'])
        
        print("✅ Test de límite de cuota pasado")
    
    def test_request_upload_url_invalid_data(self):
        """Test con datos inválidos"""
        print("❌ Probando datos inválidos...")
        
        # Datos incompletos
        data = {
            "file_name": "test.mp3"
            # Faltan file_size y file_type
        }
        
        url = reverse('direct-upload-request')
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('validation_error', response.data['error'])
        
        print("✅ Test de datos inválidos pasado")
    
    # =========================================================================
    # TESTS DE CONFIRMACIÓN DE UPLOAD
    # =========================================================================
    
    def test_confirm_upload_success(self):
        """Test confirmación exitosa de upload"""
        print("✅ Probando confirmación de upload...")
        
        # Primero crear una sesión de upload
        upload_session = UploadSession.objects.create(
            user=self.user,
            file_name="test_song.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            file_key="uploads/test-key-123",
            status='uploaded',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        # Mockear verificación de R2
        with patch.object(r2_direct, 'verify_file_uploaded') as mock_verify:
            mock_verify.return_value = (True, {'size': 1048576, 'etag': 'abc123'})
            
        with patch.object(r2_direct, 'validate_upload_integrity') as mock_validate:
            mock_validate.return_value = {'valid': True, 'metadata': {}}
        
        with patch('api2.tasks.upload_tasks.process_direct_upload.delay') as mock_task:
            mock_task.return_value = MagicMock(id='task-123')
            
            url = reverse('direct-upload-confirm', kwargs={'upload_id': upload_session.id})
            response = self.client.post(url, {}, format='json')
            
            # Verificaciones
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['status'], 'confirmed')
            self.assertTrue(response.data['processing_started'])
            
            # Actualizar sesión desde DB
            upload_session.refresh_from_db()
            self.assertEqual(upload_session.status, 'confirmed')
            
            print("✅ Test de confirmación de upload pasado")
    
    def test_confirm_upload_file_not_found(self):
        """Test cuando el archivo no se encuentra en R2"""
        print("🔍 Probando archivo no encontrado en R2...")
        
        upload_session = UploadSession.objects.create(
            user=self.user,
            file_name="test_song.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            file_key="uploads/missing-key",
            status='uploaded'
        )
        
        # Mockear que el archivo no existe en R2
        with patch.object(r2_direct, 'verify_file_uploaded') as mock_verify:
            mock_verify.return_value = (False, {})
            
            url = reverse('direct-upload-confirm', kwargs={'upload_id': upload_session.id})
            response = self.client.post(url, {}, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertIn('file_not_found', response.data['error'])
            
            # Verificar que la sesión se marcó como fallida
            upload_session.refresh_from_db()
            self.assertEqual(upload_session.status, 'failed')
            
            print("✅ Test de archivo no encontrado pasado")
    
    def test_confirm_upload_expired(self):
        """Test confirmación de upload expirado"""
        print("⏰ Probando upload expirado...")
        
        upload_session = UploadSession.objects.create(
            user=self.user,
            file_name="test_song.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            file_key="uploads/expired-key",
            status='uploaded',
            expires_at=timezone.now() - timedelta(hours=1)  # Ya expiró
        )
        
        url = reverse('direct-upload-confirm', kwargs={'upload_id': upload_session.id})
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot_confirm', response.data['error'])
        self.assertTrue(response.data['is_expired'])
        
        print("✅ Test de upload expirado pasado")
    
    # =========================================================================
    # TESTS DE ESTADO DE UPLOAD
    # =========================================================================
    
    def test_upload_status_various_states(self):
        """Test obtener estado de upload en diferentes estados"""
        print("📊 Probando estados de upload...")
        
        # Crear sesiones en diferentes estados
        states = ['pending', 'uploaded', 'confirmed', 'processing', 'ready', 'failed']
        
        for state in states:
            upload_session = UploadSession.objects.create(
                user=self.user,
                file_name=f"test_{state}.mp3",
                file_size=1048576,
                file_type="audio/mpeg",
                file_key=f"uploads/test-{state}",
                status=state
            )
            
            # Si está ready, crear canción asociada
            if state == 'ready':
                song = Song.objects.create(
                    title=f"Test {state} Song",
                    artist="Test Artist",
                    file_key=upload_session.file_key,
                    uploaded_by=self.user
                )
                upload_session.song = song
                upload_session.save()
            
            url = reverse('direct-upload-status', kwargs={'upload_id': upload_session.id})
            response = self.client.get(url)
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['status'], state)
            
            if state == 'ready':
                self.assertIn('song', response.data)
            elif state == 'failed':
                self.assertIn('can_retry', response.data)
            
            print(f"  ✅ Estado '{state}' verificado")
        
        print("✅ Test de estados de upload pasado")
    
    # =========================================================================
    # TESTS DE CUOTA DE USUARIO
    # =========================================================================
    
    def test_user_quota_endpoint(self):
        """Test endpoint de cuota de usuario"""
        print("📈 Probando endpoint de cuota...")
        
        url = reverse('user-upload-quota')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('daily_size_used', response.data)
        self.assertIn('max_daily_size', response.data)
        self.assertIn('max_daily_uploads', response.data)
        self.assertIn('remaining_daily_uploads', response.data)
        
        print("✅ Test de endpoint de cuota pasado")
    
    def test_quota_updates_after_upload(self):
        """Test que la cuota se actualiza después de un upload"""
        print("🔄 Probando actualización de cuota...")
        
        # Cuota inicial
        initial_uploads = self.quota.daily_uploads_used
        initial_size = self.quota.daily_size_used
        
        # Crear sesión de upload exitosa
        upload_session = UploadSession.objects.create(
            user=self.user,
            file_name="test_song.mp3",
            file_size=5242880,  # 5MB
            file_type="audio/mpeg",
            file_key="uploads/test-quota",
            status='ready'
        )
        
        # Simular confirmación de cuota
        self.quota.confirm_upload(5242880)
        self.quota.refresh_from_db()
        
        # Verificar que se actualizó
        self.assertEqual(self.quota.daily_uploads_used, initial_uploads + 1)
        self.assertEqual(self.quota.daily_size_used, initial_size + 5242880)
        
        print("✅ Test de actualización de cuota pasado")
    
    # =========================================================================
    # TESTS DE ADMINISTRACIÓN
    # =========================================================================
    
    def test_admin_dashboard_access(self):
        """Test acceso al dashboard de administración"""
        print("👨‍💼 Probando dashboard de admin...")
        
        # Usuario normal NO debe poder acceder
        url = reverse('upload-admin-dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Admin SÍ debe poder acceder
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('overview', response.data)
        self.assertIn('status_distribution', response.data)
        
        print("✅ Test de dashboard de admin pasado")
    
    def test_admin_stats_endpoint(self):
        """Test endpoint de estadísticas"""
        print("📊 Probando endpoint de estadísticas...")
        
        # Crear algunos datos de prueba
        for i in range(5):
            UploadSession.objects.create(
                user=self.user,
                file_name=f"test_{i}.mp3",
                file_size=1048576,
                file_type="audio/mpeg",
                file_key=f"uploads/test-{i}",
                status='ready' if i < 3 else 'failed'
            )
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('upload-stats')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('global', response.data)
        self.assertIn('weekly', response.data)
        
        if response.data['global']['total_uploads'] > 0:
            self.assertGreater(response.data['global']['successful_uploads'], 0)
        
        print("✅ Test de endpoint de estadísticas pasado")
    
    # =========================================================================
    # TESTS DE CANCELACIÓN
    # =========================================================================
    
    def test_cancel_upload_success(self):
        """Test cancelación exitosa de upload"""
        print("❌ Probando cancelación de upload...")
        
        upload_session = UploadSession.objects.create(
            user=self.user,
            file_name="test_cancel.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            file_key="uploads/cancel-key",
            status='uploaded'
        )
        
        initial_pending_size = self.quota.pending_size
        
        url = reverse('direct-upload-cancel', kwargs={'upload_id': upload_session.id})
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'cancelled')
        self.assertTrue(response.data['quota_released'])
        
        # Verificar que se actualizó el estado
        upload_session.refresh_from_db()
        self.assertEqual(upload_session.status, 'cancelled')
        
        # Verificar que se liberó la cuota pendiente
        self.quota.refresh_from_db()
        self.assertEqual(self.quota.pending_size, initial_pending_size - 1048576)
        
        print("✅ Test de cancelación de upload pasado")
    
    def test_cancel_already_processed_upload(self):
        """Test intentar cancelar upload ya procesado"""
        print("⚠️ Probando cancelación de upload procesado...")
        
        upload_session = UploadSession.objects.create(
            user=self.user,
            file_name="test_processed.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            file_key="uploads/processed-key",
            status='ready'
        )
        
        url = reverse('direct-upload-cancel', kwargs={'upload_id': upload_session.id})
        response = self.client.post(url, {}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot_cancel', response.data['error'])
        
        print("✅ Test de cancelación de upload procesado pasado")
    
    # =========================================================================
    # TESTS DE LIMPIEZA DE MANTENIMIENTO
    # =========================================================================
    
    def test_cleanup_expired_uploads(self):
        """Test limpieza de uploads expirados"""
        print("🧹 Probando limpieza de uploads expirados...")
        
        # Crear uploads expirados
        expired_upload = UploadSession.objects.create(
            user=self.user,
            file_name="expired.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            file_key="uploads/expired-key",
            status='uploaded',
            expires_at=timezone.now() - timedelta(hours=2)
        )
        
        # Crear upload NO expirado
        valid_upload = UploadSession.objects.create(
            user=self.user,
            file_name="valid.mp3",
            file_size=1048576,
            file_type="audio/mpeg",
            file_key="uploads/valid-key",
            status='uploaded',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('cleanup-expired-uploads')
        
        # Mockear la tarea de cleanup
        with patch('api2.tasks.upload_tasks.cleanup_expired_uploads.delay') as mock_task:
            mock_task.return_value = MagicMock(id='cleanup-task-123')
            
            response = self.client.post(url, {}, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.data['success'])
            self.assertEqual(response.data['async'], True)
            
            print("✅ Test de limpieza de uploads expirados pasado")


class TestUploadQuotaModel(TestCase):
    """Tests específicos para el modelo UploadQuota"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='quotauser',
            email='quota@example.com',
            password='testpass123'
        )
        self.quota = UploadQuota.objects.create(user=self.user)
    
    def test_can_upload_within_limits(self):
        """Test que se puede upload dentro de los límites"""
        self.assertTrue(self.quota.can_upload(1048576)[0])  # 1MB
    
    def test_cannot_upload_exceeds_daily_size(self):
        """Test que no se puede upload si excede tamaño diario"""
        self.quota.daily_size_used = self.quota.max_daily_size - 524288  # 0.5MB restante
        self.quota.save()
        
        can_upload, reason = self.quota.can_upload(1048576)  # Intentar 1MB
        
        self.assertFalse(can_upload)
        self.assertIn('tamaño diario', reason)
    
    def test_cannot_upload_exceeds_daily_count(self):
        """Test que no se puede upload si excede conteo diario"""
        self.quota.daily_uploads_used = self.quota.max_daily_uploads
        self.quota.save()
        
        can_upload, reason = self.quota.can_upload(1048576)
        
        self.assertFalse(can_upload)
        self.assertIn('uploads diarios', reason)
    
    def test_quota_reset(self):
        """Test que la cuota se resetea correctamente"""
        # Usar algo de cuota
        self.quota.daily_uploads_used = 5
        self.quota.daily_size_used = 100 * 1024 * 1024  # 100MB
        self.quota.save()
        
        # Resetear cuota
        self.quota.reset_daily_quota()
        self.quota.refresh_from_db()
        
        self.assertEqual(self.quota.daily_uploads_used, 0)
        self.assertEqual(self.quota.daily_size_used, 0)
        self.assertIsNotNone(self.quota.last_reset_at)


if __name__ == '__main__':
    print("🚀 Ejecutando tests de Direct Upload...")
    import unittest
    unittest.main()