"""
Django settings for testsite project.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.6/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os, re, sys
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

def load_config(confpath):
    '''
    Given a path to a file, parse its lines in ini-like format, and then
    set them in the current namespace.
    '''
    # todo: consider using something like ConfigObj for this:
    # http://www.voidspace.org.uk/python/configobj.html
    if os.path.isfile(confpath):
        sys.stderr.write('config loaded from %s\n' % confpath)
        with open(confpath) as conffile:
            line = conffile.readline()
            while line != '':
                if not line.startswith('#'):
                    look = re.match(r'(\w+)\s*=\s*(.*)', line)
                    if look:
                        try:
                            # Once Django 1.5 introduced ALLOWED_HOSTS (a tuple
                            # definitely in the site.conf set), we had no choice
                            # other than using eval. The {} are here to restrict
                            # the globals and locals context eval has access to.
                            # pylint: disable=eval-used
                            setattr(sys.modules[__name__],
                             look.group(1).upper(), eval(look.group(2), {}, {}))
                        except StandardError:
                            raise
                line = conffile.readline()
    else:
        sys.stderr.write('warning: config file %s does not exist.\n' % confpath)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.6/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '9j24plovjvx%-_bvfgd*))umqd_olg!=4#a4i9_rf*)fl9b4b_'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = []

# Database
# https://docs.djangoproject.com/en/1.6/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'testsite.urls'

WSGI_APPLICATION = 'testsite.wsgi.application'

# Internationalization
# https://docs.djangoproject.com/en/1.6/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.6/howto/static-files/

STATIC_URL = '/static/'

# Default email address to use for various automated correspondence from
# the site managers (also django-registration settings)
DEFAULT_FROM_EMAIL = "admin@example.com"

# Mail server and accounts for notifications.
# Host, port, TLS for sending email.
EMAIL_HOST = ""
EMAIL_PORT = 587
EMAIL_USE_TLS = False

# Optional SMTP authentication information for EMAIL_HOST.
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""

# Continuous build settings
# -------------------------

FIXTURE_DIRS = (
    BASE_DIR + '/testsite/fixtures',
)

# Application definition

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
#    'django.contrib.sites',  # XXX necessary?
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'survey',
    'testsite'
)

load_config(os.path.join(BASE_DIR, 'credentials'))


