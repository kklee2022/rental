"""Tenant-prefixed cache access with no ambient-key escape hatch."""

from django.core.cache import caches
from django.core.cache.backends.base import DEFAULT_TIMEOUT

from .context import require_current_tenant


class TenantScopedCache:
    """Wrap a Django cache backend so every key belongs to the active tenant."""

    def __init__(self, alias="default"):
        self.alias = alias

    @property
    def backend(self):
        return caches[self.alias]

    def make_key(self, key, version=None):
        tenant = require_current_tenant()
        namespaced = f"tenant:{tenant.pk}:{key}"
        return self.backend.make_key(namespaced, version=version)

    def get(self, key, default=None, version=None):
        return self.backend.get(self.make_key(key, version=version))

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self.backend.set(
            self.make_key(key, version=version), value, timeout=timeout
        )

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self.backend.add(
            self.make_key(key, version=version), value, timeout=timeout
        )

    def get_or_set(self, key, default, timeout=DEFAULT_TIMEOUT, version=None):
        return self.backend.get_or_set(
            self.make_key(key, version=version), default, timeout=timeout
        )

    def has_key(self, key, version=None):
        return self.backend.has_key(self.make_key(key, version=version))

    def touch(self, key, timeout=DEFAULT_TIMEOUT, version=None):
        return self.backend.touch(self.make_key(key, version=version), timeout)

    def incr(self, key, delta=1, version=None):
        return self.backend.incr(self.make_key(key, version=version), delta)

    def decr(self, key, delta=1, version=None):
        return self.backend.decr(self.make_key(key, version=version), delta)

    def delete(self, key, version=None):
        return self.backend.delete(self.make_key(key, version=version))


tenant_cache = TenantScopedCache()
