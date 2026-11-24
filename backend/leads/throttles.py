from rest_framework.throttling import SimpleRateThrottle


class EndpointThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        identity = request.user.pk if request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": identity}


class AIThrottle(EndpointThrottle):
    scope = "ai"


class DiscoveryThrottle(EndpointThrottle):
    scope = "discovery"


class LoginThrottle(EndpointThrottle):
    scope = "login"
