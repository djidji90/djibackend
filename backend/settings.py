"""
DJI Music - Configuración de Producción Optimizada
Versión: 2.0 - Escalable para miles de usuarios
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta
import dj_database_url
import logging

# Cargar variables de entorno
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ================================
# 🚨 DETECCIÓN DE ENTORNO
# ================================
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
IS_PRODUCTION = not DEBUG
RAILWAY_ENVIRONMENT = os.getenv('RAILWAY_ENVIRONMENT', '').lower() == 'true'
IS_RAILWAY = bool(os.getenv('RAILWAY_ENVIRONMENT'))

# Log de entorno
print(f"🚀 Entorno: {'PRODUCCIÓN' if IS_PRODUCTION else 'DESARROLLO'}")
print(f"📍 Railway: {'SÍ' if IS_RAILWAY else 'NO'}")

# ================================
# 🔐 SEGURIDAD - CLAVES
# ================================
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY and IS_PRODUCTION:
    print("❌ ERROR: SECRET_KEY no configurada en producción")
    sys.exit(1)

# ================================
# 🌐 HOSTS Y DOMINIOS
# ================================
ALLOWED_HOSTS = [
    'djidjimusic.com',
    'www.djidjimusic.com',
    'api.djidjimusic.com',
    'www.api.djidjimusic.com',
    'djibackend-production.up.railway.app',
    '.railway.app',  # Todos los subdominios railway
]

# En desarrollo, agregar localhost
if DEBUG:
    ALLOWED_HOSTS.extend(['localhost', '127.0.0.1', '0.0.0.0'])

# ================================
# 🔄 CSRF + CORS - PRODUCCIÓN SEGURA
# ================================
CSRF_TRUSTED_ORIGINS = [
    "https://djidjimusic.com",
    "https://www.djidjimusic.com", 
    "https://api.djidjimusic.com",
    "https://www.api.djidjimusic.com",
    "https://djibackend-production.up.railway.app",
]

CORS_ALLOWED_ORIGINS = [
    "https://djidjimusic.com",
    "https://www.djidjimusic.com",
    "https://api.djidjimusic.com",
    "https://www.api.djidjimusic.com",
]

# Solo en desarrollo permitir más orígenes
if DEBUG:
    CORS_ALLOWED_ORIGINS.extend([
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5176",
        "http://localhost:8000",
        "https://djibackend-production.up.railway.app",
    ])

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.djidjimusic\.com$",
    r"^https://.*\.railway\.app$",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
CORS_ALLOW_HEADERS = ['*']

# ================================
# 📊 LÍMITES PARA ARCHIVOS GRANDES (OPTIMIZADO)
# ================================
# Límites realistas para 5,000 usuarios
MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50MB máximo por audio
MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5MB máximo por imagen

DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_AUDIO_SIZE + MAX_IMAGE_SIZE  # 55MB
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_AUDIO_SIZE + MAX_IMAGE_SIZE  # 55MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 50  # Reducido para seguridad

# ================================
# 👤 USUARIO PERSONALIZADO
# ================================
AUTH_USER_MODEL = 'musica.CustomUser'

# ================================
# 📦 APLICACIONES INSTALADAS
# ================================
INSTALLED_APPS = [
    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Apps locales
    'musica',
    'api2',
    
    # Third-party
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'storages',
    'django_filters',
]

# ================================
# 🛡️ MIDDLEWARE OPTIMIZADO
# ================================
MIDDLEWARE = [
    # CORS primero
    'corsheaders.middleware.CorsMiddleware',
    
    # Seguridad Django
    'django.middleware.security.SecurityMiddleware',
    
    # WhiteNoise para archivos estáticos
    'whitenoise.middleware.WhiteNoiseMiddleware',
    
    # Sesiones y autenticación
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Middleware personalizado SOLO si es necesario
    # 'api2.middleware.TimeoutMiddleware',  # ⚠️ COMENTADO - revisar antes de usar
]

# ================================
# 🎯 CONFIGURACIÓN DE URLS Y TEMPLATES
# ================================
ROOT_URLCONF = 'backend.urls'

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
# 🗄️ BASE DE DATOS - POSTGRESQL OBLIGATORIO
# ================================
# FORZAR PostgreSQL en producción/railway
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL and IS_PRODUCTION:
    print("❌ ERROR CRÍTICO: DATABASE_URL no configurada en producción")
    print("💡 Solución: En Railway, agrega PostgreSQL y copia DATABASE_URL")
    sys.exit(1)

# Configuración de base de datos
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('PGDATABASE', 'railway'),
        'USER': os.getenv('PGUSER', 'postgres'),
        'PASSWORD': os.getenv('PGPASSWORD', ''),
        'HOST': os.getenv('PGHOST', 'localhost'),
        'PORT': os.getenv('PGPORT', '5432'),
        'CONN_MAX_AGE': 600,  # Connection pooling
        'OPTIONS': {
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        }
    }
}

# Si hay DATABASE_URL, usarla (Railway)
if DATABASE_URL:
    DATABASES['default'] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=IS_PRODUCTION
    )
    print("✅ PostgreSQL configurado desde DATABASE_URL")

# ================================
# 📁 ARCHIVOS ESTÁTICOS Y MEDIA
# ================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# WhiteNoise optimizado
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files - temporal local (para uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ================================
# ☁️ CLOUDFLARE R2 CONFIGURACIÓN
# ================================
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY')
R2_ACCOUNT_ID = os.getenv('R2_ACCOUNT_ID')
R2_BUCKET_NAME = os.getenv('R2_BUCKET_NAME')

# Verificar configuración R2
R2_CONFIGURED = all([
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY, 
    R2_ACCOUNT_ID,
    R2_BUCKET_NAME
])

if R2_CONFIGURED:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    
    AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
    AWS_S3_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_REGION_NAME = 'auto'  # Mejor que 'us-east-1' para R2
    AWS_S3_ADDRESSING_STYLE = 'virtual'
    AWS_S3_CUSTOM_DOMAIN = f'{R2_BUCKET_NAME}.{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = 'private'
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600  # 1 hora para URLs presigned
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    
    # Optimización para muchos archivos pequeños (metadatos de audio)
    AWS_S3_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB en memoria antes de usar disco
    AWS_S3_USE_THREADS = True  # Uploads multi-thread
    
    print("✅ Cloudflare R2 configurado correctamente")
else:
    missing = []
    if not R2_ACCESS_KEY_ID: missing.append('R2_ACCESS_KEY_ID')
    if not R2_SECRET_ACCESS_KEY: missing.append('R2_SECRET_ACCESS_KEY')
    if not R2_ACCOUNT_ID: missing.append('R2_ACCOUNT_ID')
    if not R2_BUCKET_NAME: missing.append('R2_BUCKET_NAME')
    
    print(f"⚠️  R2 no configurado completamente. Faltan: {missing}")
    print("📁 Usando sistema de archivos local para desarrollo")

# ================================
# 🔐 VALIDACIÓN DE CONTRASEÑAS
# ================================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        'OPTIONS': {
            'max_similarity': 0.7,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ================================
# 🌍 INTERNACIONALIZACIÓN
# ================================
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ================================
# 🛡️ SEGURIDAD EN PRODUCCIÓN
# ================================
if IS_PRODUCTION:
    # SSL y HTTPS
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = []  # No excepciones
    
    # Cookies seguras
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Headers de seguridad
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    
    # HSTS
    SECURE_HSTS_SECONDS = 31536000  # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Referrer Policy
    SECURE_REFERRER_POLICY = 'same-origin'
    
    print("🛡️  Configuración de seguridad PRODUCCIÓN activada")

# ================================
# 🔥 REST FRAMEWORK - OPTIMIZADO
# ================================
REST_FRAMEWORK = {
    # Autenticación
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',  # Para admin
    ),
    
    # Permisos
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    
    # Paginación
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    
    # Throttling - CRÍTICO para escalabilidad
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'api2.throttling.UploadRateThrottle',  # Throttle específico para uploads
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',           # Visitantes
        'user': '1000/day',          # Usuarios normales
        'uploads': '5/hour',         # Uploads por usuario (CRÍTICO)
        'streaming': '1000/hour',    # Streaming (alto)
    },
    
    # Filtros
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    
    # Documentación
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    
    # Renderers (optimización)
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    
    # Parsers
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
}

# Solo en desarrollo mostrar Browsable API
if DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'].append(
        'rest_framework.renderers.BrowsableAPIRenderer'
    )

# ================================
# 🔑 JWT CONFIGURATION
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
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=60),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),
}

# ================================
# 📚 DOCUMENTACIÓN API (SPECTACULAR)
# ================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'DJI Music API',
    'DESCRIPTION': 'API para plataforma de música Dji Music - Documentación',
    'VERSION': '2.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SERVE_PUBLIC': True,
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny'],
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
    'SCHEMA_COERCE_PATH_PK_SUFFIX': True,
    'SCHEMA_PATH_PREFIX_TRIM': False,
    
    # Security
    'SECURITY': [{'Bearer': []}],
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'Token JWT en formato: Bearer <token>'
        }
    },
}

# ================================
# 📝 LOGGING COMPLETO PARA PRODUCCIÓN
# ================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '''
                %(asctime)s %(levelname)s %(name)s %(message)s
                %(pathname)s %(lineno)d %(funcName)s
                %(user_id)s %(ip)s %(method)s %(status_code)s
            ''',
        },
    },
    
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'stream': sys.stdout,
        },
        'file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/django_errors.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'api_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/api.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'json',
        },
        'upload_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/uploads.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'json',
        },
    },
    
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'api2': {
            'handlers': ['console', 'api_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'api2.upload': {
            'handlers': ['upload_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'r2_helper': {
            'handlers': ['console', 'api_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Crear directorios de logs si no existen
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# ================================
# 🎛️ CONFIGURACIONES ADICIONALES
# ================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cache (simple para empezar)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# En producción, usar Redis si está disponible
REDIS_URL = os.getenv('REDIS_URL')
if REDIS_URL and IS_PRODUCTION:
    CACHES['default'] = {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 100,
                'retry_on_timeout': True,
            },
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        }
    }
    print("✅ Redis configurado para cache")

# ================================
# ⚡ OPTIMIZACIONES DJANGO
# ================================
# Desactivar seguimiento de migraciones (mejora performance)
MIGRATION_MODULES = {}

# Número de workers para procesamiento paralelo (ajustar según Railway)
DJANGO_WORKERS = os.cpu_count() or 2

# Session engine
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

# Email (configuración básica)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
if IS_PRODUCTION:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@djidjimusic.com')

# ================================
# 🎵 CONFIGURACIÓN ESPECÍFICA PARA MÚSICA
# ================================
# Límites específicos para la app de música
MUSIC_CONFIG = {
    'MAX_AUDIO_DURATION': 3600,  # 1 hora máxima
    'ALLOWED_AUDIO_FORMATS': ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac'],
    'ALLOWED_IMAGE_FORMATS': ['jpg', 'jpeg', 'png', 'webp', 'gif'],
    'DEFAULT_QUALITY': 'high',  # high, medium, low
    'ENABLE_STREAMING': True,
    'STREAM_CHUNK_SIZE': 1024 * 1024,  # 1MB chunks para streaming
    'PREVIEW_DURATION': 30,  # 30 segundos de preview
}

print("=" * 50)
print("✅ Configuración Django lista para producción")
print(f"   Entorno: {'PRODUCCIÓN' if IS_PRODUCTION else 'DESARROLLO'}")
print(f"   Database: {DATABASES['default']['ENGINE']}")
print(f"   R2 Configurado: {'SÍ' if R2_CONFIGURED else 'NO'}")
print(f"   Workers: {DJANGO_WORKERS}")
print("=" * 50)