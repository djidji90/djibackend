import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta
import dj_database_url
from kombu import Queue

# ================================
# CONFIGURACIÓN BASE
# ================================

# Cargar variables de entorno
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Seguridad
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost,djibackend-production.up.railway.app,djidjimusic.com,www.djidjimusic.com,api.djidjimusic.com,testserver'
).split(',')

# ================================
# URLs BASE
# ================================

SITE_URL = os.getenv('SITE_URL', 'https://djidjimusic.com')
API_URL = os.getenv('API_URL', 'https://api.djidjimusic.com')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://djidjimusic.com')

# ================================
# TAMAÑOS DE ARCHIVO
# ================================

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB límite absoluto
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# ================================
# LÍMITES Y CUOTAS - CONSOLIDADO Y OPTIMIZADO
# ================================

UPLOAD_LIMITS = {
    'free': {
        'max_daily_uploads': 50,
        'max_daily_size': 500 * 1024 * 1024,  # 500MB
        'max_file_size': 100 * 1024 * 1024,  # 100MB
        'max_total_storage': 5 * 1024 * 1024 * 1024,  # 5GB
    },
    'premium': {
        'max_daily_uploads': 200,
        'max_daily_size': 5 * 1024 * 1024 * 1024,  # 5GB
        'max_file_size': 500 * 1024 * 1024,  # 500MB
        'max_total_storage': 50 * 1024 * 1024 * 1024,  # 50GB
    },
    'admin': {
        'max_daily_uploads': 1000,
        'max_daily_size': 50 * 1024 * 1024 * 1024,  # 50GB
        'max_file_size': 2 * 1024 * 1024 * 1024,  # 2GB
        'max_total_storage': 500 * 1024 * 1024 * 1024,  # 500GB
    }
}

# Límites específicos por tipo de archivo
MAX_AUDIO_SIZE = 100 * 1024 * 1024  # 100MB para audio
MAX_IMAGE_SIZE = 20 * 1024 * 1024   # 20MB para imágenes

# ================================
# CSRF + CORS CONFIGURACIÓN OPTIMIZADA
# ================================

CSRF_TRUSTED_ORIGINS = [
    "https://djidjimusic.com",
    "https://www.djidjimusic.com",
    "https://api.djidjimusic.com",
    "https://www.api.djidjimusic.com",
    "https://djibackend-production.up.railway.app",
    "http://localhost:5173"
]

CORS_ALLOWED_ORIGINS = [
    "https://djidjimusic.com",
    "https://www.djidjimusic.com",
    "https://api.djidjimusic.com",
    "https://www.api.djidjimusic.com",
    "https://djibackend-production.up.railway.app",
    "http://localhost:5173"
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.djidjimusic\.com$",
    r"^https://djibackend-production\.up\.railway\.app$",
]

# Permitir localhost en desarrollo
if DEBUG:
    CORS_ALLOWED_ORIGINS.extend([
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5176",
    ])
    CSRF_TRUSTED_ORIGINS.extend([
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5176",
    ])

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# ============================================
# 🎵 CONFIGURACIÓN CORS PARA STREAMING (NUEVO)
# ============================================

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-file-name',
    'x-file-size',
    'x-upload-id',
]

# Headers adicionales para streaming
CORS_ALLOW_HEADERS += [
    'range',
    'content-range',
    'accept-ranges',
    'if-range',
]

# Headers expuestos para streaming
CORS_EXPOSE_HEADERS = [
    'accept-ranges',
    'content-range',
    'content-length',
    'etag',
    'x-cache-status',
    'x-cache-ttl',
    'x-url-expiration',
]

# ================================
# USUARIO PERSONALIZADO
# ================================

AUTH_USER_MODEL = 'musica.CustomUser'

# ================================
# APLICACIONES INSTALADAS
# ================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Apps locales
    'musica',
    'api2',
    'django_filters',
    
    # Librerías externas
    "django_celery_beat",
    "django_celery_results",
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'storages',
    'django_extensions',
]

# ================================
# MIDDLEWARE OPTIMIZADO
# ================================

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api2.middleware.TimeoutMiddleware',
]

ROOT_URLCONF = 'backend.urls'

# ================================
# TEMPLATES
# ================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# ================================
# BASE DE DATOS
# ================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 30,
        }
    }
}

