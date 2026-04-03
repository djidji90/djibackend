# wallet/health.py - NUEVO ARCHIVO
"""
Health check endpoint - Separado para evitar circular imports
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.core.cache import cache
from datetime import datetime


class WalletHealthCheckView(APIView):
    """
    GET /api/wallet/health/
    Health check para monitoreo del sistema.
    Sin autenticación para permitir monitoreo externo.
    """
    permission_classes = []
    
    def get(self, request):
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'checks': {
                'database': 'unknown',
                'cache': 'unknown'
            }
        }
        
        # Check database
        try:
            connection.ensure_connection()
            health_status['checks']['database'] = 'ok'
        except Exception as e:
            health_status['status'] = 'unhealthy'
            health_status['checks']['database'] = f'error: {str(e)}'
        
        # Check cache
        try:
            cache.set('health_check', 'ok', timeout=5)
            if cache.get('health_check') == 'ok':
                health_status['checks']['cache'] = 'ok'
            else:
                health_status['checks']['cache'] = 'error'
        except Exception as e:
            health_status['status'] = 'degraded'
            health_status['checks']['cache'] = f'error: {str(e)}'
        
        status_code = status.HTTP_200_OK if health_status['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return Response(health_status, status=status_code)