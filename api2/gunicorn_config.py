# gunicorn_config.py
import multiprocessing
import os

# Configuración básica
bind = "0.0.0.0:8000"

# Número de workers - para 3MB files, podemos optimizar
workers = 2  # Menos workers pero más estables
worker_class = "sync"

# ⚠️ CRÍTICO: Timeout más largo pero no excesivo
timeout = 120  # 2 minutos (suficiente para 3MB)
graceful_timeout = 30
keepalive = 2

# Configuración específica para requests HTTP
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Configuración de buffers (importante para archivos)
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Para evitar que workers mueran por inactividad
worker_abort = False

# Logging detallado
accesslog = "-"
errorlog = "-"
loglevel = "debug"  # Cambia a debug para ver más información
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

# Hooks para debugging
def on_starting(server):
    server.log.info("🚀 Gunicorn iniciando...")

def post_fork(server, worker):
    server.log.info(f"👷 Worker {worker.pid} creado")

def worker_int(worker):
    worker.log.info("⚠️ Worker recibió señal INT o QUIT")

def worker_abort(worker):
    worker.log.info("🚨 Worker recibió SIGABRT")

def pre_exec(server):
    server.log.info("🔧 Fork del master process")

def pre_request(worker, req):
    worker.log.debug(f"📥 Request: {req.method} {req.path}")

def post_request(worker, req, environ, resp):
    worker.log.debug(f"📤 Response: {resp.status}")

def worker_exit(server, worker):
    server.log.info(f"👋 Worker {worker.pid} saliendo")