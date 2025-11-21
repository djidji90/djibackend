import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta
import dj_database_url

# Cargar variables de entorno
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Seguridad
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost,djibackend-production.up.railway.app,djidjimusic.com,www.djidjimusic.com,api.djidjimusic.com'
).split(',')

# ================================
# 🔐 CSRF + CORS (CORREGIDO)
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

if DEBUG:
    CORS_ALLOWED_ORIGINS.extend([
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5176",
    ])

CORS_ALLOW_CREDENTIALS = True

# ================================

AUTH_USER_MODEL = 'musica.CustomUser'

# Aplicaciones
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
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'storages',
]

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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
# Configuración de base de datos mejorada
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,  # Aumentar timeout
        }
    }
}

# Detectar si estamos en Railway o con DATABASE_URL válida
DATABASE_URL = os.getenv('DATABASE_URL')
RAILWAY_ENV = os.getenv('RAILWAY_ENVIRONMENT')  # Railway establece esta variable

if DATABASE_URL and (RAILWAY_ENV or not DEBUG):
    try:
        # Verificar que sea una URL de PostgreSQL válida
        if 'postgresql://' in DATABASE_URL or 'postgres://' in DATABASE_URL:
            DATABASES['default'] = dj_database_url.parse(
                DATABASE_URL, 
                conn_max_age=600,
                conn_health_checks=True,
            )
            print("✅ Configurado PostgreSQL para producción")
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
# ================================
# ☁️ CLOUDFLARE R2 CONFIG - VERSIÓN CORREGIDA
# ================================
# USA los nombres CORRECTOS de variables de entorno
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")  # Cambiado de R2_ACCESS_KEY
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")  
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")

if all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID, R2_BUCKET_NAME]):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

    AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID  # Cambiado de R2_ACCESS_KEY
    AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME

    AWS_S3_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_REGION_NAME = 'auto'
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_CUSTOM_DOMAIN = f'{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    
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

# Internacionalización
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
# REST FRAMEWORK
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
        'rest_framework.throttling.UserRateThrottle'
    ],
    
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day'
    }

    
}

# ================================
# JWT
# ================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': os.getenv('JWT_SECRET_KEY', SECRET_KEY),
}

# ================================
# SPECTACULAR (DOCUMENTACIÓN API)
# ================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'DJI Music API',
    'DESCRIPTION': 'API para plataforma de música Dji Music',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# ================================
# LOGGING
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
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'django_errors.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'api2': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
