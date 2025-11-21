# api2/tests/test_song_models.py
from django.test import TestCase
from api2.models import Song
from django.contrib.auth import get_user_model

# Usar get_user_model() en lugar de User directo
User = get_user_model()

class TestSongModel(TestCase):
    def setUp(self):
        """Configuración inicial para todas las pruebas"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        print("✅ Usuario de prueba creado")
    
    def test_song_creation(self):
        """Test creación básica de canción"""
        print("🎵 Probando creación de canción...")
        song = Song.objects.create(
            title="Test Song",
            artist="Test Artist",
            genre="Rock",
            uploaded_by=self.user
        )
        
        self.assertEqual(song.title, "Test Song")
        self.assertEqual(song.artist, "Test Artist")
        self.assertEqual(song.genre, "Rock")
        self.assertEqual(song.uploaded_by, self.user)
        self.assertTrue(song.is_public)
        print("✅ Test de creación de canción pasado")
    
    def test_song_str_representation(self):
        """Test representación en string"""
        print("🎵 Probando representación string...")
        song = Song.objects.create(
            title="Mi Canción",
            artist="Mi Artista", 
            genre="Pop",
            uploaded_by=self.user
        )
        
        self.assertEqual(str(song), "Mi Canción by Mi Artista")
        print("✅ Test de representación string pasado")
    
    def test_song_file_name_property(self):
        """Test propiedad file_name"""
        print("🎵 Probando propiedad file_name...")
        song = Song.objects.create(
            title="Test Song",
            artist="Test Artist",
            genre="Rock", 
            uploaded_by=self.user,
            file_key="songs/my_song.mp3"
        )
        
        self.assertEqual(song.file_name, "my_song.mp3")
        print("✅ Test de propiedad file_name pasado")
    
    def test_song_image_name_property(self):
        """Test propiedad image_name"""
        print("🎵 Probando propiedad image_name...")
        song = Song.objects.create(
            title="Test Song",
            artist="Test Artist",
            genre="Rock", 
            uploaded_by=self.user,
            image_key="images/my_image.jpg"
        )
        
        self.assertEqual(song.image_name, "my_image.jpg")
        print("✅ Test de propiedad image_name pasado")
    
    def test_song_default_values(self):
        """Test que los valores por defecto se establecen correctamente"""
        print("🎵 Probando valores por defecto...")
        song = Song.objects.create(
            title="Test Song",
            artist="Test Artist",
            genre="Rock",
            uploaded_by=self.user
        )
        
        self.assertEqual(song.likes_count, 0)
        self.assertEqual(song.plays_count, 0)
        self.assertEqual(song.downloads_count, 0)
        self.assertTrue(song.is_public)
        print("✅ Test de valores por defecto pasado")
    
    def test_song_save_generates_keys(self):
        """Test que save() genera keys automáticamente"""
        print("🎵 Probando generación automática de keys...")
        song = Song(
            title="Auto Key Song",
            artist="Auto Key Artist", 
            genre="Test Genre",
            uploaded_by=self.user,
            file_key="songs/temp_file"  # Key temporal
        )
        song.save()
        
        # Verificar que se generaron keys únicas
        self.assertNotEqual(song.file_key, "songs/temp_file")
        self.assertTrue(song.file_key.startswith('songs/'))
        self.assertTrue(song.file_key.endswith('.mp3'))
        self.assertTrue(song.image_key.startswith('images/'))
        self.assertTrue(song.image_key.endswith('.jpg'))
        print("✅ Test de generación automática de keys pasado")