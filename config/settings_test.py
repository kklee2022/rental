from .settings import *  # noqa: F401,F403

INSTALLED_APPS = [*INSTALLED_APPS, "tests_support"]  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    **STORAGES,  # noqa: F405
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
