# api2/tests/test_download_url.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from api2.models import Song, Download
from unittest.mock import patch, MagicMock
import secrets

User = get_user_model()

class DownloadURLViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.client.force_authenticate(user=self.user)
        
        self.song = Song.objects.create(
            title='Test Song',
            artist='Test Artist',
            genre='Test',
            file_key='songs/test.mp3',
            is_public=True
        )
    
    @patch('api2.views.check_file_exists')
    @patch('api2.views.generate_presigned_url')
    @patch('api2.views.get_file_info')
    def test_get_download_url_success(self, mock_file_info, mock_generate_url, mock_check_exists):
        """Test: Obtener URL de descarga exitosamente"""
        # Configurar mocks
        mock_check_exists.return_value = True
        mock_generate_url.return_value = 'https://r2.test/url.mp3'
        mock_file_info.return_value = {'size': 12345}
        
        url = reverse('song-download-url', kwargs={'song_id': self.song.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('download_url', response.data)
        self.assertIn('download_token', response.data)
        self.assertEqual(response.data['file_size'], 12345)
        
        # Verificar que se creó el Download
        download = Download.objects.filter(
            user=self.user,
            song=self.song
        ).first()
        self.assertIsNotNone(download)
        self.assertEqual(download.download_token, response.data['download_token'])
        self.assertFalse(download.is_confirmed)
    
    def test_get_download_url_song_not_found(self):
        """Test: Canción no existe"""
        url = reverse('song-download-url', kwargs={'song_id': 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
    
    @patch('api2.views.check_file_exists')
    def test_get_download_url_file_not_found(self, mock_check_exists):
        """Test: Archivo no existe en R2"""
        mock_check_exists.return_value = False
        
        url = reverse('song-download-url', kwargs={'song_id': self.song.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
    
    def test_get_download_url_rate_limit(self):
        """Test: Rate limiting funciona"""
        # Configurar rate limit manualmente
        cache_key = f"download_url_{self.user.id}_{self.song.id}"
        from django.core.cache import cache
        cache.set(cache_key, True, timeout=3600)
        
        url = reverse('song-download-url', kwargs={'song_id': self.song.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 429)
        self.assertIn('retry_after', response.data)