from rest_framework.throttling import ScopedRateThrottle

class AIThrottle(ScopedRateThrottle):
    scope="ai"

class DiscoveryThrottle(ScopedRateThrottle):
    scope="discovery"

class LoginThrottle(ScopedRateThrottle):
    scope="login"
