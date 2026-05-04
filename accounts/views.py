import json
import logging
# import signing  # Django's signing module alias below
import os

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from .decorators import admin_required
from orderapp.models import Order
from customiseapp.models import CarouselSlide, Product, DesignSubmission,SendItemRequest,ProductCustomisation

logger = logging.getLogger(__name__)
User = get_user_model()
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.core import signing as django_signing
from django.contrib.auth import update_session_auth_hash
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST, require_http_methods
from .file_validators import validate_carousel_image,validate_product_image,validate_multiple_design_assets
from .decorators import login_required_json, admin_required
from .email_service import (
    send_admin_login_alert,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
    send_pending_verification_email,   
)
from .forms import (
    AdminLoginForm,
    ChangePasswordForm,
    CustomerLoginForm,
    CustomerRegisterForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    ProfileUpdateForm,
)
from django.utils.text import slugify
import uuid as _uuid
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from .models import PasswordResetToken,EmailVerificationToken


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_MB = 8

User   = get_user_model()
logger = logging.getLogger("accounts")


def _get_ip(request) -> str:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")


def _json_body(request) -> dict:
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return request.POST.dict()


def _form_errors(form) -> dict:
    return {field: errs[0] for field, errs in form.errors.items()}


def _ok(data: dict = None, redirect_url: str = None, status: int = 200) -> JsonResponse:
    payload = {"success": True}
    if data:       payload.update(data)
    if redirect_url: payload["redirect"] = redirect_url
    return JsonResponse(payload, status=status)


def _err(error: str = None, errors: dict = None, status: int = 400) -> JsonResponse:
    payload = {"success": False}
    if error:   payload["error"] = error
    if errors:  payload["errors"] = errors
    return JsonResponse(payload, status=status)


def whishlistpage(request):   return render(request, "wishlist.html")
def workshoppage(request):    return render(request, "workshop.html")
def premiumpage(request):     return render(request, "premium-service.html")
def installationpage(request):return render(request, "installation.html")
def contactpage(request):     return render(request, "contact.html")



_ACTIVATION_MAX_AGE = getattr(settings, "REGISTRATION_TOKEN_MAX_AGE", 86_400)


_ACTIVATION_SALT = "customiseme-uk-registration-v2"


@require_http_methods(["GET", "POST"])
def registerpage(request):
    if request.user.is_authenticated:
        return redirect("home-page")

    if request.method == "GET":
        return render(request, "register.html", {"form": CustomerRegisterForm()})

    # ── POST ──
    form = CustomerRegisterForm(request.POST)
    if not form.is_valid():
        return render(request, "register.html", {"form": form})

    cd    = form.cleaned_data
    email = cd["email"]  

    
    if User.objects.filter(email=email).exists():
        form.add_error("email", "An account with this email already exists.")
        return render(request, "register.html", {"form": form})

    
    payload = {
        "full_name": cd.get("full_name", ""),
        "email":     email,
        "password":  cd["password"],  
    }
    token = django_signing.dumps(payload, salt=_ACTIVATION_SALT)

   
    send_pending_verification_email(email, cd.get("full_name", ""), token)
    logger.info("Registration pending (email not yet verified): %s", email)

    return render(request, "register.html", {
        "form":             CustomerRegisterForm(),
        "register_pending": True,
        "pending_email":    email,
    })


@require_http_methods(["GET"])
def activate_account(request, token):
    try:
        payload = django_signing.loads(
            token,
            salt=_ACTIVATION_SALT,
            max_age=_ACTIVATION_MAX_AGE,
        )
    except django_signing.SignatureExpired:
        request.session["verify_error"] = (
            "This activation link has expired (valid for 24 hours). "
            "Please register again."
        )
        return redirect("register-page")
    except django_signing.BadSignature:
        request.session["verify_error"] = (
            "This activation link is invalid or has already been used."
        )
        return redirect("login-page")

    email     = payload["email"]
    full_name = payload.get("full_name", "")
    password  = payload["password"]

    # Idempotency: if the user already exists (double-click), just redirect.
    if User.objects.filter(email=email).exists():
        request.session["verify_success"] = (
            "Your account is already active. Please sign in."
        )
        return redirect("login-page")

    # ── Create the user NOW — only after email ownership is proven ──
    user = User.objects.create_user(
        email              = email,
        password           = password,
        full_name          = full_name,
        is_active          = True,   # active immediately — they proved the email
        is_email_verified  = True,   # mark verified right away
    )

    send_welcome_email(user)
    logger.info("Account activated and created: %s", email)

    request.session["verify_success"] = (
        f"Welcome! Your account has been verified. You can now sign in."
    )
    return redirect("login-page")



