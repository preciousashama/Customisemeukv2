"""
Django settings for customiseproject project.
"""
import os
from pathlib import Path
from django.contrib.messages import constants as message_constants
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv()



SECRET_KEY=os.getenv("SECRET_KEY")
DEBUG=os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = ["customisemeuk.onrender.com"]

INSTALLED_APPS = [
    "accounts",
    "customiseapp.apps.CustomiseappConfig", 
    "orderapp",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    'whitenoise.middleware.WhiteNoiseMiddleware',
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "customiseproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "customiseapp.context_processors.header_counts",
            ],
        },
    },
]

WSGI_APPLICATION = "customiseproject.wsgi.application"



AUTH_USER_MODEL     = "accounts.CustomUser"
LOGIN_URL           = "account/login/"
LOGIN_REDIRECT_URL  = "/"
LOGOUT_REDIRECT_URL = "account/login/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]



# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }


if os.getenv('DJANGO_ENV') == 'production':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
}



DEFAULT_FILE_STORAGE="customiseapp.firebase_storage.FirebaseStorage"
FIREBASE_STORAGE_BUCKET=os.getenv("FIREBASE_STORAGE_BUCKET", "")

# File-path fallback — only used when FIREBASE_PRIVATE_KEY is NOT set
_fb_json = BASE_DIR / "firebase-credentials.json"
FIREBASE_CREDENTIALS_JSON = _fb_json if _fb_json.exists() else None



STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SITE_URL               = os.getenv("SITE_URL", "http://localhost:8000")



BREVO_API_KEY      = os.getenv("BREVO_API_KEY", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@customisemeuk.com")
DEFAULT_FROM_NAME  = os.getenv("DEFAULT_FROM_NAME", "CustomiseMe UK")

EMAIL_VERIFICATION_TIMEOUT_HOURS = int(os.getenv("EMAIL_VERIFICATION_TIMEOUT_HOURS") or 24)
PASSWORD_RESET_TIMEOUT_HOURS     = int(os.getenv("PASSWORD_RESET_TIMEOUT_HOURS") or 2)



SESSION_COOKIE_HTTPONLY  = True
SESSION_COOKIE_SAMESITE  = "Lax"
SESSION_ENGINE           = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE       = 60 * 60 * 24 * 30   # 30 days
SESSION_COOKIE_AGE_SHORT = 60 * 60 * 24         # 1 day (no "remember me")

# Must be False so JS can read the CSRF token for fetch() calls
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"



LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_I18N      = True
USE_TZ        = True

REGISTRATION_TOKEN_MAX_AGE = 86_400   # 24 h in seconds


STATIC_URL       = "/static/"
STATIC_ROOT      = BASE_DIR / "staticfiles"
# STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024   # 30 MB overall
FILE_UPLOAD_MAX_MEMORY_SIZE = 26 * 1024 * 1024   # 26 MB per file



MESSAGE_TAGS = {
    message_constants.DEBUG:   "debug",
    message_constants.INFO:    "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR:   "error",
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
