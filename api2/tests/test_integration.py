# api2/tests/test_integration.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from api2.models import Song, Download
from unittest.mock import patch, MagicMock
import secrets

User = get_user_model()

class FullFlowTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.client.force_authenticate(user=self.user)
        
        self.song = Song.objects.create(
            title='Test Song',
            artist='Test Artist',
            genre='Test',
            file_key='songs/test.mp3',
            downloads_count=0,
            is_public=True
        )
    
    @patch('api2.views.check_file_exists')
    @patch('api2.views.generate_presigned_url')
    @patch('api2.views.get_file_info')
    def test_complete_download_flow(self, mock_file_info, mock_generate_url, mock_check_exists):
        """Test: Flujo completo de descarga y confirmación"""
        # Configurar mocks
        mock_check_exists.return_value = True
        mock_generate_url.return_value = 'https://r2.test/url.mp3'
        mock_file_info.return_value = {'size': 12345}
        
        # PASO 1: Obtener URL de descarga
        download_url = reverse('song-download-url', kwargs={'song_id': self.song.id})
        response1 = self.client.get(download_url)
        
        self.assertEqual(response1.status_code, 200)
        download_token = response1.data['download_token']
        self.assertIsNotNone(download_token)
        
        # Verificar que se creó el registro pendiente
        download = Download.objects.get(download_token=download_token)
        self.assertFalse(download.is_confirmed)
        self.assertEqual(download.song.id, self.song.id)
        
        # PASO 2: Confirmar descarga
        confirm_url = reverse('confirm-download')
        response2 = self.client.post(confirm_url, {
            'download_token': download_token,
            'success': True,
            'file_size': 12345
        }, format='json')
        
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.data['status'], 'confirmed')
        
        # Verificar que se actualizó
        download.refresh_from_db()
        self.assertTrue(download.is_confirmed)
        
        # Verificar que el contador aumentó
        self.song.refresh_from_db()
        self.assertEqual(self.song.downloads_count, 1)