# notifications/push_providers.py
"""
Proveedores de notificaciones push.
Soporte para Firebase Cloud Messaging (iOS/Android) y Web Push (VAPID).
"""

import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class FirebasePushProvider:
    """
    Proveedor de notificaciones push con Firebase Cloud Messaging.
    Para iOS y Android.
    """
    
    def __init__(self):
        self.initialized = False
        self.messaging = None
        self._initialize()
    
    def _initialize(self):
        """Inicializar Firebase SDK"""
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging
            
            if not firebase_admin._apps:
                cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
                if cred_path:
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    self.messaging = messaging
                    self.initialized = True
                    logger.info("Firebase Cloud Messaging inicializado")
                else:
                    logger.warning("FIREBASE_CREDENTIALS_PATH no configurado. Push deshabilitado.")
            
            else:
                self.messaging = messaging
                self.initialized = True
                
        except ImportError:
            logger.warning("firebase-admin no instalado. Ejecutar: pip install firebase-admin")
        except Exception as e:
            logger.error(f"Error inicializando Firebase: {e}")
    
    def send(self, device_token, title, body, data=None, click_action=None):
        """Enviar notificación push a un dispositivo."""
        if not self.initialized or not self.messaging:
            logger.error("Firebase no inicializado")
            return False
        
        try:
            message_data = data or {}
            if click_action:
                message_data['click_action'] = click_action
            
            message = self.messaging.Message(
                notification=self.messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=message_data,
                token=device_token,
            )
            
            if click_action:
                message.android = self.messaging.AndroidConfig(
                    priority='high',
                    notification=self.messaging.AndroidNotification(
                        click_activity=click_action,
                        sound='default'
                    )
                )
            
            message.apns = self.messaging.APNSConfig(
                payload=self.messaging.APNSPayload(
                    aps=self.messaging.Aps(
                        sound='default',
                        badge=1
                    )
                )
            )
            
            response = self.messaging.send(message)
            logger.debug(f"Push enviado: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Error enviando push a {device_token}: {e}")
            return False


class WebPushProvider:
    """
    Proveedor de Web Push (VAPID) para navegadores.
    """
    
    def __init__(self):
        self.vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', None)
        self.vapid_public_key = getattr(settings, 'VAPID_PUBLIC_KEY', None)
        self.vapid_email = getattr(settings, 'VAPID_EMAIL', None)
        
        if not all([self.vapid_private_key, self.vapid_public_key, self.vapid_email]):
            logger.warning("VAPID no configurado. Web push deshabilitado.")
    
    def send(self, subscription_info, title, body, data=None):
        """Enviar notificación web push."""
        if not all([self.vapid_private_key, self.vapid_public_key, self.vapid_email]):
            logger.error("VAPID no configurado")
            return False
        
        try:
            from pywebpush import webpush, WebPushException
            
            webpush(
                subscription_info=subscription_info,
                data=body,
                vapid_private_key=self.vapid_private_key,
                vapid_claims={"sub": f"mailto:{self.vapid_email}"},
                ttl=86400
            )
            logger.debug(f"Web push enviado")
            return True
            
        except WebPushException as e:
            logger.error(f"Error enviando web push: {e}")
            return False
        except ImportError:
            logger.error("pywebpush no instalado. Ejecutar: pip install pywebpush")
            return False
        except Exception as e:
            logger.error(f"Error enviando web push: {e}")
            return False


class MockPushProvider:
    """
    Proveedor mock para desarrollo.
    Simula envío de push sin conexión externa.
    """
    
    def send(self, device_token, title, body, data=None, click_action=None):
        logger.info(f"[MOCK PUSH] to {device_token}: {title}")
        logger.debug(f"   Body: {body}")
        logger.debug(f"   Data: {data}")
        logger.debug(f"   Click Action: {click_action}")
        return True


_firebase_provider = None
_webpush_provider = None
_mock_provider = None


def get_push_provider(device_type):
    """
    Obtener el proveedor de push según el tipo de dispositivo.
    En desarrollo, usa mock si no hay configuración.
    """
    global _firebase_provider, _webpush_provider, _mock_provider
    
    is_production = getattr(settings, 'DEBUG', True) is False
    
    if device_type in ['ios', 'android']:
        if _firebase_provider is None:
            _firebase_provider = FirebasePushProvider()
            if not is_production and not _firebase_provider.initialized:
                logger.info("Usando MockPushProvider para desarrollo")
                if _mock_provider is None:
                    _mock_provider = MockPushProvider()
                return _mock_provider
        return _firebase_provider
    
    elif device_type == 'web':
        if _webpush_provider is None:
            _webpush_provider = WebPushProvider()
            if not is_production and not _webpush_provider.vapid_private_key:
                logger.info("Usando MockPushProvider para desarrollo")
                if _mock_provider is None:
                    _mock_provider = MockPushProvider()
                return _mock_provider
        return _webpush_provider
    
    return None