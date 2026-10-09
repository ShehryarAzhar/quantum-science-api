from rest_framework.throttling import SimpleRateThrottle


class PasswordResetThrottle(SimpleRateThrottle):
    # Djoser's UserViewSet cannot be given a throttle without subclassing the
    # view, so this is a default throttle class that limits one action only.
    scope = "password_reset"

    def allow_request(self, request, view):
        if getattr(view, "action", None) != "reset_password":
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        # Keyed on the IP for logged-in callers too: the route is public.
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
