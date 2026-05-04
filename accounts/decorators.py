from functools import wraps
from django.shortcuts import redirect


def role_required(allowed_roles=None):
    """
    Decorator that restricts access to views based on user role.
    Must be applied AFTER @login_required so request.user is always authenticated.

    Usage:
        @login_required
        @role_required(['USER'])
        def my_view(request): ...
    """
    if allowed_roles is None:
        allowed_roles = []

    def decorator(view_func):
        @wraps(view_func)  # Preserves __name__, __module__, etc. — required for @login_required compat
        def wrapper(request, *args, **kwargs):
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            # Role mismatch — send back to auth page
            return redirect('auth_page')

        return wrapper
    return decorator