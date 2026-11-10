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

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '.railway.app', '.onrender.com', '.render.com', '*']

# ─── IA — Configuración (Ollama / OpenRouter) ───────────────────────────────
AI_PROVIDER = config('AI_PROVIDER', default='ollama').strip().lower()
OLLAMA_BASE_URL = config('OLLAMA_BASE_URL', default='http://localhost:11434').rstrip('/')
OLLAMA_MODEL = config('OLLAMA_MODEL', default='qwen3.5:4b').strip()

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
]

# Incluir WhiteNoise si está instalado en el entorno
try:
    import whitenoise  # noqa: F401
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
except ImportError:
    pass

MIDDLEWARE.extend([
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
])

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
# Desarrollo local por defecto: SQLite | Producción / Despliegue: PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Configuración dinámica para producción (Render/Railway) o DATABASE_URL personalizada
# Con USE_LOCAL_DB=True en .env se asegura el uso de SQLite en local pase lo que pase con DATABASE_URL
USE_LOCAL_DB = config('USE_LOCAL_DB', cast=bool, default=False)
DATABASE_URL = None if USE_LOCAL_DB else config('DATABASE_URL', default=None)
if DATABASE_URL:
    try:
        import dj_database_url
        is_local_db = ('localhost' in DATABASE_URL) or ('127.0.0.1' in DATABASE_URL) or ('sqlite' in DATABASE_URL)
        DATABASES['default'] = dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=config('DB_SSL_REQUIRE', cast=bool, default=not is_local_db)
        )
    except ImportError:
        pass

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

# Configuración de almacenamiento: en producción usa WhiteNoise si está instalado y no estamos en DEBUG.
# En desarrollo (DEBUG=True) se usa el storage nativo de Django para evitar problemas con hashes y archivos faltantes.
has_whitenoise = False
try:
    import whitenoise  # noqa: F401
    has_whitenoise = True
except ImportError:
    has_whitenoise = False

if has_whitenoise and not DEBUG:
    staticfiles_storage = "whitenoise.storage.CompressedManifestStaticFilesStorage"
else:
    staticfiles_storage = "django.contrib.staticfiles.storage.StaticFilesStorage"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": staticfiles_storage,
    },
}

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