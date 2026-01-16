# api2/tests/test_rate_limiting.py
from django.test import TestCase
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()

class TestRateLimitingSystem(TestCase):
    """Pruebas específicas para rate limiting"""
    
    def setUp(self):
        print("\n" + "="*60)
        print("🔄 Configurando tests de rate limiting...")
        
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='ratelimituser',
            email='ratelimit@test.com',
            password='ratelimit123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Limpiar cache antes de cada test
        cache.clear()
        
        # Crear archivo de prueba
        self.audio_content = b'ID3\x03\x00' + b'A' * 1024
        self.audio_file = SimpleUploadedFile(
            "test_rate.mp3",
            self.audio_content,
            content_type="audio/mpeg"
        )
        
        print("✅ Configuración completada")
        print("="*60)
    
    def test_01_rate_limit_resets_after_hour(self):
        """Prueba 1: Rate limit se reseta después de 1 hora"""
        print("\n⏰ Test 1: Rate limit se reseta")
        
        # Simular que ya usamos 19 uploads
        hour_key = f"upload_{self.user.id}_{timezone.now().hour}"
        cache.set(hour_key, 19, 3600)  # Expira en 1 hora
        
        # El upload #20 debería funcionar
        data = {
            'title': 'Upload 20',
            'artist': 'Test',
            'genre': 'Test',
            'audio_file': self.audio_file,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            print("   ✅ ÉXITO: Upload #20 aceptado")
        else:
            print(f"   ❌ FALLÓ: Debería aceptar upload #20")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_02_rate_limit_blocks_21st_upload(self):
        """Prueba 2: El upload #21 debe ser bloqueado"""
        print("\n⏰ Test 2: Upload #21 bloqueado")
        
        # Simular 20 uploads ya realizados
        hour_key = f"upload_{self.user.id}_{timezone.now().hour}"
        cache.set(hour_key, 20, 3600)
        
        data = {
            'title': 'Upload 21 (debería fallar)',
            'artist': 'Test',
            'genre': 'Test',
            'audio_file': self.audio_file,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 429:
            print("   ✅ ÉXITO: Upload #21 bloqueado (429)")
            error_msg = response.json().get('error', '')
            print(f"   Mensaje: {error_msg}")
        else:
            print(f"   ❌ FALLÓ: Debería bloquear con 429")
        
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
    
    def test_03_different_users_have_separate_limits(self):
        """Prueba 3: Límites separados por usuario"""
        print("\n⏰ Test 3: Límites separados por usuario")
        
        # Crear segundo usuario
        user2 = User.objects.create_user(
            username='user2',
            email='user2@test.com',
            password='user2pass123'
        )
        
        # Usuario 1 ya hizo 20 uploads
        hour_key1 = f"upload_{self.user.id}_{timezone.now().hour}"
        cache.set(hour_key1, 20, 3600)
        
        # Usuario 2 no ha hecho uploads
        self.client.force_authenticate(user=user2)
        
        data = {
            'title': 'Primer upload usuario 2',
            'artist': 'User2',
            'genre': 'Test',
            'audio_file': self.audio_file,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            print("   ✅ ÉXITO: Usuario 2 puede upload aunque usuario 1 llegó al límite")
        else:
            print(f"   ❌ FALLÓ: Usuario 2 debería poder upload")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_04_rate_limit_per_hour_not_per_day(self):
        """Prueba 4: Límite por hora, no por día"""
        print("\n⏰ Test 4: Límite por hora (no acumula día)")
        
        # Simular 20 uploads en la hora anterior
        previous_hour = timezone.now().hour - 1
        if previous_hour < 0:
            previous_hour = 23
        
        prev_hour_key = f"upload_{self.user.id}_{previous_hour}"
        cache.set(prev_hour_key, 20, 3600)  # Aún no expiró
        
        # En la hora actual no hay uploads
        current_hour_key = f"upload_{self.user.id}_{timezone.now().hour}"
        cache.set(current_hour_key, 0, 3600)
        
        data = {
            'title': 'Upload en hora nueva',
            'artist': 'Test',
            'genre': 'Test',
            'audio_file': self.audio_file,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            print("   ✅ ÉXITO: Nuevo hour, nuevo límite")
        else:
            print(f"   ❌ FALLÓ: Debería permitir en nueva hora")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def tearDown(self):
        """Limpieza"""
        print("\n🧹 Limpiando tests de rate limiting...")
        cache.clear()
        print("✅ Completado")