@require_http_methods(["GET", "POST"])
def loginpage(request):
    if request.user.is_authenticated:
        return redirect("home-page")

    context = {}
    for key in ("verify_success", "verify_error", "reset_error"):
        val = request.session.pop(key, None)
        if val:
            context[key] = val

    if request.method == "GET":
        context["form"] = CustomerLoginForm()
        return render(request, "login.html", context)

    form = CustomerLoginForm(request.POST)
    context["form"] = form

    if not form.is_valid():
        return render(request, "login.html", context)

    cd       = form.cleaned_data
    email    = cd["email"]
    password = cd["password"]

    try:
        user_obj = User.objects.get(email=email)
    except User.DoesNotExist:
        form.add_error(None, "Invalid email or password.")
        return render(request, "login.html", context)

    if getattr(user_obj, "is_locked", False):
        form.add_error(None, "Account temporarily locked. Please try again later.")
        return render(request, "login.html", context)

    if not getattr(user_obj, "is_email_verified", True):
        context["verify_warning"] = (
            "Please verify your email address before signing in. "
            "<a href='/resend-verification/'>Resend verification email</a>"
        )
        return render(request, "login.html", context)

    auth_user = authenticate(request, username=email, password=password)

    if auth_user is None:
        if hasattr(user_obj, "record_failed_login"):
            user_obj.record_failed_login()
        form.add_error(None, "Invalid email or password.")
        return render(request, "login.html", context)

    if hasattr(auth_user, "clear_failed_logins"):
        auth_user.clear_failed_logins()

    login(request, auth_user)
    logger.info("Customer login: %s", auth_user.email)

    if cd.get("remember_me"):
        request.session.set_expiry(60 * 60 * 24 * 30)
    else:
        request.session.set_expiry(0)

    if auth_user.role == auth_user.Role.ADMIN or auth_user.is_staff:
        return redirect("admin-page")

    next_url = request.GET.get("next") or request.POST.get("next", "")

    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    
    return redirect("home-page")

    # logger.info("Customer login: %s", auth_user.email)

    # if cd.get("remember_me"):
    #     request.session.set_expiry(60 * 60 * 24 * 30)
    # else:
    #     request.session.set_expiry(0)

    # next_url = request.GET.get("next") or request.POST.get("next", "")
    # if next_url and next_url.startswith("/"):
    #     return redirect(next_url)
    # return redirect("home-page")



@login_required
def profilepage(request):
    if request.method == "POST" and request.POST.get("action") == "update_profile":
        full_name = request.POST.get("full_name", "").strip()
        request.user.full_name = full_name
        request.user.save(update_fields=["full_name"])
        messages.success(request, "Profile updated successfully.")
        return redirect("me")
    return render(request, "me.html")



@require_http_methods(["GET"])
def verify_email(request, token):
    try:
        token_obj = EmailVerificationToken.objects.select_related("user").get(token=token)
    except EmailVerificationToken.DoesNotExist:
        request.session["verify_error"] = "Invalid or unrecognised verification link."
        return redirect("login-page")

    if not token_obj.is_valid:
        request.session["verify_error"] = (
            "This verification link has already been used or has expired."
        )
        return redirect("login-page")

    token_obj.used = True
    token_obj.save(update_fields=["used"])

    user = token_obj.user
    user.is_email_verified = True
    user.is_active         = True
    user.save(update_fields=["is_email_verified", "is_active"])

    send_welcome_email(user)
    logger.info("Email verified (legacy flow): %s", user.email)

    request.session["verify_success"] = "Email verified! You can now sign in."
    return redirect("login-page")