# Detectar entorno y configurar base de datos apropiada
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL and not DEBUG:
    try:
        if 'postgresql://' in DATABASE_URL or 'postgres://' in DATABASE_URL:
            DATABASES['default'] = dj_database_url.parse(
                DATABASE_URL,
                conn_max_age=600,
                conn_health_checks=True,
                ssl_require=True,
            )
            DATABASES['default']['CONN_MAX_AGE'] = 60
            DATABASES['default']['OPTIONS'] = {
                'connect_timeout': 10,
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
            }
            print("PostgreSQL configurado para producción con optimizaciones")
        else:
            print("DATABASE_URL no es de PostgreSQL. Usando SQLite.")
    except Exception as e:
        print(f"Error configurando PostgreSQL: {e}")
        print("Usando SQLite como fallback")
else:
    print("SQLite en uso para desarrollo local")

# ================================
# ARCHIVOS ESTÁTICOS
# ================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

WHITENOISE_MAX_AGE = 31536000
WHITENOISE_USE_FINDERS = True
WHITENOISE_MANIFEST_STRICT = False

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ================================
# CLOUDFLARE R2 CONFIG
# ================================

R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")

R2_UPLOADS_PREFIX = 'uploads/'
R2_PRESIGNED_EXPIRY = 3600
R2_MAX_FILE_SIZE = MAX_UPLOAD_SIZE
R2_DOWNLOAD_URL_EXPIRY = 300

if all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID, R2_BUCKET_NAME]):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
    AWS_S3_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_REGION_NAME = 'auto'
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = 'private'
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_USE_SSL = True
    AWS_S3_VERIFY = True
    AWS_S3_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
    
    print("R2 Configurado correctamente con optimizaciones")
else:
    missing = []
    if not R2_ACCESS_KEY_ID: missing.append('R2_ACCESS_KEY_ID')
    if not R2_SECRET_ACCESS_KEY: missing.append('R2_SECRET_ACCESS_KEY')
    if not R2_ACCOUNT_ID: missing.append('R2_ACCOUNT_ID')
    if not R2_BUCKET_NAME: missing.append('R2_BUCKET_NAME')
    print(f"R2 no configurado. Variables faltantes: {missing}")

# ================================
# VALIDACIÓN DE CONTRASEÑAS
# ================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ================================
# INTERNACIONALIZACIÓN
# ================================

LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ================================
# SEGURIDAD EN PRODUCCIÓN
# ================================

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ================================
# REST FRAMEWORK OPTIMIZADO
# ================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '10000/day',
        'uploads': '50/hour',
        'quota': '100/minute',
        'status': '200/minute',
        'stream': '100/hour',      # 🎵 NUEVO - Streaming usuarios autenticados
        'stream_anon': '10/hour',  # 🎵 NUEVO - Streaming usuarios anónimos
    },
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer' if DEBUG else 'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
    'UNAUTHENTICATED_USER': None,
    'UNAUTHENTICATED_TOKEN': None,
}

# ================================
# JWT CONFIGURACIÓN
# ================================

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': os.getenv('JWT_SECRET_KEY', SECRET_KEY),
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# ================================
# SPECTACULAR
# ================================

SPECTACULAR_SETTINGS = {
    'TITLE': 'DJI Music API',
    'DESCRIPTION': 'API para plataforma de música Dji Music',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
}

# ================================
# LOGGING OPTIMIZADO
# ================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{levelname}] {asctime} {name}: {message}",
            "style": "{",
        },
        "sql": {
            "format": "[SQL] {duration:.3f}s {sql}",
            "style": "{",
        },
        "celery": {
            "format": "[%(asctime)s] [%(name)s] [%(levelname)s] [PID:%(process)d] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs/django.log",
            "maxBytes": 10485760,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "sql_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs/slow_queries.log",
            "maxBytes": 10485760,
            "backupCount": 3,
            "formatter": "sql",
            "level": "WARNING",
        },
        "celery_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs/celery.log",
            "maxBytes": 10485760,
            "backupCount": 3,
            "formatter": "celery",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["sql_file"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
        "musica": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "api2": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console", "celery_file"],
            "level": "INFO",
            "propagate": True,
        },
        "celery.task": {
            "handlers": ["celery_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# Crear directorio de logs si no existe
if not os.path.exists(BASE_DIR / "logs"):
    os.makedirs(BASE_DIR / "logs")

# ================================
# CACHE - OPTIMIZADO PARA PRODUCCIÓN
# ================================

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"{REDIS_URL}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_CLASS": "redis.BlockingConnectionPool",
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "timeout": 20,
            },
            "MAX_CONNECTIONS": 1000,
            "PICKLE_VERSION": -1,
            "SOCKET_KEEPALIVE": True,
            "SOCKET_TIMEOUT": 5,
        },
        "KEY_PREFIX": "dji",
        "TIMEOUT": 300,
    }
}

