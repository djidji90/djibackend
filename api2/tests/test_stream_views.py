# api2/tests/test_stream_views.py
"""
Tests para las vistas de streaming
==================================
✅ Rate limiting
✅ Permisos (públicas/privadas)
✅ Generación de URLs
✅ Cache
✅ Manejo de errores
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.conf import settings
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from rest_framework.response import Response
from unittest.mock import patch, MagicMock, PropertyMock
import time

from api2.models import Song
from api2.views import StreamSongView, StreamRateThrottle

User = get_user_model()

class StreamRateThrottleTests(APITestCase):
    """Tests para el rate limiting de streaming"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='jordi',
            email='jordi@example.com',
            password='machimbo90'
        )
        self.request = MagicMock()
        self.request.user = self.user
        self.request.path = '/api2/songs/1/stream/'
        self.request.META = {'REMOTE_ADDR': '127.0.0.1'}
    
    def test_cache_key_generation_authenticated(self):
        """Verifica que la clave de cache para usuario autenticado es correcta"""
        throttle = StreamRateThrottle()
        
        # Usar PropertyMock para is_authenticated
        type(self.request.user).is_authenticated = PropertyMock(return_value=True)
        self.request.user.pk = self.user.pk
        
        cache_key = throttle.get_cache_key(self.request, None)
        self.assertIn(f"user_{self.user.pk}", cache_key)
        self.assertIn("stream", cache_key)
    
    def test_cache_key_generation_anonymous(self):
        """Verifica que la clave de cache para usuario anónimo es correcta"""
        throttle = StreamRateThrottle()
        
        # Configurar mock para usuario anónimo
        anon_request = MagicMock()
        anon_request.user.is_authenticated = False
        
        # Mock get_ident
        with patch.object(throttle, 'get_ident', return_value='1.2.3.4'):
            cache_key = throttle.get_cache_key(anon_request, None)
            self.assertIn("anon_1.2.3.4", cache_key)
            self.assertIn("stream", cache_key)


class StreamSongViewTests(APITestCase):
    """Tests para la vista principal de streaming"""
    
    def setUp(self):
        # Crear usuarios
        self.user = User.objects.create_user(
            username='jordi',
            email='jordi@example.com',
            password='machimbo90'
        )
        self.other_user = User.objects.create_user(
            username='otro_usuario',
            email='otro@example.com',
            password='machimbo90'
        )
        self.staff_user = User.objects.create_user(
            username='staff_jordi',
            email='staff.jordi@example.com',
            password='machimbo90',
            is_staff=True
        )
        
        # Canción pública del usuario principal
        self.public_song = Song.objects.create(
            title='Mi Canción Pública',
            artist='Jordi',
            file_key='canciones/jordi/publica.mp3',
            duration='180',
            genre='Pop',
            uploaded_by=self.user,
            is_public=True
        )
        
        # Canción privada del usuario principal
        self.private_song = Song.objects.create(
            title='Mi Canción Privada',
            artist='Jordi',
            file_key='canciones/jordi/privada.mp3',
            duration='180',
            genre='Pop',
            uploaded_by=self.user,
            is_public=False
        )
        
        # Canción sin dueño
        self.orphan_song = Song.objects.create(
            title='Canción Huérfana',
            artist='Desconocido',
            file_key='canciones/orphan.mp3',
            duration='180',
            genre='Rock',
            uploaded_by=None,
            is_public=True
        )
        
        self.url_public = reverse('song-stream', args=[self.public_song.id])
        self.url_private = reverse('song-stream', args=[self.private_song.id])
        
        # Limpiar cache
        cache.clear()
    
    def test_stream_unauthenticated(self):
        """Verifica que usuarios no autenticados no pueden acceder"""
        response = self.client.get(self.url_public)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_stream_song_not_found(self):
        """Verifica manejo de canción inexistente"""
        self.client.force_authenticate(user=self.user)
        url = reverse('song-stream', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_stream_song_no_file_key(self):
        """Verifica manejo de canción sin archivo (usando el valor por defecto)"""
        # Crear canción normal (se generará un file_key automático)
        song_no_file = Song.objects.create(
            title='Canción sin archivo',
            artist='Jordi',
            duration='180',
            genre='Pop',
            uploaded_by=self.user,
            is_public=True
        )
        
        # 🟢 SOBREESCRIBIR con el valor problemático (bypass del save())
        Song.objects.filter(id=song_no_file.id).update(file_key='songs/temp_file')
        song_no_file.refresh_from_db()
        
        self.client.force_authenticate(user=self.user)
        url = reverse('song-stream', args=[song_no_file.id])
        response = self.client.get(url)
        
        # 🟢 AHORA SÍ DEBE DAR 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['code'], 'MISSING_FILE')
    
    @patch('api2.views.generate_presigned_url')
    def test_public_song_accessible_by_any_user(self, mock_generate_url):
        """Verifica que canciones públicas son accesibles por cualquier usuario autenticado"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url_public)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('stream_url', response.data['data'])
        self.assertEqual(response.data['song']['id'], self.public_song.id)
    
    @patch('api2.views.generate_presigned_url')
    def test_owner_can_access_private_song(self, mock_generate_url):
        """Verifica que el dueño puede acceder a su canción privada"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        
        self.client.force_authenticate(user=self.user)  # dueño
        response = self.client.get(self.url_private)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    @patch('api2.views.generate_presigned_url')
    def test_other_user_cannot_access_private_song(self, mock_generate_url):
        """Verifica que otro usuario no puede acceder a canción privada"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        
        self.client.force_authenticate(user=self.other_user)  # otro usuario
        response = self.client.get(self.url_private)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'PERMISSION_DENIED')
    
    @patch('api2.views.generate_presigned_url')
    def test_staff_can_access_private_song(self, mock_generate_url):
        """Verifica que staff puede acceder a cualquier canción privada"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.url_private)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    @patch('api2.views.generate_presigned_url')
    def test_orphan_public_song_accessible(self, mock_generate_url):
        """Verifica que canción pública sin dueño es accesible"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        
        self.client.force_authenticate(user=self.user)
        url = reverse('song-stream', args=[self.orphan_song.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    @patch('api2.views.generate_presigned_url')
    def test_url_generation_failure(self, mock_generate_url):
        """Verifica manejo de error en generación de URL"""
        mock_generate_url.return_value = None  # Error generando URL
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url_public)
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['code'], 'URL_GENERATION_FAILED')
    
    @patch('api2.views.get_file_info')
    @patch('api2.views.generate_presigned_url')
    def test_stream_with_file_info(self, mock_generate_url, mock_file_info):
        """Verifica que se incluye file_size cuando está disponible"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        mock_file_info.return_value = {'size': 5242880}
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url_public)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['file_size'], 5242880)


