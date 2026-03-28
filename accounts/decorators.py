import json
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import redirect


def login_required_json(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
               request.content_type == "application/json":
                return JsonResponse(
                    {"success": False, "error": "Authentication required.",
                     "redirect": "/login/"},
                    status=401,
                )
            return redirect(f"/login/?next={request.path}")
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/admin-login/")
        if not (request.user.is_staff and request.user.role == "admin"):
            return JsonResponse(
                {"success": False, "error": "Admin access required."},
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def customer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if request.user.role != "customer" or not request.user.is_email_verified:
            return redirect("/login/")
        return view_func(request, *args, **kwargs)
    return wrapper