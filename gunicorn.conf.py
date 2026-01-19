# gunicorn_config.py - OPTIMIZADO PARA RAILWAY
import multiprocessing
import os

# ================================
# 🚀 CONFIGURACIÓN GUNICORN PRODUCCIÓN
# ================================
bind = "0.0.0.0:8000"

# Workers basados en memoria disponible (Railway Hobby: 512MB RAM)
# Fórmula: (RAM total - overhead) / RAM por worker
# Django worker: ~50-100MB, usamos 80MB como base
available_ram = 512  # MB en Railway Hobby
worker_ram = 80  # MB por worker
max_workers = max(2, (available_ram - 100) // worker_ram)  # Dejar 100MB para sistema

workers = min(max_workers, multiprocessing.cpu_count() * 2 + 1)
workers = 4  # Valor seguro para Railway Hobby

# Worker class ASYNC (CRÍTICO para escalabilidad)
worker_class = "gevent"  # Cambia de "sync" a "gevent"
worker_connections = 1000

# Timeouts optimizados para uploads
timeout = 180  # 3 minutos para uploads grandes
graceful_timeout = 60
keepalive = 5

# Configuración para requests HTTP
max_requests = 1000
max_requests_jitter = 100
limit_request_line = 4096
limit_request_fields = 50
limit_request_field_size = 8190

# Para evitar que workers mueran por inactividad
worker_abort = False

# Logging detallado
accesslog = "-"
errorlog = "-"
loglevel = "info"  # En producción usar 'info', no 'debug'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

# ================================
# 🎯 CONFIGURACIÓN ESPECÍFICA GEVENT
# ================================
# Configuración adicional para gevent
gevent_monkey = True

# ================================
# 📊 HOOKS PARA MONITOREO
# ================================
def on_starting(server):
    server.log.info(f"🚀 Gunicorn iniciando con {workers} workers ({worker_class})")

def post_fork(server, worker):
    server.log.info(f"👷 Worker {worker.pid} creado")

def worker_exit(server, worker):
    server.log.info(f"👋 Worker {worker.pid} saliendo")

def pre_request(worker, req):
    if 'upload' in req.path:
        worker.log.info(f"📥 Upload iniciado: {req.method} {req.path}")

def post_request(worker, req, environ, resp):
    if 'upload' in req.path:
        worker.log.info(f"📤 Upload completado: {resp.status} - {req.path}")

print(f"✅ Gunicorn configurado: {workers} workers, clase: {worker_class}")