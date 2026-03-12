# api2/tests/test_models.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from api2.models import Song, Download
import secrets

User = get_user_model()

class DownloadModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        self.song = Song.objects.create(
            title='Test Song',
            artist='Test Artist',
            genre='Test',
            file_key='songs/test.mp3'
        )
    
    def test_create_download_with_token(self):
        """Verificar que se puede crear un Download con token"""
        token = secrets.token_urlsafe(32)
        download = Download.objects.create(
            user=self.user,
            song=self.song,
            download_token=token,
            is_confirmed=False
        )
        
        self.assertIsNotNone(download.id)
        self.assertEqual(download.download_token, token)
        self.assertFalse(download.is_confirmed)
    
    def test_download_token_unique(self):
        """Verificar que los tokens son únicos"""
        token = secrets.token_urlsafe(32)
        Download.objects.create(
            user=self.user,
            song=self.song,
            download_token=token,
            is_confirmed=False
        )
        
        with self.assertRaises(Exception):
            Download.objects.create(
                user=self.user,
                song=self.song,
                download_token=token,  # Mismo token
                is_confirmed=False
            )
    
    def test_download_token_not_null(self):
        """Verificar que el token no puede ser null"""
        with self.assertRaises(Exception):
            Download.objects.create(
                user=self.user,
                song=self.song,
                download_token=None,  # No permitido
                is_confirmed=False
            )