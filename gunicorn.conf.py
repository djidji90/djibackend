# gunicorn_config_fixed.py - VERSIÓN CORREGIDA
import os
from gevent import monkey
monkey.patch_all()

bind = "0.0.0.0:8000"
workers = 4
worker_class = "gevent"
worker_connections = 1000
timeout = 180
graceful_timeout = 60
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
limit_request_line = 4096
limit_request_fields = 50
limit_request_field_size = 8190

# ❌ NO USAR worker_abort = False
# ✅ Dejarlo sin definir o usar None

accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

def on_starting(server):
    server.log.info("🚀 Gunicorn iniciado con workers async")

print("✅ Gunicorn config fixed para Railway")