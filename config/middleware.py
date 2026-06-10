class BrowserSecurityHeadersMiddleware:
    """Add browser protections that are safe for the current hosted assets."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://checkout.razorpay.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' https://*.razorpay.com; "
            "frame-src https://*.razorpay.com",
        )
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(), payment=(self)',
        )
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin-allow-popups')
        response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
        return response
