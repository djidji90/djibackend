# api2/tests/test_views.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from api2.models import Song, Comment, MusicEvent

User = get_user_model()

class TestSongViews(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.song = Song.objects.create(
            title="Test Song",
            artist="Test Artist",
            genre="Rock",
            uploaded_by=self.user
        )
        print("✅ Configuración de SongViews completada")
    
    def test_song_list_api(self):
        """Test endpoint de listado de canciones"""
        print("🌐 Probando listado de canciones...")
        url = reverse('song-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ Test de listado de canciones pasado")
    
    def test_like_song_api(self):
        """Test endpoint de like"""
        print("❤️ Probando like de canción...")
        url = reverse('song-like', kwargs={'song_id': self.song.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('likes_count', response.data)
        print("✅ Test de like de canción pasado")

class TestCommentViews(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='commentuser',
            email='comment@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.song = Song.objects.create(
            title="Comment Test Song",
            artist="Comment Test Artist",
            genre="Rock",
            uploaded_by=self.user
        )
        print("✅ Configuración de CommentViews completada")
    
    def test_comment_list_api(self):
        """Test listado de comentarios"""
        print("💬 Probando listado de comentarios...")
        # Crear algunos comentarios
        Comment.objects.create(
            user=self.user,
            song=self.song,
            content="Primer comentario"
        )
        Comment.objects.create(
            user=self.user,
            song=self.song,
            content="Segundo comentario"
        )
        
        url = reverse('song-comments', kwargs={'song_id': self.song.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ Test de listado de comentarios pasado")
    
    def test_create_comment_api(self):
        """Test creación de comentario"""
        print("💬 Probando creación de comentario...")
        url = reverse('song-comments', kwargs={'song_id': self.song.id})
        data = {'content': 'Este es un comentario de prueba'}
        
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['content'], data['content'])
        print("✅ Test de creación de comentario pasado")

class TestMusicEventViews(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='eventuser',
            email='event@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        print("✅ Configuración de MusicEventViews completada")
    
    def test_event_list_api(self):
        """Test listado de eventos"""
        print("🎪 Probando listado de eventos...")
        # Crear algunos eventos
        MusicEvent.objects.create(
            title="Evento 1",
            description="Descripción 1",
            event_type="concert",
            event_date="2024-12-31T20:00:00Z",
            location="Madrid"
        )
        
        url = reverse('event-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print("✅ Test de listado de eventos pasado")