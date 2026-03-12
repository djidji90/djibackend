# api2/tests/test_confirm.py
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from api2.models import Song, Download
from django.core.cache import cache
import secrets
from unittest.mock import patch, MagicMock 

User = get_user_model()

@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
})
class ConfirmDownloadViewTest(TestCase):
    
    def setUp(self):
        """Crear datos frescos para cada test"""
        # Limpiar todo
        cache.clear()
        Download.objects.all().delete()
        Song.objects.all().delete()
        User.objects.all().delete()
        
        self.client = APIClient()
        
        # Crear usuarios
        self.user = User.objects.create_user(
            username='testuser', 
            password='12345',
            email='testuser@example.com'
        )
        self.other_user = User.objects.create_user(
            username='other', 
            password='12345',
            email='other@example.com'
        )
        
        self.client.force_authenticate(user=self.user)
        
        # Crear canción
        self.song = Song.objects.create(
            title='Test Song',
            artist='Test Artist',
            genre='Test',
            file_key='songs/test.mp3',
            downloads_count=0  # EXPLÍCITAMENTE 0
        )
        
        # Crear download con token
        self.download_token = secrets.token_urlsafe(32)
        self.download = Download.objects.create(
            user=self.user,
            song=self.song,
            download_token=self.download_token,
            is_confirmed=False
        )
        
        # Verificación extra
        self.assertEqual(self.song.downloads_count, 0)
    
    def tearDown(self):
        """Limpiar TODO después de cada test"""
        cache.clear()
        Download.objects.all().delete()
        Song.objects.all().delete()
        User.objects.all().delete()
    
    def _reset_song_counter(self):
        """Método auxiliar para resetear el contador"""
        self.song.refresh_from_db()
        self.song.downloads_count = 0
        self.song.save(update_fields=['downloads_count'])
        self.song.refresh_from_db()
    
    def test_confirm_download_success(self):
        """Test: Confirmar descarga exitosamente"""
        # Resetear contador antes del test
        self._reset_song_counter()
        self.assertEqual(self.song.downloads_count, 0)
        
        url = reverse('song-download-confirm')
        response = self.client.post(url, {
            'download_token': self.download_token,
            'success': True,
            'file_size': 12345
        }, format='json')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'confirmed')
        
        self.download.refresh_from_db()
        self.assertTrue(self.download.is_confirmed)
        
        self.song.refresh_from_db()
        self.assertEqual(self.song.downloads_count, 1)
    
    def test_confirm_download_wrong_user(self):
        """Test: Otro usuario intenta confirmar"""
        self._reset_song_counter()
        
        self.client.force_authenticate(user=self.other_user)
        
        url = reverse('song-download-confirm')
        response = self.client.post(url, {
            'download_token': self.download_token,
            'success': True
        }, format='json')
        
        self.assertEqual(response.status_code, 403)
        
        self.download.refresh_from_db()
        self.assertFalse(self.download.is_confirmed)
        self.song.refresh_from_db()
        self.assertEqual(self.song.downloads_count, 0)
    
    def test_confirm_download_invalid_token(self):
        """Test: Token inválido"""
        self._reset_song_counter()
        
        url = reverse('song-download-confirm')
        response = self.client.post(url, {
            'download_token': 'token_invalido',
            'success': True
        }, format='json')
        
        self.assertEqual(response.status_code, 404)
        self.song.refresh_from_db()
        self.assertEqual(self.song.downloads_count, 0)
    
    def test_confirm_download_missing_token(self):
        """Test: No se envía token"""
        self._reset_song_counter()
        
        url = reverse('song-download-confirm')
        response = self.client.post(url, {
            'success': True
        }, format='json')
        
        self.assertEqual(response.status_code, 400)
        self.song.refresh_from_db()
        self.assertEqual(self.song.downloads_count, 0)
    
    def test_confirm_download_failed(self):
        """Test: Descarga fallida"""
        self._reset_song_counter()
        
        url = reverse('song-download-confirm')
        response = self.client.post(url, {
            'download_token': self.download_token,
            'success': False
        }, format='json')
        
        self.assertEqual(response.status_code, 200)
        
        self.download.refresh_from_db()
        self.assertFalse(self.download.is_confirmed)
        self.song.refresh_from_db()
        self.assertEqual(self.song.downloads_count, 0)
    
    @patch('api2.views.cache.get')
    def test_confirm_download_from_cache(self, mock_cache_get):
        """Test: Confirmación usando cache primero"""
        self._reset_song_counter()
        
        mock_cache_get.return_value = {
            'download_id': self.download.id,
            'user_id': self.user.id,
            'song_id': self.song.id
        }
        
        url = reverse('song-download-confirm')
        response = self.client.post(url, {
            'download_token': self.download_token,
            'success': True
        }, format='json')
        
        self.assertEqual(response.status_code, 200)
        mock_cache_get.assert_called_with(f"token_{self.download_token}")
        self.song.refresh_from_db()
        self.assertEqual(self.song.downloads_count, 1)