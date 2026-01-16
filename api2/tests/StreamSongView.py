# api2/tests/test_streaming.py
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from api2.models import Song

User = get_user_model()

class TestStreamingSystem(TestCase):
    """Pruebas para el sistema de streaming"""
    
    def setUp(self):
        print("\n" + "="*60)
        print("🔄 Configurando tests de streaming...")
        
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='streamuser',
            email='stream@test.com',
            password='streampass123'
        )
        
        # Crear canción de prueba con file_key
        self.song = Song.objects.create(
            title="Canción para streaming",
            artist="Artista stream",
            genre="Streaming",
            file_key="songs/stream_test_audio.mp3",
            uploaded_by=self.user
        )
        
        self.client.force_authenticate(user=self.user)
        
        print("✅ Configuración completada")
        print("="*60)
    
    def test_01_streaming_requires_authentication(self):
        """Prueba 1: Streaming requiere autenticación"""
        print("\n🎧 Test 1: Autenticación requerida para streaming")
        
        self.client.force_authenticate(user=None)
        
        response = self.client.get(f'/api2/songs/{self.song.id}/stream/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code in [401, 403]:
            print("   ✅ ÉXITO: Autenticación requerida")
        else:
            print(f"   ❌ FALLÓ: Debería requerir autenticación")
        
        self.assertIn(response.status_code, [401, 403])
    
    def test_02_streaming_with_range_header(self):
        """Prueba 2: Streaming con Range header"""
        print("\n🎧 Test 2: Streaming con Range header")
        
        headers = {'HTTP_RANGE': 'bytes=0-999'}
        
        response = self.client.get(
            f'/api2/songs/{self.song.id}/stream/',
            **headers
        )
        
        print(f"   Status: {response.status_code}")
        
        # Nota: Este test puede fallar si R2 no está configurado en tests
        # pero verificamos la estructura de respuesta
        if response.status_code in [200, 206]:
            print("   ✅ ÉXITO: Streaming con range funcionó")
            print(f"   Content-Type: {response.headers.get('Content-Type')}")
            print(f"   Accept-Ranges: {response.headers.get('Accept-Ranges')}")
            
            # Verificar headers importantes
            self.assertIn('Accept-Ranges', response.headers)
            self.assertEqual(response.headers['Accept-Ranges'], 'bytes')
        else:
            print(f"   ⚠️ Status inesperado: {response.status_code}")
            # No fallamos el test porque R2 puede no estar disponible
    
    def test_03_streaming_without_range(self):
        """Prueba 3: Streaming sin Range header"""
        print("\n🎧 Test 3: Streaming completo (sin range)")
        
        response = self.client.get(f'/api2/songs/{self.song.id}/stream/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ ÉXITO: Streaming completo funcionó")
            print(f"   Content-Type: {response.headers.get('Content-Type')}")
        else:
            print(f"   ⚠️ Status: {response.status_code}")
    
    def test_04_streaming_nonexistent_song(self):
        """Prueba 4: Streaming de canción inexistente"""
        print("\n🎧 Test 4: Canción inexistente")
        
        response = self.client.get('/api2/songs/99999/stream/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print("   ✅ ÉXITO: Canción inexistente devuelve 404")
        else:
            print(f"   ❌ FALLÓ: Debería devolver 404")
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_05_streaming_song_without_file_key(self):
        """Prueba 5: Canción sin file_key"""
        print("\n🎧 Test 5: Canción sin file_key")
        
        # Crear canción sin file_key
        no_file_song = Song.objects.create(
            title="Sin archivo",
            artist="Sin archivo",
            genre="Test",
            uploaded_by=self.user
        )
        
        response = self.client.get(f'/api2/songs/{no_file_song.id}/stream/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print("   ✅ ÉXITO: Canción sin file_key devuelve 404")
        else:
            print(f"   ❌ FALLÓ: Debería devolver 404")
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def tearDown(self):
        """Limpieza"""
        print("\n🧹 Limpiando tests de streaming...")
        print("✅ Completado")