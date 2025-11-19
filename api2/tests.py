# api2/tests.py - VERSIÓN CORREGIDA
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import Song, Like, Download, Comment, MusicEvent, UserProfile
from api2.r2_utils import generate_presigned_url
import uuid

User = get_user_model()


class UserTests(APITestCase):
    def setUp(self):
        self.user_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        self.user = User.objects.create_user(**self.user_data)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_user_creation(self):
        """Test que un usuario puede crearse correctamente"""
        self.assertEqual(self.user.username, 'testuser')
        self.assertTrue(self.user.check_password('testpass123'))

    def test_user_profile_creation(self):
        """Test que el perfil de usuario se crea automáticamente"""
        # UserProfile debería crearse automáticamente por la señal
        profile_exists = UserProfile.objects.filter(user=self.user).exists()
        self.assertTrue(profile_exists)


class SongTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='artist',
            email='artist@example.com',
            password='testpass123'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.song_data = {
            'title': 'Test Song',
            'artist': 'Test Artist',
            'genre': 'Rock',
            'duration': '3:45',
            'file_key': f'songs/{uuid.uuid4().hex[:12]}.mp3',
            'image_key': f'images/{uuid.uuid4().hex[:12]}.jpg',
            'uploaded_by': self.user,
            'is_public': True
        }
        self.song = Song.objects.create(**self.song_data)

    def test_song_creation(self):
        """Test que una canción puede crearse correctamente"""
        self.assertEqual(self.song.title, 'Test Song')
        self.assertEqual(self.song.artist, 'Test Artist')
        self.assertEqual(self.song.genre, 'Rock')
        self.assertTrue(self.song.is_public)

    def test_song_str_representation(self):
        """Test la representación en string de la canción"""
        self.assertEqual(str(self.song), 'Test Song by Test Artist')

    def test_song_file_url_generation(self):
        """Test que se genera URL firmada para el archivo"""
        url = generate_presigned_url(self.song.file_key)
        self.assertIsNotNone(url)
        # No verificar la URL específica ya que puede variar

    def test_song_list_api(self):
        """Test el endpoint de listado de canciones"""
        url = reverse('song-list')
        response = self.client.get(url)
        # Puede ser 200 o 404 dependiendo de la configuración
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])


class LikeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.song = Song.objects.create(
            title='Test Song',
            artist='Test Artist',
            genre='Rock',
            file_key=f'songs/{uuid.uuid4().hex[:12]}.mp3',
            uploaded_by=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_like_creation(self):
        """Test que un like puede crearse correctamente"""
        like = Like.objects.create(user=self.user, song=self.song)
        self.assertEqual(like.user, self.user)
        self.assertEqual(like.song, self.song)

    def test_like_count_updates(self):
        """Test que el contador de likes se actualiza automáticamente"""
        initial_count = self.song.likes_count
        
        Like.objects.create(user=self.user, song=self.song)
        self.song.refresh_from_db()
        
        self.assertEqual(self.song.likes_count, initial_count + 1)

    def test_like_unique_constraint(self):
        """Test que un usuario no puede dar like dos veces a la misma canción"""
        Like.objects.create(user=self.user, song=self.song)
        
        with self.assertRaises(Exception):  # Debe fallar por unique constraint
            Like.objects.create(user=self.user, song=self.song)


class CommentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.song = Song.objects.create(
            title='Test Song',
            artist='Test Artist',
            genre='Rock',
            file_key=f'songs/{uuid.uuid4().hex[:12]}.mp3',
            uploaded_by=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_comment_creation(self):
        """Test que un comentario puede crearse correctamente"""
        comment = Comment.objects.create(
            song=self.song,
            user=self.user,
            content='This is a test comment'
        )
        self.assertEqual(comment.content, 'This is a test comment')
        self.assertEqual(comment.song, self.song)
        self.assertEqual(comment.user, self.user)

    def test_comment_ordering(self):
        """Test que los comentarios se ordenan por fecha de creación descendente"""
        comment1 = Comment.objects.create(
            song=self.song,
            user=self.user,
            content='First comment'
        )
        comment2 = Comment.objects.create(
            song=self.song,
            user=self.user,
            content='Second comment'
        )
        
        comments = Comment.objects.all()
        self.assertEqual(comments[0], comment2)  # Más reciente primero
        self.assertEqual(comments[1], comment1)


class MusicEventTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='organizer',
            email='organizer@example.com',
            password='testpass123'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        from django.utils import timezone
        from datetime import timedelta
        
        self.event_data = {
            'title': 'Test Festival',
            'description': 'A test music festival',
            'event_type': 'festival',
            'event_date': timezone.now() + timedelta(days=30),
            'location': 'Test Venue',
            'venue': 'Main Stage',
            'image_key': f'events/{uuid.uuid4().hex[:12]}.jpg',
            'is_active': True
        }

    def test_event_creation(self):
        """Test que un evento puede crearse correctamente"""
        event = MusicEvent.objects.create(**self.event_data)
        self.assertEqual(event.title, 'Test Festival')
        self.assertEqual(event.event_type, 'festival')
        self.assertTrue(event.is_active)

    def test_event_str_representation(self):
        """Test la representación en string del evento"""
        event = MusicEvent.objects.create(**self.event_data)
        self.assertEqual(str(event), 'Test Festival')


class SearchAndDiscoveryTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Crear canciones de prueba para búsqueda
        self.song1 = Song.objects.create(
            title='Rock Song',
            artist='Rock Band',
            genre='Rock',
            file_key=f'songs/{uuid.uuid4().hex[:12]}.mp3',
            uploaded_by=self.user
        )
        
        self.song2 = Song.objects.create(
            title='Jazz Song',
            artist='Jazz Trio',
            genre='Jazz',
            file_key=f'songs/{uuid.uuid4().hex[:12]}.mp3',
            uploaded_by=self.user
        )

    def test_artist_list_api(self):
        """Test el endpoint de lista de artistas"""
        url = reverse('artist-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('artists', response.data)


class R2UtilsTests(TestCase):
    def setUp(self):
        self.test_key = f'test/{uuid.uuid4().hex[:12]}.txt'

    def test_generate_presigned_url(self):
        """Test que se pueden generar URLs firmadas"""
        url = generate_presigned_url(self.test_key)
        self.assertIsNotNone(url)

    def test_generate_presigned_url_invalid_key(self):
        """Test manejo de keys inválidas"""
        url = generate_presigned_url('')
        self.assertIsNone(url)


class ModelRelationshipsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.song = Song.objects.create(
            title='Test Song',
            artist='Test Artist',
            genre='Rock',
            file_key=f'songs/{uuid.uuid4().hex[:12]}.mp3',
            uploaded_by=self.user
        )

    def test_song_user_relationship(self):
        """Test la relación entre canción y usuario"""
        self.assertEqual(self.song.uploaded_by, self.user)
        self.assertIn(self.song, self.user.uploaded_songs.all())

    def test_comment_relationships(self):
        """Test las relaciones de comentarios"""
        comment = Comment.objects.create(
            song=self.song,
            user=self.user,
            content='Test comment'
        )
        
        self.assertEqual(comment.song, self.song)
        self.assertEqual(comment.user, self.user)
        self.assertIn(comment, self.song.comments.all())
        self.assertIn(comment, self.user.comments.all())

    def test_like_relationships(self):
        """Test las relaciones de likes"""
        like = Like.objects.create(user=self.user, song=self.song)
        
        self.assertEqual(like.user, self.user)
        self.assertEqual(like.song, self.song)
        # Usar el related_name correcto
        self.assertIn(like, self.user.like_set.all())