import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta
import dj_database_url

# ================================
# 🚀 CONFIGURACIÓN BASE
# ================================
# Cargar variables de entorno
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Seguridad
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost,djibackend-production.up.railway.app,djidjimusic.com,www.djidjimusic.com,api.djidjimusic.com'
    '127.0.0.1,localhost,djibackend-production.up.railway.app,djidjimusic.com,www.djidjimusic.com,api.djidjimusic.com,testserver'
).split(',')

# ================================
# 🔗 URLs BASE
# ================================
SITE_URL = os.getenv('SITE_URL', 'https://djidjimusic.com')
API_URL = os.getenv('API_URL', 'https://api.djidjimusic.com')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://djidjimusic.com')

# ================================
# 📦 TAMAÑOS DE ARCHIVO
# ================================
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# ================================
# 📊 LÍMITES Y CUOTAS DE USUARIO
# ================================
# Límites por defecto (Free tier)
DEFAULT_UPLOAD_LIMITS = {
    'max_daily_uploads': 50,  # 50 uploads por día
    'max_daily_size': 500 * 1024 * 1024,  # 500MB por día
    'max_file_size': 100 * 1024 * 1024,  # 100MB por archivo
    'max_total_storage': 5 * 1024 * 1024 * 1024,  # 5GB total
}

# Límites para planes premium (ejemplo)
PREMIUM_UPLOAD_LIMITS = {
    'max_daily_uploads': 200,
    'max_daily_size': 5 * 1024 * 1024 * 1024,  # 5GB por día
    'max_file_size': 500 * 1024 * 1024,  # 500MB por archivo
    'max_total_storage': 50 * 1024 * 1024 * 1024,  # 50GB total
}

# Para admins
ADMIN_UPLOAD_LIMITS = {
    'max_daily_uploads': 1000,
    'max_daily_size': 50 * 1024 * 1024 * 1024,  # 50GB por día
    'max_file_size': 2 * 1024 * 1024 * 1024,  # 2GB por archivo
    'max_total_storage': 500 * 1024 * 1024 * 1024,  # 500GB total
}

# Límites del sistema
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500MB límite absoluto
MAX_AUDIO_SIZE = 300 * 1024 * 1024  # 300MB para audio
MAX_IMAGE_SIZE = 50 * 1024 * 1024  # 50MB para imágenes

# ================================
# 🔐 CSRF + CORS CONFIGURACIÓN
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
    "https://djibackend-production.up.railway.app",
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.djidjimusic\.com$",
    r"^https://djibackend-production\.up\.railway\.app$",
]

# Permitir localhost mientras desarrollas
if DEBUG or os.getenv("RAILWAY_ENVIRONMENT"):
    localhost_ports = ["8000", "5173", "5174", "5176"]
    for port in localhost_ports:
        CORS_ALLOWED_ORIGINS.append(f"http://localhost:{port}")

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]
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

# ================================
# 👤 USUARIO PERSONALIZADO
# ================================
AUTH_USER_MODEL = 'musica.CustomUser'

# ================================
# 📦 APLICACIONES INSTALADAS
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
    "django_celery_results",  # ¡IMPORTANTE para resultado en DB!
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'storages',
]

# ================================
# ⚙️ MIDDLEWARE
# ================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
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
# 🎨 TEMPLATES
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
# 📌 BASE DE DATOS — LOCAL + RAILWAY
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

DATABASE_URL = os.getenv('DATABASE_URL')
RAILWAY_ENV = os.getenv('RAILWAY_ENVIRONMENT')

if DATABASE_URL and (RAILWAY_ENV or not DEBUG):
    try:
        if 'postgresql://' in DATABASE_URL or 'postgres://' in DATABASE_URL:
            DATABASES['default'] = dj_database_url.parse(
                DATABASE_URL, 
                conn_max_age=600,
                conn_health_checks=True,
                ssl_require=True,
            )
            print("✅ PostgreSQL configurado para producción")
        else:
            print("⚠️ DATABASE_URL no es de PostgreSQL. Usando SQLite.")
    except Exception as e:
        print(f"❌ Error configurando PostgreSQL: {e}")
        print("🔄 Usando SQLite como fallback")

# ================================
# 📁 ARCHIVOS ESTÁTICOS
# ================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ================================
# ☁️ CLOUDFLARE R2 CONFIG
# ================================
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")  
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")

# Configuración para uploads directos
R2_UPLOADS_PREFIX = 'uploads/'
R2_PRESIGNED_EXPIRY = 3600  # 1 hora
R2_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB máximo por archivo
R2_DOWNLOAD_URL_EXPIRY = 300  # 5 minutos para URLs de descarga

if all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID, R2_BUCKET_NAME]):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

    AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
    AWS_S3_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_REGION_NAME = 'auto'
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_CUSTOM_DOMAIN = f'{R2_BUCKET_NAME}.{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = 'private'
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600  # 1 hora para URLs firmadas
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_USE_SSL = True
    AWS_S3_VERIFY = True

    print("✅ R2 Configurado correctamente")