# ============================================
# 🎵 CONFIGURACIÓN DE CACHE PARA STREAMING (NUEVO)
# ============================================

PRESIGNED_URL_CACHE_TIMEOUT = 1800  # 30 minutos
FILE_EXISTS_CACHE_TIMEOUT = 300      # 5 minutos
R2_CACHE_PREFIX = "r2"
STREAM_URL_EXPIRATION = 300          # 5 minutos para URLs firmadas

# Tiempos de cache específicos por vista
VIEW_CACHE_TIMES = {
    'quota_view': 30,
    'status_view': 10,
    'user_profile': 60,
    'track_list': 120,
    'stream_url': 300,      # 🎵 URLs de streaming
    'stream_metadata': 600, # 🎵 Metadata de canciones
}

# Configuración de sesiones en cache
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 1209600
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ================================
# CELERY
# ================================

CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = 'django-db'

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_POOL_LIMIT = 10
CELERY_BROKER_HEARTBEAT = 10
CELERY_BROKER_CONNECTION_TIMEOUT = 30
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': 3600,
    'max_retries': 3,
    'interval_start': 0,
    'interval_step': 0.2,
    'interval_max': 0.5,
    'fanout_prefix': True,
    'fanout_patterns': True,
    'socket_keepalive': True,
    'socket_timeout': 5,
}

CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 200000
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Configuración de colas
CELERY_TASK_QUEUES = (
    Queue('default'),
    Queue('uploads'),
    Queue('maintenance'),
)

CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_DEFAULT_EXCHANGE = 'default'
CELERY_TASK_DEFAULT_ROUTING_KEY = 'default'
CELERY_TASK_CREATE_MISSING_QUEUES = True

CELERY_TASK_ANNOTATIONS = {
    'musica.tasks.process_upload': {
        'rate_limit': '10/m'
    }
}

# ================================
# CONFIGURACIONES FINALES
# ================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ================================
# FUNCIONES DE OPTIMIZACIÓN
# ================================

def create_database_indexes():
    """Crear índices necesarios para optimizar queries"""
    print("\n=== OPTIMIZANDO BASE DE DATOS CON ÍNDICES ===")
    
    indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_uploadsession_status ON musica_uploadsession(status);",
        "CREATE INDEX IF NOT EXISTS idx_uploadsession_user_status ON musica_uploadsession(user_id, status);",
        "CREATE INDEX IF NOT EXISTS idx_uploadsession_created ON musica_uploadsession(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_uploadsession_expires ON musica_uploadsession(expires_at) WHERE status = 'pending';",
        "CREATE INDEX IF NOT EXISTS idx_uploadquota_user_date ON musica_uploadquota(user_id, date);",
        "CREATE INDEX IF NOT EXISTS idx_uploadquota_user ON musica_uploadquota(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_customuser_email ON musica_customuser(email);",
        "CREATE INDEX IF NOT EXISTS idx_customuser_username ON musica_customuser(username);",
        "CREATE INDEX IF NOT EXISTS idx_track_user ON musica_track(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_track_created ON musica_track(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_track_status ON musica_track(status);",
    ]
    
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            for sql in indexes_sql:
                try:
                    cursor.execute(sql)
                    print(f"Indice creado: {sql[:50]}...")
                except Exception as e:
                    if "already exists" not in str(e):
                        print(f"Error creando indice: {e}")
    except Exception as e:
        print(f"No se pudieron crear indices: {e}")

if os.getenv('CREATE_INDEXES_ON_STARTUP', 'False') == 'True':
    create_database_indexes()

# ================================
# RESUMEN DE CONFIGURACIÓN
# ================================

print("""
 ╔════════════════════════════════════════════════════════════╗
 ║  🎵 DJI MUSIC API - CONFIGURACIÓN COMPLETA                 ║
 ╠════════════════════════════════════════════════════════════╣
 ║  • Streaming optimizado con URLs firmadas                  ║
 ║  • Rate limiting: 100 streams/hora por usuario             ║
 ║  • Cache Redis: URLs cacheadas 30 minutos                  ║
 ║  • CORS headers para streaming configurados                ║
 ║  • Colas Celery: default, uploads, maintenance             ║
 ║  • Listo para producción                                   ║
 ╚════════════════════════════════════════════════════════════╝
""")