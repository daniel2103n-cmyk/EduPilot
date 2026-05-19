"""
EduPilot — Django Settings.

Fase 1: Configuración base local con SQLite.
Fase 2: Migrar a PostgreSQL + Railway deployment.
"""

from pathlib import Path
from decouple import config, Undefined

# ─── Rutas base ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Seguridad ────────────────────────────────────────────────────────────────
# Lee SECRET_KEY del .env; si no existe usa el insecure key para desarrollo
try:
    SECRET_KEY = config('SECRET_KEY')
except Exception:
    SECRET_KEY = 'django-insecure-2a(+%i7pd#+u_(svt)rh-s!xffs*c1uf-=1sk&3w7*b+5l9x%)'

DEBUG = config('DEBUG', cast=bool, default=True)

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.railway.app']

# ─── IA — OpenRouter ──────────────────────────────────────────────────────────
# Fase 2: usar en ai_service.py
try:
    OPENROUTER_API_KEY = config('OPENROUTER_API_KEY')
except Exception:
    OPENROUTER_API_KEY = ''

# ─── Apps ─────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # EduPilot apps
    'apps.authentication',
    'apps.students',
    'apps.courses',
    'apps.academic',
    'apps.routes',
    'apps.ai',
]

# ─── Middleware ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

# ─── Templates ────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],   # templates/ en raíz del proyecto
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ─── Base de Datos ────────────────────────────────────────────────────────────
# Fase 1: SQLite | Fase 2: PostgreSQL en Railway
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ─── Validación de contraseñas ────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Internacionalización ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# ─── Archivos estáticos ───────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── Modelo de usuario personalizado ─────────────────────────────────────────
AUTH_USER_MODEL = 'authentication.User'

# ─── Autenticación y redirección ─────────────────────────────────────────────
LOGIN_URL          = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ─── Clave primaria por defecto ───────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'