class StreamSongViewCacheTests(APITestCase):
    """Tests específicos para el sistema de cache"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='jordi',
            email='jordi.cache@example.com',
            password='machimbo90'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        self.song = Song.objects.create(
            title='Canción para test de cache',
            artist='Jordi',
            file_key='canciones/jordi/cache-test.mp3',
            duration='180',
            genre='Pop',
            uploaded_by=self.user,
            is_public=True
        )
        
        self.url = reverse('song-stream', args=[self.song.id])
        cache.clear()
    
    @patch('api2.views.generate_presigned_url')
    def test_cache_hit_after_first_request(self, mock_generate_url):
        """Verifica que la segunda request usa cache"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        
        # Primera request - cache miss
        response1 = self.client.get(self.url)
        self.assertEqual(response1['X-Cache-Status'], 'MISS')
        
        # Segunda request - debería ser cache hit
        response2 = self.client.get(self.url)
        self.assertEqual(response2['X-Cache-Status'], 'HIT')
        
        # generate_presigned_url solo debería llamarse una vez
        mock_generate_url.assert_called_once()
    
@patch('api2.views.generate_presigned_url')
def test_different_expiration_cache_keys(self, mock_generate_url):
    """Verifica que diferentes expiraciones usan diferentes claves de cache"""
    mock_generate_url.return_value = 'https://r2.test/stream-url'
    
    # Primera request con expiración por defecto (300)
    response1 = self.client.get(self.url)
    self.assertEqual(response1['X-Cache-Status'], 'MISS')
    
    # 🟢 IMPORTANTE: Resetear cache también
    cache.clear()
    
    # Resetear mock
    mock_generate_url.reset_mock()
    mock_generate_url.return_value = 'https://r2.test/stream-url-600'
    
    # Segunda request con expiración diferente
    with patch.object(StreamSongView, 'URL_EXPIRATION', 600):
        response2 = self.client.get(self.url)
        self.assertEqual(response2['X-Cache-Status'], 'MISS')
    
    # Verificar que se llamó dos veces
    self.assertEqual(mock_generate_url.call_count, 2)


