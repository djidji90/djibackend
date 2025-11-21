# api2/tests/test_authentication.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from api2.models import Song

User = get_user_model()

class TestAuthentication(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='authuser',
            email='auth@example.com',
            password='testpass123'
        )
        self.song = Song.objects.create(
            title="Auth Test Song",
            artist="Auth Test Artist",
            genre="Rock",
            uploaded_by=self.user
        )
        print("✅ Configuración de Authentication completada")
    
    def test_unauthenticated_access_to_public_endpoints(self):
        """Test que endpoints públicos son accesibles sin autenticación"""
        print("🔐 Probando acceso público...")
        self.client.force_authenticate(user=None)  # Remover autenticación
        
        # Endpoints que deberían ser públicos (solo lectura)
        url = reverse('song-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ Test de acceso público pasado")
    
    def test_authenticated_required_for_actions(self):
        """Test que acciones requieren autenticación"""
        print("🔐 Probando requerimiento de autenticación...")
        self.client.force_authenticate(user=None)  # Remover autenticación
        
        # Intentar dar like sin autenticar
        url = reverse('song-like', kwargs={'song_id': self.song.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        print("✅ Test de requerimiento de autenticación pasado")
    
    def test_authenticated_user_can_perform_actions(self):
        """Test que usuario autenticado puede realizar acciones"""
        print("🔐 Probando acciones de usuario autenticado...")
        self.client.force_authenticate(user=self.user)
        
        # Dar like estando autenticado
        url = reverse('song-like', kwargs={'song_id': self.song.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ Test de acciones de usuario autenticado pasado")