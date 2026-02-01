# api2/tests/test_upload_admin.py
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from api2.models import UploadSession
from django.utils import timezone
from datetime import timedelta
import uuid

User = get_user_model()

@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
})
class UploadAdminTests(TestCase):
    
    def setUp(self):
        self.client = APIClient()
        
        # Crear usuarios con emails únicos usando uuid
        unique_id = uuid.uuid4().hex[:8]
        
        self.admin_user = User.objects.create_user(
            username=f'admin_{unique_id}',
            email=f'admin_{unique_id}@test.com',
            password='adminpass123',
            is_staff=True
        )
        
        self.regular_user = User.objects.create_user(
            username=f'regular_{unique_id}',
            email=f'regular_{unique_id}@test.com',
            password='regularpass123',
            is_staff=False
        )
        
        # Crear datos de prueba con expires_at
        for i in range(5):
            UploadSession.objects.create(
                user=self.regular_user,
                file_name=f'test_{i}.mp3',
                file_size=10485760 * (i + 1),
                file_type='audio/mpeg',
                file_key=f'uploads/test_{i}.mp3',
                status='ready',
                expires_at=timezone.now() + timedelta(hours=1)  # ¡Campo requerido!
            )
    
    def test_admin_dashboard_access_staff(self):
        """Prueba acceso a dashboard con usuario staff"""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('upload-admin-dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('stats', response.data)
        print(f"✓ Dashboard admin accesible para staff")
    
    def test_admin_dashboard_access_non_staff(self):
        """Prueba acceso a dashboard con usuario no staff"""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse('upload-admin-dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        print(f"✓ Dashboard admin bloqueado para no-staff")

@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
})
class SimpleAdminTest(TestCase):
    """Test simple para verificar que funciona"""
    
    def test_admin_user_creation(self):
        """Test básico de creación de usuario admin"""
        user = User.objects.create_user(
            username='test_admin',
            email='test_admin@example.com',
            password='testpass123',
            is_staff=True
        )
        self.assertTrue(user.is_staff)
        print(f"✓ Usuario admin creado correctamente")