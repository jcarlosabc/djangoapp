
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-demo') # Use os.environ.get for SECRET_KEY
DEBUG = os.environ.get('DEBUG', 'True') == 'True' # Use os.environ.get for DEBUG
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',') # Use os.environ.get for ALLOWED_HOSTS

# New variable for data protection clause
DATA_PROTECTION_CLAUSE_TEXT = os.environ.get('DATA_PROTECTION_CLAUSE_TEXT', 'Al continuar, usted acepta la recopilación y el uso de sus datos personales de acuerdo con nuestra política de privacidad. Sus datos serán utilizados únicamente para los fines de esta encuesta y no serán compartidos con terceros sin su consentimiento explícito.')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'surveys',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'encuestasite.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]

WSGI_APPLICATION = 'encuestasite.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'surveys:list'
LOGOUT_REDIRECT_URL = 'login'
