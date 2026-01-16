# gunicorn.conf.py
import multiprocessing

# Configuración para subidas grandes a R2
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'  # O 'gevent' si instalas gunicorn[gevent]
timeout = 300  # 5 minutos para subidas grandes (default: 30s)
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Para subidas grandes
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190