@require_POST
def resend_verification(request):
    data  = _json_body(request)
    email = data.get("email", "").lower().strip()
    try:
        user = User.objects.get(email=email, role=User.Role.CUSTOMER)
        if not user.is_email_verified:
            from .models import EmailVerificationToken
            EmailVerificationToken.objects.filter(user=user, used=False).update(used=True)
            token_obj = EmailVerificationToken.objects.create(user=user)
            send_verification_email(user, str(token_obj.token))
    except User.DoesNotExist:
        pass
    return _ok({"message": "If that email is registered and unverified, a new link has been sent."})



def admin_login_page(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin-page')
    
    error = None
    if request.method == 'POST':
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                user = User.objects.get(email=cd['email'])
            except User.DoesNotExist:
                error = 'Invalid credentials.'
            else:
                if getattr(user, 'is_locked', False):
                    error = 'Account temporarily locked.'
                elif not (user.is_staff and user.role == User.Role.ADMIN):
                    error = 'Access denied. Admin accounts only.'
                else:
                    auth_user = authenticate(request, username=cd['email'], password=cd['password'])
                    if auth_user is None:
                        error = 'Invalid credentials.'
                    else:
                        login(request, auth_user)
                        request.session.set_expiry(60*60*8 if cd.get('remember') else 0)
                        return redirect('admin-page')
        else:
            error = 'Please check the fields below.'
    
    return render(request, 'admin-login.html', {'error': error})




def _user_stats():
    total    = User.objects.filter(role=User.Role.CUSTOMER).count()
    verified = User.objects.filter(role=User.Role.CUSTOMER, is_email_verified=True).count()
    return {
        "total_customers":      total,
        "verified_customers":   verified,
        "unverified_customers": total - verified,
        "total_admins": User.objects.filter(role=User.Role.ADMIN).count(),
    }
 
 
def _products_qs(search_query=""):
    qs = Product.objects.filter(is_active=True).order_by("name")
    if search_query:
        qs = (
            qs.filter(name__icontains=search_query)
            | qs.filter(sku__icontains=search_query)
            | qs.filter(category__icontains=search_query)
        ).distinct()
    return qs
 
 
def _build_context(request, active_tab, search_query="", form_errors=None,
                   edit_slide=None, edit_product=None, viewed_order=None):
    return {
        "stats":          _user_stats(),
        "recent_orders":  Order.objects.select_related("customer").order_by("-created_at")[:20],
        "slides":         CarouselSlide.objects.filter(is_active=True).order_by("position", "id"),
        "products":       _products_qs(search_query),
        "design_submissions": DesignSubmission.objects.select_related("user")
                                                      .prefetch_related("files")
                                                      .order_by("-created_at"),
        "send_item_requests": SendItemRequest.objects.select_related("user")
                          .prefetch_related("files")
                          .order_by("-created_at"),
        "product_customisations": ProductCustomisation.objects
                          .select_related("user", "product")
                          .filter(final_price__isnull=False)
                          .order_by("-created_at"),
        "search_query":   search_query,
        "current_admin":  request.user,
        "active_tab":     active_tab,
        "form_errors":    form_errors or {},
        "edit_slide":     edit_slide,
        "edit_product":   edit_product,
        "viewed_order": viewed_order,
    }
 


 
def _handle_update_send_request(request):
 
    req_id       = request.POST.get("send_request_id")
    new_status   = request.POST.get("send_request_status", "").strip()
    admin_notes  = request.POST.get("admin_notes", "").strip()
    quoted_raw   = request.POST.get("quoted_price", "").strip()
 
    VALID_STATUSES = {
        "pending", "quoted", "confirmed", "in_work",
        "shipped", "complete", "cancelled",
    }
 
    if new_status not in VALID_STATUSES:
        messages.error(request, "Invalid status value.")
        return redirect(f"{request.path}?tab=send_requests")
 
    req = get_object_or_404(SendItemRequest, pk=req_id)
 
    req.status      = new_status
    req.admin_notes = admin_notes

    if quoted_raw:
        try:
            req.quoted_price = Decimal(quoted_raw)
        except InvalidOperation:
            messages.error(request, "Invalid quoted price — please enter a number.")
            return redirect(f"{request.path}?tab=send_requests")
    else:
        req.quoted_price = None
 
    req.save(update_fields=["status", "admin_notes", "quoted_price"])
 
    messages.success(
        request,
        f'Request #{req.pk} ({req.full_name}) updated to '
        f'"{req.get_status_display()}".'
    )
    return redirect(f"{request.path}?tab=send_requests")
 
 
@admin_required
def admin_dashboard_data(request):
    if request.method == "GET":
        active_tab      = request.GET.get("tab", "orders")
        search_query    = request.GET.get("q", "").strip()
        edit_slide_id   = request.GET.get("edit_slide")
        edit_product_id = request.GET.get("edit_product")
        order_query     = request.GET.get("q", "").strip()
 
        edit_slide   = get_object_or_404(CarouselSlide, pk=edit_slide_id)  if edit_slide_id   else None
        edit_product = get_object_or_404(Product,       pk=edit_product_id) if edit_product_id else None
 
        if edit_slide:   active_tab = "carousel"
        if edit_product: active_tab = "products"
 
        viewed_order = None
        if active_tab == "orders" and order_query:
            viewed_order = (
                Order.objects.filter(order_number=order_query).first()
                or Order.objects.filter(pk=order_query).first()
            )
 
        return render(request, "admin-page.html",
                      _build_context(request, active_tab, search_query,
                                     edit_slide=edit_slide,
                                     edit_product=edit_product,
                                     viewed_order=viewed_order))
 
    # ── POST ─────────────────────────────────────────────────
    action = request.POST.get("action", "")
 
    # ══ § 02  Carousel ═══════════════════════════════════════
    if action in ("add_slide", "edit_slide"):
        title    = request.POST.get("slide_title", "").strip()
        subtitle = request.POST.get("slide_subtitle", "").strip()
        image    = request.FILES.get("slide_image")
        slide_id = request.POST.get("slide_id")
        errors   = {}
 
        if not title:
            errors["slide_title"] = "Title is required."
 
        if image:
            try:
                validate_carousel_image(image)
            except ValidationError as e:
                errors["slide_image"] = e.message
        elif action == "add_slide":
            errors["slide_image"] = "An image is required for new slides."
 
        if errors:
            edit_slide = get_object_or_404(CarouselSlide, pk=slide_id) if slide_id else None
            return render(request, "admin-page.html",
                          _build_context(request, "carousel",
                                         form_errors=errors, edit_slide=edit_slide))
 
        if action == "edit_slide" and slide_id:
            slide          = get_object_or_404(CarouselSlide, pk=slide_id)
            slide.title    = title
            slide.subtitle = subtitle
            if image:
                if slide.image:
                    slide.image.delete(save=False)   # ← delete old file from Firebase
                slide.image = image                  # ← assign new file; .save() uploads it
            slide.save()
            messages.success(request, f'Slide "{title}" updated.')
        else:
            s = CarouselSlide(title=title, subtitle=subtitle)
            if image:
                s.image = image
            s.save()
            messages.success(request, f'Slide "{title}" added to the carousel.')
 
        return redirect(f"{request.path}?tab=carousel")
 
 
    if action == "delete_slide":
        slide = get_object_or_404(CarouselSlide, pk=request.POST.get("slide_id"))
        title = slide.title
        if slide.image:
            slide.image.delete(save=False)   # ← removes file from Firebase
        slide.delete()
        messages.success(request, f'Slide "{title}" removed.')
        return redirect(f"{request.path}?tab=carousel")
    
 
    if action == "update_order_status":
        order_id    = request.POST.get("order_id")
        new_status  = request.POST.get("order_status", "").strip()
        redirect_to = request.POST.get("redirect_order", "")
        VALID = {"processing", "shipped", "delivered", "cancelled"}
 
        if new_status not in VALID:
            messages.error(request, "Invalid status.")
            return redirect(f"{request.path}?tab=orders")
 
        order = get_object_or_404(Order, pk=order_id)
        order.status = new_status
        order.save(update_fields=["status"])
        messages.success(request, f'Order #{order.order_number} status updated to "{new_status}".')
        return redirect(f"{request.path}?tab=orders&q={redirect_to}")
 
  
    if action in ("add_product", "edit_product"):
        name        = request.POST.get("product_name", "").strip()
        sku         = request.POST.get("product_sku", "").strip()
        price_raw   = request.POST.get("product_price", "").strip()
        stock_raw   = request.POST.get("product_stock", "").strip()
        category    = request.POST.get("product_category", "").strip()
        description = request.POST.get("product_description", "").strip()
        image       = request.FILES.get("product_image")
        product_id  = request.POST.get("product_id")
        errors      = {}
 
        if not name: errors["product_name"] = "Product name is required."
        if not sku:  errors["product_sku"]  = "SKU is required."
 
        try:
            price_val = float(price_raw)
            if price_val < 0: raise ValueError
        except (ValueError, TypeError):
            errors["product_price"] = "Enter a valid price (e.g. 29.99)."
            price_val = None
 
        try:
            stock_val = int(stock_raw)
            if stock_val < 0: raise ValueError
        except (ValueError, TypeError):
            errors["product_stock"] = "Enter a valid stock count."
            stock_val = None
 
        if image:
            try:
                validate_product_image(image)
            except ValidationError as e:
                errors["product_image"] = e.message
 
        if errors:
            edit_product = get_object_or_404(Product, pk=product_id) if product_id else None
            return render(request, "admin-page.html",
                          _build_context(request, "products",
                                         form_errors=errors, edit_product=edit_product))
 
        if action == "edit_product" and product_id:
            p             = get_object_or_404(Product, pk=product_id)
            p.name        = name
            p.sku         = sku
            p.price       = price_val
            p.stock       = stock_val
            p.category    = category
            p.description = description
            if image:
                if p.image:
                    p.image.delete(save=False)   
                p.image = image                
            p.save()
            messages.success(request, f'Product "{name}" updated.')
 
        else:
            base_slug = slugify(name)
            slug      = base_slug
            if Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{str(_uuid.uuid4())[:8]}"
 
           
            try:
                p = Product(
                    name=name, slug=slug, sku=sku,
                    price=price_val, stock=stock_val,
                    category=category, description=description,
                )
                if image:
                    p.image = image      
                p.save()                 
            except Exception as exc:
                logger.error("Product save failed: %s", exc)
                messages.error(
                    request,
                    f'Product "{name}" could not be saved — image upload failed. '
                    f'Check FIREBASE_STORAGE_BUCKET and FIREBASE_PRIVATE_KEY in your .env. '
                    f'Error: {exc}'
                )
                return redirect(f"{request.path}?tab=products&add_product=1")
 
            messages.success(request, f'Product "{name}" added to inventory.')
 
        return redirect(f"{request.path}?tab=products")
 
    if action == "delete_product":
        p    = get_object_or_404(Product, pk=request.POST.get("product_id"))
        name = p.name
        if p.image:
            p.image.delete(save=False) 
        p.delete()
        messages.success(request, f'Product "{name}" deleted.')
        return redirect(f"{request.path}?tab=products")
 
   
    if action == "update_submission_status":
        sub_id = request.POST.get("submission_id")
        status = request.POST.get("submission_status", "").strip()
        note   = request.POST.get("admin_note", "").strip()
        VALID  = {"pending", "in_review", "in_progress", "completed", "rejected"}
 
        if status not in VALID:
            messages.error(request, "Invalid status value.")
            return redirect(f"{request.path}?tab=designs")
 
        sub            = get_object_or_404(DesignSubmission, pk=sub_id)
        sub.status     = status
        sub.admin_note = note
        sub.save(update_fields=["status", "admin_note"])
        messages.success(request,
            f'Submission #{str(sub.id)[:8]} updated to "{sub.get_status_display()}".')
        return redirect(f"{request.path}?tab=designs")
    
    if action == "update_send_request_status":
       return _handle_update_send_request(request)
 
    if action == "update_customisation_status":
        cust_id    = request.POST.get("customisation_id", "").strip()
        new_status = request.POST.get("customisation_status", "").strip()
        admin_note = request.POST.get("customisation_note", "").strip()
        VALID = {"pending", "in_production", "completed", "on_hold", "cancelled"}
        if new_status not in VALID:
            messages.error(request, "Invalid customisation status.")
            return redirect(f"{request.path}?tab=customisations")
        cust = get_object_or_404(ProductCustomisation, pk=cust_id)
        cust.fulfilment_status = new_status
        cust.admin_note        = admin_note
        cust.save(update_fields=["fulfilment_status", "admin_note", "updated_at"])
        messages.success(
            request,
            f"Customisation #{str(cust_id)[:8]} updated to '{new_status}'."
            + (" Note saved." if admin_note else "")
        )
        return redirect(f"{request.path}?tab=customisations")
 
    messages.error(request, "Unknown action.")
    return redirect(request.path)


@login_required_json
def me(request):
    u = request.user
    return JsonResponse({"success": True, "user": {
        "id": str(u.id), "email": u.email, "full_name": u.full_name,
        "role": u.role, "is_email_verified": u.is_email_verified,
    }})



@login_required_json
@require_POST
def profile_update(request):
    data = _json_body(request)
    form = ProfileUpdateForm(data)
    if not form.is_valid():
        return _err(errors=_form_errors(form))
    request.user.full_name = form.cleaned_data.get("full_name", request.user.full_name)
    request.user.save(update_fields=["full_name"])
    return _ok({"full_name": request.user.full_name})



# @require_POST
# def password_reset_request(request):
#     data = _json_body(request)
#     form = PasswordResetRequestForm(data)
#     if not form.is_valid():
#         return _err(errors=_form_errors(form))
#     email = form.cleaned_data["email"]
#     try:
#         user = User.objects.get(email=email, is_active=True)
#         PasswordResetToken.objects.filter(user=user, used=False).update(used=True)
#         token_obj = PasswordResetToken.objects.create(user=user)
#         send_password_reset_email(user, str(token_obj.token))
#         logger.info("Password reset requested: %s", email)
#     except User.DoesNotExist:
#         pass
#     return _ok({"message": "If that email is registered, a password reset link has been sent."})



# @require_http_methods(["GET", "POST"])
# def password_reset_confirm(request, token):
#     try:
#         token_obj = PasswordResetToken.objects.select_related("user").get(token=token)
#     except PasswordResetToken.DoesNotExist:
#         if request.method == "GET":
#             request.session["reset_error"] = "Invalid or expired password reset link."
#             return redirect("login-page")
#         return _err("Invalid or expired reset link.")

#     if not token_obj.is_valid:
#         if request.method == "GET":
#             request.session["reset_error"] = "This reset link has already been used or has expired."
#             return redirect("login-page")
#         return _err("This reset link has already been used or has expired.")

#     if request.method == "GET":
#         return render(request, "reset-password.html", {"reset_token": str(token)})

#     data = _json_body(request)
#     form = PasswordResetConfirmForm(data)
#     if not form.is_valid():
#         return _err(errors=_form_errors(form))

#     user = token_obj.user
#     user.set_password(form.cleaned_data["password"])
#     if hasattr(user, "clear_failed_logins"):
#         user.clear_failed_logins()
#     user.save()

#     token_obj.used = True
#     token_obj.save(update_fields=["used"])

#     logger.info("Password reset completed: %s", user.email)
#     return _ok({"message": "Password reset successfully. You can now sign in."}, redirect_url="/login/")




@login_required
def changepasswordpage(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        old_pw  = form.cleaned_data["old_password"]
        new_pw  = form.cleaned_data["new_password"]
        if not request.user.check_password(old_pw):
            form.add_error("old_password", "Your current password is incorrect.")
        else:
            request.user.set_password(new_pw)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password updated successfully.")
            return redirect("password-change")
    return render(request, "change-password.html", {"form": form})



@require_POST
def user_logout(request):
    logout(request)
    return redirect('home-page')


@require_POST
def admin_logout(request):
    logout(request)
    return redirect('admin-login-page')