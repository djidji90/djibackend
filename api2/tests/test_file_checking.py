# api2/tests/test_file_checking.py
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from api2.models import Song

User = get_user_model()

class TestFileCheckingSystem(TestCase):
    """Pruebas para el sistema de verificación de archivos"""
    
    def setUp(self):
        print("\n" + "="*60)
        print("🔄 Configurando tests de file checking...")
        
        self.client = APIClient()
        
        # Crear dos usuarios
        self.owner = User.objects.create_user(
            username='owneruser',
            email='owner@test.com',
            password='ownerpass123'
        )
        
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='otherpass123'
        )
        
        self.admin = User.objects.create_user(
            username='adminuser',
            email='admin@test.com',
            password='adminpass123',
            is_staff=True
        )
        
        # Crear canción de prueba
        self.song = Song.objects.create(
            title="Canción para testing",
            artist="Artista de prueba",
            genre="Test",
            file_key="songs/test_123456_audio.mp3",  # Key simulada
            image_key="images/test_123456_cover.jpg",  # Key simulada
            uploaded_by=self.owner
        )
        
        print("✅ Configuración completada")
        print("="*60)
    
    def test_01_owner_can_check_files(self):
        """Prueba 1: Owner puede verificar sus archivos"""
        print("\n🔍 Test 1: Owner verificando sus archivos")
        
        self.client.force_authenticate(user=self.owner)
        
        response = self.client.get(f'/api2/songs/{self.song.id}/check-files/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ ÉXITO: Owner puede verificar")
            print(f"   Audio key: {data['files']['audio']['key']}")
            print(f"   Image key: {data['files']['image']['key']}")
        else:
            print(f"   ❌ FALLÓ: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_02_admin_can_check_any_files(self):
        """Prueba 2: Admin puede verificar cualquier archivo"""
        print("\n🔍 Test 2: Admin verificando archivos")
        
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get(f'/api2/songs/{self.song.id}/check-files/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("   ✅ ÉXITO: Admin puede verificar cualquier canción")
        else:
            print(f"   ❌ FALLÓ: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_03_other_user_cannot_check_files(self):
        """Prueba 3: Otro usuario NO puede verificar"""
        print("\n🔍 Test 3: Otro usuario intentando verificar")
        
        self.client.force_authenticate(user=self.other_user)
        
        response = self.client.get(f'/api2/songs/{self.song.id}/check-files/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code in [403, 404]:
            print("   ✅ ÉXITO: Otro usuario no puede verificar")
        else:
            print(f"   ❌ FALLÓ: Debería haber fallado")
        
        self.assertIn(response.status_code, [403, 404])
    
    def test_04_unauthenticated_cannot_check(self):
        """Prueba 4: Usuario no autenticado NO puede verificar"""
        print("\n🔍 Test 4: Usuario no autenticado")
        
        self.client.force_authenticate(user=None)
        
        response = self.client.get(f'/api2/songs/{self.song.id}/check-files/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code in [401, 403]:
            print("   ✅ ÉXITO: Autenticación requerida")
        else:
            print(f"   ❌ FALLÓ: Debería requerir autenticación")
        
        self.assertIn(response.status_code, [401, 403])
    
    def test_05_nonexistent_song_returns_404(self):
        """Prueba 5: Canción inexistente devuelve 404"""
        print("\n🔍 Test 5: Canción inexistente")
        
        self.client.force_authenticate(user=self.owner)
        
        response = self.client.get('/api2/songs/99999/check-files/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 404:
            print("   ✅ ÉXITO: Canción inexistente devuelve 404")
        else:
            print(f"   ❌ FALLÓ: Debería devolver 404")
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_06_song_with_temp_file_key(self):
        """Prueba 6: Canción con file_key temporal"""
        print("\n🔍 Test 6: Canción con file_key temporal")
        
        # Crear canción con file_key temporal
        temp_song = Song.objects.create(
            title="Canción temporal",
            artist="Artista temp",
            genre="Temp",
            file_key="songs/temp_file",  # Key temporal
            uploaded_by=self.owner
        )
        
        self.client.force_authenticate(user=self.owner)
        
        response = self.client.get(f'/api2/songs/{temp_song.id}/check-files/')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("   ✅ ÉXITO: Manejo correcto de file_key temporal")
            print(f"   Audio exists: {data['files']['audio']['exists']}")
            self.assertFalse(data['files']['audio']['exists'])
        else:
            print(f"   ❌ FALLÓ: {response.json()}")
    
    def tearDown(self):
        """Limpieza"""
        print("\n🧹 Limpiando tests de file checking...")
        print("✅ Completado")