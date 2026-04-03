# wallet/monitoring/metrics.py
"""
Métricas Prometheus para el sistema wallet
"""
from prometheus_client import Counter, Histogram, Gauge, Summary
import time

# Contadores de operaciones
DEPOSITS_TOTAL = Counter(
    'wallet_deposits_total',
    'Total número de depósitos',
    ['status', 'method']
)

PURCHASES_TOTAL = Counter(
    'wallet_purchases_total',
    'Total número de compras',
    ['status']
)

WITHDRAWALS_TOTAL = Counter(
    'wallet_withdrawals_total',
    'Total número de retiros',
    ['status', 'method']
)

OFFICE_WITHDRAWALS_TOTAL = Counter(
    'wallet_office_withdrawals_total',
    'Total número de retiros en oficina',
    ['status', 'office_id']
)

# Histogramas de latencia
TRANSACTION_DURATION = Histogram(
    'wallet_transaction_duration_seconds',
    'Duración de transacciones',
    ['operation'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5)
)

API_LATENCY = Histogram(
    'wallet_api_latency_seconds',
    'Latencia de endpoints de API',
    ['endpoint', 'method'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2)
)

# Gauges (estados actuales)
ACTIVE_USERS = Gauge(
    'wallet_active_users',
    'Usuarios activos en los últimos 5 minutos'
)

PENDING_HOLDS_TOTAL = Gauge(
    'wallet_pending_holds_total',
    'Total de holds pendientes'
)

TOTAL_BALANCE = Gauge(
    'wallet_total_balance',
    'Balance total en el sistema',
    ['currency']
)

# Summary para errores
ERRORS_TOTAL = Counter(
    'wallet_errors_total',
    'Total de errores por tipo',
    ['error_type', 'endpoint']
)


class MetricsMiddleware:
    """Middleware para capturar métricas de requests"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration = time.time() - start_time
        
        # Registrar latencia de API
        endpoint = request.path
        method = request.method
        
        API_LATENCY.labels(endpoint=endpoint, method=method).observe(duration)
        
        return response


def record_transaction_duration(operation, duration):
    """Registrar duración de transacción"""
    TRANSACTION_DURATION.labels(operation=operation).observe(duration)


def record_error(error_type, endpoint):
    """Registrar error"""
    ERRORS_TOTAL.labels(error_type=error_type, endpoint=endpoint).inc()