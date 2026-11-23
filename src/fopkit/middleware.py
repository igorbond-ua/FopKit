"""
Security headers middleware.
Adds Content-Security-Policy and other security headers to every response.
"""


class SecurityHeadersMiddleware:
    """Add security-related HTTP headers to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content-Security-Policy:
        # - Scripts, styles, fonts, images: same origin only.
        # - No inline scripts (nonce-less), no eval.
        # - IndexedDB / fetch: same origin.
        # - Disallow framing (also handled by XFrameOptions, belt + braces).
        csp_parts = [
            "default-src 'self'",
            # Allow inline styles for the small style="…" attributes in templates
            "style-src 'self' 'unsafe-inline'",
            "script-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "base-uri 'self'",
            "object-src 'none'",
        ]
        response["Content-Security-Policy"] = "; ".join(csp_parts)
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "same-origin"
        response["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

        return response