else:
    missing = []
    if not R2_ACCESS_KEY_ID: missing.append('R2_ACCESS_KEY_ID')
    if not R2_SECRET_ACCESS_KEY: missing.append('R2_SECRET_ACCESS_KEY') 
    if not R2_ACCOUNT_ID: missing.append('R2_ACCOUNT_ID')
    if not R2_BUCKET_NAME: missing.append('R2_BUCKET_NAME')
    print(f"⚠️  R2 no configurado. Variables faltantes: {missing}")

# ================================
# 🔐 VALIDACIÓN DE CONTRASEÑAS
# ================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
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
# 🚀 REST FRAMEWORK
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
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '10000/day',
        'uploads': '50/hour',  # Throttle específico para uploads
    },
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# ================================
# 🔐 JWT CONFIGURACIÓN
# ================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': os.getenv('JWT_SECRET_KEY', SECRET_KEY),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ==============================================
# 📊 LÍMITES Y CUOTAS DE USUARIO
# ==============================================

# Límites por defecto (Free tier)
DEFAULT_UPLOAD_LIMITS = {
    'max_daily_uploads': 50,  # 50 uploads por día
    'max_daily_size': 500 * 1024 * 1024,  # 500MB por día
    'max_file_size': 100 * 1024 * 1024,  # 100MB por archivo
    'max_total_storage': 5 * 1024 * 1024 * 1024,  # 5GB total
}

# Límites para planes premium (ejemplo)
PREMIUM_UPLOAD_LIMITS = {
    'max_daily_uploads': 200,
    'max_daily_size': 5 * 1024 * 1024 * 1024,  # 5GB por día
    'max_file_size': 500 * 1024 * 1024,  # 500MB por archivo
    'max_total_storage': 50 * 1024 * 1024 * 1024,  # 50GB total
}

# Para admins
ADMIN_UPLOAD_LIMITS = {
    'max_daily_uploads': 1000,
    'max_daily_size': 50 * 1024 * 1024 * 1024,  # 50GB por día
    'max_file_size': 2 * 1024 * 1024 * 1024,  # 2GB por archivo
    'max_total_storage': 500 * 1024 * 1024 * 1024,  # 500GB total
}

# ================================
# 📚 SPECTACULAR (DOCUMENTACIÓN API)
# ================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'DJI Music API',
    'DESCRIPTION': 'API para plataforma de música Dji Music',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ================================
# 📝 LOGGING BASE
# ================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {asctime} {name}: {message}",
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
        "celery_console": {
            "class": "logging.StreamHandler",
            "formatter": "celery",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "api2": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["celery_console"],
            "level": "INFO",
            "propagate": True,
        },
        "celery.task": {
            "handlers": ["celery_console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

if DEBUG:
    LOGGING["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "filename": BASE_DIR / "logs/django.log",
        "formatter": "simple",
    }
    LOGGING["root"]["handlers"].append("file")

# ================================
# 🎯 CONFIGURACIONES FINALES
# ================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cache configuration
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv(
            "REDIS_URL",
            "redis://127.0.0.1:6379/1"
        ),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

# Session settings
SESSION_COOKIE_AGE = 1209600  # 2 semanas
SESSION_SAVE_EVERY_REQUEST = True

# ================================
# 🔄 CELERY CONFIGURACIÓN PRODUCCIÓN
# ================================

# Broker y Backend
# ================================
# 🔄 CELERY CONFIGURACIÓN PRODUCCIÓN - FIXED
# ================================

import os

# 1. Obtener REDIS_URL explícitamente
REDIS_URL = os.getenv('REDIS_URL')

# 2. DEBUG check
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# 3. Configuración Celery EXPLÍCITA
if DEBUG:
    # Desarrollo local
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
    print("🔧 Celery configurado para desarrollo local")
else:
    # PRODUCCIÓN (Railway)
    # Opción A: URL directa desde variable
    if REDIS_URL:
        CELERY_BROKER_URL = REDIS_URL if REDIS_URL.endswith('/0') else f"{REDIS_URL}/0"
        CELERY_RESULT_BACKEND = 'django-db'  # Más confiable en producción
        
        # Log seguro
        safe_url = CELERY_BROKER_URL
        if '@' in CELERY_BROKER_URL:
            parts = CELERY_BROKER_URL.split('@')
            safe_url = f"redis://***@{parts[1]}"
        print(f"✅ Celery configurado con Redis: {safe_url}")
    
    # Opción B: Fallback si no hay REDIS_URL
    else:
        CELERY_BROKER_URL = 'redis://localhost:6379/0'
        CELERY_RESULT_BACKEND = 'django-db'
        print("⚠️  ADVERTENCIA: REDIS_URL no configurada, usando localhost")

# 4. FORZAR Redis como broker (importante!)
CELERY_BROKER_TRANSPORT = 'redis'
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': 3600,
    'fanout_prefix': True,
    'fanout_patterns': True,
}

# 5. Cache también necesita Redis
if not DEBUG and REDIS_URL:
    CACHES["default"]["LOCATION"] = f"{REDIS_URL}/1"