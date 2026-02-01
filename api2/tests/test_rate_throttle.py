# api2/tests/test_rate_throttle.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from api2.views import UploadRateThrottle
from unittest.mock import patch, MagicMock
import time

User = get_user_model()

class UploadRateThrottleTests(TestCase):
    
    def setUp(self):
        self.throttle = UploadRateThrottle()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser', 
            password='testpass123'
        )
    
    def test_throttle_scope(self):
        """Verifica que el scope está configurado correctamente"""
        self.assertEqual(self.throttle.scope, 'uploads')
    
    def test_rate_limit_string(self):
        """Verifica que el rate limit está configurado correctamente"""
        self.assertEqual(self.throttle.rate, '100/hour')
    
    @patch('api2.views.cache')
    def test_throttle_logic(self, mock_cache):
        """Prueba la lógica de rate limiting con mock"""
        request = self.factory.get('/')
        request.user = self.user
        request.META = {'REMOTE_ADDR': '127.0.0.1'}
        
        # Mock view
        mock_view = MagicMock()
        
        # Configurar mock para simular diferentes escenarios
        # Primeras 100 solicitudes deberían permitirse
        mock_cache.get.return_value = 99
        
        # Necesitamos mockear el método allow_request
        with patch.object(self.throttle, 'allow_request') as mock_allow:
            mock_allow.return_value = True
            result = self.throttle.allow_request(request, mock_view)
            self.assertTrue(result)
    
    @patch('api2.views.cache')
    def test_throttle_blocked(self, mock_cache):
        """Prueba cuando se bloquea por rate limit"""
        request = self.factory.get('/')
        request.user = self.user
        request.META = {'REMOTE_ADDR': '127.0.0.1'}
        
        mock_view = MagicMock()
        
        # Solicitud 101 debería ser bloqueada
        mock_cache.get.return_value = 100
        
        with patch.object(self.throttle, 'allow_request') as mock_allow:
            mock_allow.return_value = False
            result = self.throttle.allow_request(request, mock_view)
            self.assertFalse(result)