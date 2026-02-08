"""
Patch para tests - Evita problemas de Redis/Celery en tests
"""
import sys
import uuid
import os

if os.environ.get('RUNNING_TESTS', '0') == '1' or 'test' in sys.argv:
    from celery import Celery
    from django.conf import settings
    from unittest.mock import MagicMock

    class MockCeleryApp(Celery):
        def send_task(self, name, args=None, kwargs=None, **options):
            mock = MagicMock()
            mock.id = f"mock-task-{uuid.uuid4().hex[:8]}"
            return mock

    settings.CELERY_BROKER_URL = 'memory://'
    settings.CELERY_RESULT_BACKEND = 'cache+memory://'