class StreamSongViewCompatTests(APITestCase):
    """Tests para la vista de compatibilidad (redirect)"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='jordi',
            email='jordi.compat@example.com',
            password='machimbo90'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        self.song = Song.objects.create(
            title='Canción para compatibilidad',
            artist='Jordi',
            file_key='canciones/jordi/compat.mp3',
            duration='180',
            genre='Pop',
            uploaded_by=self.user,
            is_public=True
        )
        
        self.url = reverse('song-stream-legacy', args=[self.song.id])
    
    @patch('api2.views.generate_presigned_url')
    def test_redirect_to_stream_url(self, mock_generate_url):
        """Verifica que la vista de compatibilidad redirige correctamente"""
        stream_url = 'https://r2.test/stream-url'
        mock_generate_url.return_value = stream_url
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.url, stream_url)
        
        # Verificar headers de no-cache
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')
    
    @patch('api2.views.StreamSongView.get')
    def test_redirect_handles_errors(self, mock_stream_view_get):
        """Verifica que la vista de compatibilidad maneja errores"""
        # Simular error en la vista principal
        error_response = Response(
            {'error': 'not_found'},
            status=status.HTTP_404_NOT_FOUND
        )
        mock_stream_view_get.return_value = error_response
        
        response = self.client.get(self.url)
        
        # Debe devolver el mismo error
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class StreamSongViewDebugTests(APITestCase):
    """Tests para la vista de debug"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='jordi',
            email='jordi.debug@example.com',
            password='machimbo90'
        )
        self.client = APIClient()
        self.url = reverse('stream-debug')
    
    @override_settings(DEBUG=True)
    def test_debug_view_requires_authentication(self):
        """Verifica que debug view requiere autenticación incluso en DEBUG"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    @override_settings(DEBUG=True)
    @patch('api2.views.test_r2_connection')
    def test_debug_view_authenticated(self, mock_r2_conn):
        """Verifica que debug view funciona autenticado"""
        self.client.force_authenticate(user=self.user)
        mock_r2_conn.return_value = {'status': 'ok'}
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('environment', response.data)
        self.assertEqual(response.data['environment']['user'], self.user.id)
    
    @override_settings(DEBUG=False)
    def test_debug_view_disabled_in_production(self):
        """Verifica que debug view no está disponible en producción"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class StreamMetricsViewTests(APITestCase):
    """Tests para el endpoint de métricas"""
    
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='jordi_staff',
            email='jordi.staff@example.com',
            password='machimbo90',
            is_staff=True
        )
        self.user = User.objects.create_user(
            username='jordi',
            email='jordi.metrics@example.com',
            password='machimbo90'
        )
        self.url = reverse('stream-metrics')
    
    @override_settings(DEBUG=True)
    @patch('api2.views.METRICS_AVAILABLE', True)
    @patch('api2.views.generate_latest')
    def test_metrics_accessible_in_debug_without_auth(self, mock_generate):
        """Verifica que en DEBUG no requiere autenticación"""
        mock_generate.return_value = b'metrics data'
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    @override_settings(DEBUG=False)
    @patch('api2.views.METRICS_AVAILABLE', True)
    @patch('api2.views.generate_latest')
    def test_metrics_require_staff_in_production(self, mock_generate):
        """Verifica que en producción solo staff puede acceder"""
        mock_generate.return_value = b'metrics data'
        
        # Usuario no autenticado - debe dar 401
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        
        # Usuario autenticado pero no staff - debe dar 403
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Staff puede
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    @patch('api2.views.METRICS_AVAILABLE', False)
    def test_metrics_not_available(self):
        """Verifica manejo cuando prometheus no está instalado"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)


class StreamSongViewIntegrationTests(APITestCase):
    """Tests de integración con R2 real (usando mocks)"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='jordi',
            email='jordi.integration@example.com',
            password='machimbo90'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        self.song = Song.objects.create(
            title='Mi Canción de Prueba',
            artist='Jordi',
            file_key='canciones/jordi/mi-cancion.mp3',
            duration='180',
            genre='Pop',
            uploaded_by=self.user,
            is_public=True
        )
        
        self.url = reverse('song-stream', args=[self.song.id])
    
    @patch('api2.views.generate_presigned_url')
    @patch('api2.views.get_file_info')
    def test_complete_stream_flow(self, mock_file_info, mock_generate_url):
        """Prueba el flujo completo de streaming"""
        mock_generate_url.return_value = 'https://r2.test/stream-url'
        mock_file_info.return_value = {
            'size': 5242880,
            'content_type': 'audio/mpeg'
        }
        
        response = self.client.get(self.url)
        
        # Verificar estructura completa
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Data
        self.assertIn('data', response.data)
        self.assertIn('stream_url', response.data['data'])
        self.assertIn('expires_in', response.data['data'])
        self.assertIn('expires_at', response.data['data'])
        self.assertIn('file_size', response.data['data'])
        
        # Song info
        self.assertIn('song', response.data)
        self.assertEqual(response.data['song']['id'], self.song.id)
        self.assertEqual(response.data['song']['title'], self.song.title)
        
        # Meta
        self.assertIn('meta', response.data)
        self.assertIn('request_id', response.data['meta'])
        self.assertIn('timestamp', response.data['meta'])
        self.assertIn('cache', response.data['meta'])
        
        # Headers
        self.assertIn('X-Cache-Status', response)
        self.assertIn('X-Cache-TTL', response)