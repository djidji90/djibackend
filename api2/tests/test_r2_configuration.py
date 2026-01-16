# api2/tests/test_download_models.py
from django.test import TestCase
from api2.models import Song, Download
from django.contrib.auth import get_user_model

User = get_user_model()

class TestDownloadModel(TestCase):
    def setUp(self):
        """Configuración inicial para todas las pruebas"""
        self.user = User.objects.create_user(
            username='downloaduser',
            email='download@example.com',
            password='testpass123'
        )
        self.song = Song.objects.create(
            title="Download Test Song",
            artist="Download Test Artist",
            genre="Rock",
            uploaded_by=self.user
        )
        print("✅ Configuración de DownloadModel completada")
    
    def test_download_creation(self):
        """Test creación de descarga"""
        print("📥 Probando creación de descarga...")
        download = Download.objects.create(user=self.user, song=self.song)
        
        self.assertEqual(download.user, self.user)
        self.assertEqual(download.song, self.song)
        self.assertIsNotNone(download.downloaded_at)
        print("✅ Test de creación de descarga pasado")
    
    def test_download_updates_song_count(self):
        """Test que descarga actualiza el contador"""
        print("📥 Probando actualización de contador de descargas...")
        
        # Contador inicial debería ser 0
        self.assertEqual(self.song.downloads_count, 0)
        
        # Crear descarga debería actualizar el contador
        download = Download.objects.create(user=self.user, song=self.song)
        self.song.refresh_from_db()
        
        self.assertEqual(self.song.downloads_count, 1)
        print("✅ Test de actualización de contador de descargas pasado")