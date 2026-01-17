# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8080"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"

# ⭐⭐ INCREMENTAR ESTOS TIMEOUTS ⭐⭐
timeout = 300  # 5 minutos (default: 30)
keepalive = 5
graceful_timeout = 300

# Para archivos grandes
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"