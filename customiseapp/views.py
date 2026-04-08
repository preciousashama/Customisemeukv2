import json
import logging
import stripe

from decimal import Decimal, InvalidOperation
from datetime import date
import re as _re
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .file_validators import validate_multiple_design_assets
from .models import (
    CarouselSlide, Product, Wishlist,
   DesignSubmission,DesignSubmissionFile,
   SendItemFile,SendItemRequest,
   ProductCustomisation,
    SERVICE_TYPES, BUDGET_RANGES,
)
from orderapp.models import OrderItem,Order
from accounts.email_service import send_order_confirmation_email
logger        = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY



def _get_cart(request):
    cart = request.session.get("cart", [])
    enriched = []
    for item in cart:
        try:
            price = Decimal(str(item.get("price", "0")))
        except InvalidOperation:
            price = Decimal("0")
        qty = max(1, int(item.get("quantity", 1)))
        enriched.append({
            **item,
            "price_decimal": price,
            "quantity":      qty,
            "line_total":    price * qty,
        })
    return enriched


def _cart_totals(cart):
    subtotal = sum(i["line_total"] for i in cart)
    shipping  = Decimal("0.00") if subtotal >= 100 else Decimal("6.99")
    total     = subtotal + shipping
    return {"subtotal": subtotal, "shipping": shipping, "total": total}


def header_counts(request):
    wish_count = 0
    cart_count = 0
    if request.user.is_authenticated:
        wish_count = Wishlist.objects.filter(user=request.user).count()
    cart = request.session.get("cart", [])
    cart_count = sum(i.get("quantity", 1) for i in cart)
    return {
        "wish_count": wish_count,
        "cart_count": cart_count,
    }


def _save_cart(request, cart):
    # Strip Decimal fields before storing in session (session uses JSON)
    request.session["cart"] = [
        {k: str(v) if isinstance(v, Decimal) else v
         for k, v in item.items()
         if k not in ("price_decimal", "line_total")}
        for item in cart
    ]
    request.session.modified = True



def page_not_found_view(request, exception=None):
    return render(request, "404.html", status=404)


def landing(request):

    return render(request,"landing.html")



def homepage(request):
    slides   = CarouselSlide.objects.filter(is_active=True).order_by("position", "id")
    featured = Product.objects.filter(is_active=True).order_by("?")[:4]
    # Pass wishlist product IDs so heart buttons render filled for logged-in users
    wished_ids = set()
    if request.user.is_authenticated:
        wished_ids = set(
            str(pk) for pk in
            Wishlist.objects.filter(user=request.user).values_list("product_id", flat=True)
        )
    return render(request, "index.html", {
        "slides":     slides,
        "featured":   featured,
        "wished_ids": wished_ids,
        
    })


def aboutpage(request):         return render(request, "about.html")
def privacypage(request):       return render(request, "privacy.html")
def workshoppage(request):      return render(request, "workshop.html")
def subscriptionpage(request):  return render(request, "subscription.html")
# def senditempage(request):      return render(request, "senditems.html")
def faqpage(request):           return render(request, "faq.html")
def conditionpage(request):     return render(request, "conditions.html")
# def contactpage(request):       return render(request, "contact.html")
# def giftpage(request):          return render(request, "gift.html")
def designstudiopage(request):  return render(request, "design-studio.html")



def shoppage(request):
    qs   = Product.objects.filter(is_active=True)
    cat  = request.GET.get("cat", "").strip()
    q    = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "")

    if cat:
        qs = qs.filter(category__iexact=cat)
    if q:
        qs = (qs.filter(name__icontains=q) | qs.filter(description__icontains=q)).distinct()
    qs = qs.order_by("price" if sort == "price_asc" else
                     "-price" if sort == "price_desc" else "name")

    wished_ids = set()
    if request.user.is_authenticated:
        wished_ids = set(
            str(pk) for pk in
            Wishlist.objects.filter(user=request.user).values_list("product_id", flat=True)
        )

    return render(request, "shop.html", {
        "products":    qs,
        "active_cat":  cat,
        "search_query": q,
        "sort":        sort,
        "categories":  Product.objects.filter(is_active=True)
                               .values_list("category", flat=True)
                               .distinct().order_by("category"),
        "wished_ids":  wished_ids,
    })




def productpage(request, slug=None):
    if slug:
        product = get_object_or_404(Product, slug=slug, is_active=True)
    else:
        product = Product.objects.filter(is_active=True).first()
 
    related = (
        Product.objects.filter(is_active=True, category=product.category)
        .exclude(pk=product.pk)[:4]
        if product else []
    )
 
    is_wished   = False
    wish_count  = 0
    placements = [
        "Front Left", "Front Centre", "Front Right", "Front Full",
        "Back Left", "Back Centre", "Back Right", "Back Full"
    ]
    if request.user.is_authenticated and product:
        is_wished  = Wishlist.objects.filter(user=request.user, product=product).exists()
        wish_count = Wishlist.objects.filter(user=request.user).count()
 
    cart       = request.session.get("cart", [])
    cart_count = sum(int(item.get("quantity", 1)) for item in cart)
 
    return render(request, "product.html", {
        "product":    product,
        "related":    related,
        "is_wished":  is_wished,
        "wish_count": wish_count,
        "cart_count": cart_count,
        "placements":placements,
    })



@login_required
def wishlistpage(request):
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if request.method == "POST":
        action     = request.POST.get("action", "")
        product_id = request.POST.get("product_id", "")

        if action == "toggle":
            product = get_object_or_404(Product, pk=product_id)
            obj, created = Wishlist.objects.get_or_create(
                user=request.user, product=product
            )
            if not created:
                obj.delete()
                state = "removed"
            else:
                state = "added"
            count = Wishlist.objects.filter(user=request.user).count()
            if is_ajax:
                return JsonResponse({"state": state, "count": count})
            return redirect("wishlist-page")

    
        if action == "move_to_cart":
            item = get_object_or_404(Wishlist, user=request.user, product_id=product_id)
            product = item.product
            cart = _get_cart(request)
            existing = next((i for i in cart if i.get("product_id") == product_id), None)
            if existing:
                existing["quantity"] = existing.get("quantity", 1) + 1
            else:
                cart.append({
                    "product_id": str(product.id),
                    "name":       product.name,
                    "price":      str(product.price),
                    "quantity":   1,
                    "image_url":  product.image.url if product.image else "",
                    "variant":    "",
                })
            _save_cart(request, cart)
            item.delete()
            totals = _cart_totals(_get_cart(request))
            if is_ajax:
                return JsonResponse({
                    "ok": True,
                    "cart_count": sum(i.get("quantity", 1) for i in request.session.get("cart", [])),
                    "cart_total": str(totals["total"]),
                })
            messages.success(request, f'"{product.name}" moved to your cart.')
            return redirect("wishlist-page")

        if action == "add_all_to_cart":
            items = Wishlist.objects.filter(user=request.user).select_related("product")
            cart  = _get_cart(request)
            added = 0
            for wl in items:
                p  = wl.product
                if p.is_out_of_stock:
                    continue
                existing = next((i for i in cart if i.get("product_id") == str(p.id)), None)
                if existing:
                    existing["quantity"] = existing.get("quantity", 1) + 1
                else:
                    cart.append({
                        "product_id": str(p.id),
                        "name":       p.name,
                        "price":      str(p.price),
                        "quantity":   1,
                        "image_url":  p.image.url if p.image else "",
                        "variant":    "",
                    })
                added += 1
            _save_cart(request, cart)
            if is_ajax:
                return JsonResponse({"ok": True, "added": added})
            messages.success(request, f"{added} item(s) added to your cart.")
            return redirect("cart-page")

       
        if action == "remove":
            Wishlist.objects.filter(user=request.user, product_id=product_id).delete()
            count = Wishlist.objects.filter(user=request.user).count()
            if is_ajax:
                return JsonResponse({"ok": True, "count": count})
            return redirect("wishlist-page")

  
    wish_items = (
        Wishlist.objects
        .filter(user=request.user)
        .select_related("product")
        .order_by("-added_at")
    )
    recommended = Product.objects.filter(is_active=True).order_by("?")[:4]
    return render(request, "wishlist.html", {
        "wish_items":   wish_items,
        "recommended":  recommended,
        "total_count":  wish_items.count(),
        # "total_count": wish_items.count(),
      
    })



def cartpage(request):
    if request.method == "POST":
        action     = request.POST.get("action", "")
        product_id = request.POST.get("product_id", "")
        cart       = _get_cart(request)
        is_ajax    = request.headers.get("x-requested-with") == "XMLHttpRequest"

        if action == "add_item":
            colour        = request.POST.get("colour",       "").strip()
            size          = request.POST.get("size",         "").strip()
            artwork_size  = request.POST.get("artwork_size", "").strip()
            placement     = request.POST.get("placement",    "").strip()
            printing_side = request.POST.get("printing_side","").strip()
            variant       = request.POST.get("variant",      "").strip()
            # Use price_override (JS-calculated with add-ons) if present
            raw_price     = request.POST.get("price_override") or request.POST.get("price", "0")

            existing = next((i for i in cart if
                             i.get("product_id") == product_id and
                             i.get("variant") == variant), None)
            if existing:
                existing["quantity"] = existing.get("quantity", 1) + 1
            else:
                cart.append({
                    "product_id":    product_id,
                    "name":          request.POST.get("name", ""),
                    "price":         raw_price,
                    "quantity":      1,
                    "image_url":     request.POST.get("image_url", ""),
                    "variant":       variant,
                    "colour":        colour,
                    "size":          size,
                    "artwork_size":  artwork_size,
                    "placement":     placement,
                    "printing_side": printing_side,
                })

            artwork_file = request.FILES.get("artwork_file")
            try:
                from .models import ProductCustomisation, Product as _Product
                from decimal import Decimal as _D, InvalidOperation as _IE
                try:
                    fp = _D(str(raw_price))
                except _IE:
                    fp = None
                pc = ProductCustomisation(
                    user            = request.user if request.user.is_authenticated else None,
                    session_key     = request.session.session_key or "",
                    colour          = colour,
                    size            = size,
                    artwork_size    = artwork_size,
                    placement       = placement,
                    printing_side   = printing_side,
                    variant_summary = variant,
                    final_price     = fp,
                    artwork_filename= artwork_file.name if artwork_file else "",
                )
                try:
                    pc.product = _Product.objects.get(pk=product_id)
                except (_Product.DoesNotExist, Exception):
                    pass
                if artwork_file:
                    pc.artwork_file = artwork_file
                pc.save()
            except Exception as _e:
                logger.warning("Could not save ProductCustomisation: %s", _e)

        elif action == "update_qty":
            qty = max(0, int(request.POST.get("quantity", 1)))
            if qty == 0:
                cart = [i for i in cart if i.get("product_id") != product_id]
            else:
                for item in cart:
                    if item.get("product_id") == product_id:
                        item["quantity"] = qty
                        break

        elif action == "remove_item":
            cart = [i for i in cart if i.get("product_id") != product_id]

        elif action == "clear_cart":
            cart = []

        _save_cart(request, cart)
        if is_ajax:
            enriched = _get_cart(request)
            totals   = _cart_totals(enriched)
            return JsonResponse({
                "cart_count": sum(i["quantity"] for i in enriched),
                "subtotal":   str(totals["subtotal"]),
                "shipping":   str(totals["shipping"]),
                "total":      str(totals["total"]),
            })
        return redirect("cart-page")

    # GET
    enriched    = _get_cart(request)
    totals      = _cart_totals(enriched)
    recommended = Product.objects.filter(is_active=True).order_by("?")[:4]
    return render(request, "cart.html", {
        "cart":           enriched,
        "totals":         totals,
        "recommended":    recommended,
        "stripe_pub_key": settings.STRIPE_PUBLISHABLE_KEY,
    })



@require_POST
def create_checkout_session(request):
    from orderapp.models import Order   # avoid circular import
 
    from customiseapp.views import _get_cart, _cart_totals
 
    cart    = _get_cart(request)
    totals  = _cart_totals(cart)
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
 
    if not cart:
        err = "Your cart is empty."
        return (JsonResponse({"error": err}, status=400) if is_ajax
                else (messages.error(request, err) or redirect("cart-page")))
 
    site_url   = settings.SITE_URL.rstrip("/")
    line_items = []
 
    for item in cart:
        pid = item.get("product_id", "")
        stripe_price_id = None
 
        if pid:
            try:
                product = Product.objects.only(
                    "stripe_price_id", "stripe_product_id",
                    "price", "name", "image", "sku",
                ).get(pk=pid)
                stripe_price_id = product.stripe_price_id or None
            except Product.DoesNotExist:
                product = None
        else:
            product = None
 
        if stripe_price_id:
            line_items.append({
                "price": stripe_price_id,
                "quantity": item["quantity"],
                "metadata": {
                    "product_name": product.name if product else item.get("name", "Item"),
                    "product_sku": product.sku if product else "",
                }
            })
        else:
            unit_amount = int(item["price_decimal"] * 100)
            image_url   = item.get("image_url", "")
            line_items.append({
                "price_data": {
                    "currency":     "gbp",
                    "unit_amount":  unit_amount,
                    "product_data": {
                        "name":        item["name"],
                        "description": item.get("variant") or None,
                        "images":      [image_url] if image_url else [],
                    },
                },
                "quantity": item["quantity"],
            })
 
  
    if totals["shipping"] > 0:
        line_items.append({
            "price_data": {
                "currency":     "gbp",
                "unit_amount":  int(totals["shipping"] * 100),
                "product_data": {"name": "Standard Shipping"},
            },
            "quantity": 1,
        })
 
    metadata = {}
    if request.user.is_authenticated:
        metadata["user_id"]    = str(request.user.id)
        metadata["user_email"] = request.user.email

    request.session["pending_cart"] = request.session.get("cart", [])
    request.session.modified = True
 
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=line_items,
            customer_email=(
                request.user.email if request.user.is_authenticated else None
            ),
            metadata=metadata,
            success_url=(
                f"{site_url}/order/confirm/?session_id={{CHECKOUT_SESSION_ID}}"
            ),
            cancel_url=f"{site_url}/cart/",
            billing_address_collection="required",
            shipping_address_collection={
                "allowed_countries": ["GB", "IE", "FR", "DE", "ES", "IT", "NL", "US"],
            },
            phone_number_collection={"enabled": True},
            allow_promotion_codes=True,
        )
    except stripe.StripeError as e:
        logger.error("Stripe session creation failed: %s", e)
        return (
            JsonResponse({"error": str(e)}, status=500) if is_ajax
            else (
                messages.error(request, "Payment error. Please try again.")
                or redirect("cart-page")
            )
        )
 
    request.session["stripe_session_id"] = session.id
    request.session.modified = True
 
    if is_ajax:
        return JsonResponse({"checkout_url": session.url})
    return redirect(session.url, permanent=False)




@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload    = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    secret     = settings.STRIPE_WEBHOOK_SECRET
 
    logger.info(
        "Stripe webhook received — sig_header present: %s, secret configured: %s",
        bool(sig_header),
        bool(secret),
    )
 
    if not secret:
        logger.error(
            "STRIPE_WEBHOOK_SECRET is not set. "
            "Set it in Render environment variables → copy the signing secret "
            "from Stripe Dashboard → Webhooks → your endpoint → Signing secret."
        )
        # Return 200 so Stripe doesn't keep retrying — but log the problem
        return HttpResponse("Webhook secret not configured", status=200)
 
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError as e:
        logger.warning("Stripe webhook invalid payload: %s", e)
        return HttpResponse(status=400)
    except stripe.SignatureVerificationError as e:
        logger.warning(
            "Stripe webhook signature verification FAILED. "
            "This usually means STRIPE_WEBHOOK_SECRET is set to the wrong value. "
            "Make sure you copied the signing secret from the DASHBOARD ENDPOINT "
            "(whsec_...) — NOT the CLI listener secret (whsec_test_...). "
            "Error: %s", e
        )
        return HttpResponse(status=400)
 
    logger.info("Stripe webhook event received: %s", event["type"])
 

 
    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        session_id = sess.get("id", "")
        logger.info("checkout.session.completed for session %s", session_id)
 

        order = Order.objects.filter(stripe_session_id=session_id).first()
 
        if order:
            # Order exists — just update status and payment intent
            changed = False
            if order.status not in ("confirmed", "shipped", "delivered"):
                order.status = "confirmed"
                changed = True
            pi = sess.get("payment_intent", "") or ""
            if pi and not order.stripe_payment_intent:
                order.stripe_payment_intent = pi
                changed = True
            if changed:
                order.save(update_fields=["status", "stripe_payment_intent"])
                logger.info("Order %s updated to confirmed via webhook", order.order_number)
        else:
            # Order doesn't exist yet (user closed tab before confirm page loaded)
            # Create it from the Stripe session
            logger.info("Order not found for session %s — creating from webhook", session_id)
            _create_order_from_session(sess)
 
    elif event["type"] == "payment_intent.payment_failed":
        pi = event["data"]["object"]
        updated = Order.objects.filter(
            stripe_payment_intent=pi["id"]
        ).exclude(status__in=("shipped", "delivered")).update(status="cancelled")
        logger.info("payment_intent.payment_failed: %s orders cancelled", updated)
 
    elif event["type"] == "charge.refunded":
        charge = event["data"]["object"]
        pi_id = charge.get("payment_intent", "")
        if pi_id:
            updated = Order.objects.filter(stripe_payment_intent=pi_id).update(status="refunded")
            logger.info("charge.refunded: %s orders refunded for pi %s", updated, pi_id)
 
    return HttpResponse(status=200)




def _create_order_from_session(sess):
    try:
        full_sess = stripe.checkout.Session.retrieve(
            sess["id"],
            expand=["line_items"],
        )
        shipping = full_sess.get("shipping_details") or full_sess.get("customer_details") or {}
        addr     = (shipping.get("address") or {})
 
        order = Order.objects.create(
            guest_email           = full_sess.get("customer_email", "") or "",
            guest_name            = shipping.get("name", "") or "",
            status                = "confirmed",
            stripe_session_id     = full_sess["id"],
            stripe_payment_intent = full_sess.get("payment_intent", "") or "",
            shipping_name         = shipping.get("name", "") or "",
            shipping_line1        = addr.get("line1", "") or "",
            shipping_line2        = addr.get("line2", "") or "",
            shipping_city         = addr.get("city", "") or "",
            shipping_county       = addr.get("state", "") or "",
            shipping_postcode     = addr.get("postal_code", "") or "",
            shipping_country      = addr.get("country", "") or "GB",
        )
 
        # Build items from Stripe line_items
        subtotal = Decimal("0.00")
        line_items = (full_sess.get("line_items") or {}).get("data", [])
        for li in line_items:
            price_obj   = li.get("price") or {}
            prod_obj    = price_obj.get("product") or {}
            name        = prod_obj.get("name", "Item") if isinstance(prod_obj, dict) else "Item"
            unit_amount = price_obj.get("unit_amount", 0) or 0
            price_dec   = Decimal(unit_amount) / 100
            qty         = li.get("quantity", 1)
 
            # Skip shipping line item
            if name == "Standard Shipping":
                order.shipping_cost = price_dec
                continue
 
            OrderItem.objects.create(
                order    = order,
                name     = name,
                sku      = "",
                price    = price_dec,
                quantity = qty,
            )
            subtotal += price_dec * qty
 
        order.subtotal = subtotal
        order.total    = subtotal + order.shipping_cost
        order.save(update_fields=["subtotal", "shipping_cost", "total"])
 
        # Send confirmation email
        try:
            send_order_confirmation_email(order)
        except Exception as e:
            logger.error("Webhook email error for order %s: %s", order.order_number, e)
 
        logger.info("Order %s created from webhook for session %s", order.order_number, sess["id"])
 
    except Exception as e:
        logger.error("Failed to create order from webhook session %s: %s", sess.get("id"), e)




def designservicepage(request):
    ctx = {"service_types": SERVICE_TYPES, "budget_ranges": BUDGET_RANGES}
    if request.method == "GET":
        return render(request, "design-service.html", ctx)

    errors = {}
    service_type     = request.POST.get("service_type", "").strip()
    contact_name     = request.POST.get("contact_name", "").strip()
    contact_email    = request.POST.get("contact_email", "").strip()
    contact_phone    = request.POST.get("contact_phone", "").strip()
    brief_text       = request.POST.get("brief_text", "").strip()
    colour_palette   = request.POST.get("colour_palette", "").strip()
    budget_range     = request.POST.get("budget_range", "").strip()
    deadline_raw     = request.POST.get("deadline", "").strip()
    additional_notes = request.POST.get("additional_notes", "").strip()
    uploaded_files   = request.FILES.getlist("design_files")

    if not service_type:  errors["service_type"]  = "Please select a project type."
    if not contact_name:  errors["contact_name"]   = "Your name is required."
    if not contact_email: errors["contact_email"]  = "Your email is required."
    if not brief_text:    errors["brief_text"]      = "A project description is required."

    deadline = None
    if deadline_raw:
        try:
            deadline = date.fromisoformat(deadline_raw)
        except ValueError:
            errors["deadline"] = "Invalid date format."

    validated_files = []
    if uploaded_files:
        try:
            validated_files = validate_multiple_design_assets(uploaded_files)
        except ValidationError as e:
            errors["design_files"] = str(e.message)

    if errors:
        ctx.update({"errors": errors, "post_data": request.POST})
        return render(request, "design-service.html", ctx)

    sub = DesignSubmission.objects.create(
        user             = request.user if request.user.is_authenticated else None,
        contact_name     = contact_name,
        contact_email    = contact_email,
        contact_phone    = contact_phone,
        service_type     = service_type,
        brief_text       = brief_text,
        colour_palette   = colour_palette,
        budget_range     = budget_range,
        deadline         = deadline,
        additional_notes = additional_notes,
    )
    for f, mime in validated_files:
        DesignSubmissionFile.objects.create(
            submission=sub, file=f,
            original_filename=f.name, mime_type=mime, file_size_bytes=f.size,
        )
    messages.success(request, "Your design request has been submitted! We'll be in touch within 24 hours.")
    return redirect("design-service-page")



def _valid_email(email: str) -> bool:
    return bool(_re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))
 
 
def contactpage(request):
    if request.method == "POST":
        action = request.POST.get("action", "contact")
 
        if action == "newsletter":
            email = request.POST.get("newsletter_email", "").strip().lower()
            if email and _valid_email(email):
                messages.success(
                    request,
                    f"Thanks! {email} has been added to our newsletter."
                )
            else:
                messages.error(request, "Please enter a valid email address.")
            return redirect("contact-page")
 
        full_name = request.POST.get("full_name", "").strip()
        email     = request.POST.get("email",     "").strip().lower()
        phone     = request.POST.get("phone",     "").strip()
        subject   = request.POST.get("subject",   "").strip()
        message   = request.POST.get("message",   "").strip()
 
        # Validation
        errors = {}
        if not full_name:
            errors["full_name"] = "Your name is required."
        if not email:
            errors["email"] = "Your email address is required."
        elif not _valid_email(email):
            errors["email"] = "Please enter a valid email address."
        if not subject:
            errors["subject"] = "Please select a subject."
        if not message:
            errors["message"] = "Please write a message."
        elif len(message) < 10:
            errors["message"] = "Message is too short — please give us more detail."
 
        if errors:
            # Re-render form with errors and preserved values
            return render(request, "contact.html", {
                "form_errors": errors,
                "form_data": {
                    "full_name": full_name,
                    "email":     email,
                    "phone":     phone,
                    "subject":   subject,
                    "message":   message,
                },
            })
 
        # ── Send notification email to admin ───────────────────────
        try:
            from accounts.email_service import _send, _wrap
 
            admin_html = _wrap(f"""
              <h2 style="font-family:Georgia,serif;font-size:22px;font-weight:300;
                         color:#0a0a0a;margin-bottom:20px;">New Contact Enquiry</h2>
              <table style="width:100%;border-collapse:collapse;font-size:13px;color:#4a4a4a;">
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;font-weight:600;width:140px;">Name</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;">{full_name}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;font-weight:600;">Email</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;">
                    <a href="mailto:{email}" style="color:#0a0a0a;">{email}</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;font-weight:600;">Phone</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;">{phone or "—"}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;font-weight:600;">Subject</td>
                  <td style="padding:10px 0;border-bottom:1px solid #e8e8e6;">{subject}</td>
                </tr>
                <tr>
                  <td style="padding:10px 0;font-weight:600;vertical-align:top;">Message</td>
                  <td style="padding:10px 0;white-space:pre-wrap;line-height:1.7;">{message}</td>
                </tr>
              </table>
            """)
 
            admin_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@customisemeuk.com")
            _send(admin_email, "CustomiseMe UK Admin",
                  f"[Contact] {subject} — {full_name}", admin_html)
 
            # ── Send confirmation email to the user ────────────────
            confirm_html = _wrap(f"""
              <h2 style="font-family:Georgia,serif;font-size:26px;font-weight:300;
                         color:#0a0a0a;margin-bottom:16px;">
                We've received your message ✦
              </h2>
              <p style="color:#4a4a4a;font-size:14px;line-height:1.8;margin-bottom:8px;">
                Hello {full_name},
              </p>
              <p style="color:#4a4a4a;font-size:14px;line-height:1.8;margin-bottom:24px;">
                Thanks for reaching out about <strong>{subject}</strong>.
                We typically respond within one business day — we'll reply to
                <strong>{email}</strong>.
              </p>
              <div style="background:#f2f2f0;border:1px solid #e8e8e6;
                          padding:20px 24px;margin-bottom:24px;">
                <p style="font-size:12px;font-weight:600;letter-spacing:.14em;
                           text-transform:uppercase;color:#888;margin-bottom:10px;">
                  Your message
                </p>
                <p style="font-size:13px;color:#4a4a4a;line-height:1.7;
                           white-space:pre-wrap;">{message}</p>
              </div>
              <p style="color:#888;font-size:12px;line-height:1.6;">
                If you didn't send this message, please ignore this email.
              </p>
            """)
            _send(email, full_name,
                  "We received your message — CustomiseMe UK", confirm_html)
 
        except Exception as exc:
            # Email failure is non-fatal — form submission still succeeded
            import logging
            logging.getLogger(__name__).error("Contact email error: %s", exc)
 
        messages.success(
            request,
            f"Thanks {full_name}! Your message has been sent. "
            f"We'll reply to {email} within one business day."
        )
        return redirect("contact-page")
 
    return render(request, "contact.html")



def senditempage(request):
    if request.method == "POST":
        full_name      = request.POST.get("fullName",      "").strip()
        email          = request.POST.get("email",         "").strip()
        phone          = request.POST.get("phone",         "").strip()
        items_desc     = request.POST.get("items",         "").strip()
        custom_details = request.POST.get("customDetails", "").strip()
        agreed_terms   = request.POST.get("agreeTerms")   == "on"
        agreed_waiver  = request.POST.get("agreeWaiver")  == "on"
 
        raw_qty  = request.POST.get("quantity", "").strip()
        quantity = int(raw_qty) if raw_qty.isdigit() else None
 
        raw_deadline = request.POST.get("deadline", "").strip()
        deadline = None
        if raw_deadline:
            try:
                from datetime import date as _date
                deadline = _date.fromisoformat(raw_deadline)
            except ValueError:
                deadline = None
 
        errors = {}
        if not full_name:
            errors["fullName"] = "Name is required."
        if not email:
            errors["email"] = "Email is required."
        if not items_desc:
            errors["items"] = "Please describe the items you are sending."
 
        if errors:
            messages.error(request, "Please correct the errors below.")
            return render(request, "senditems.html", {
                "form_errors": errors,
                "form_data":   request.POST,
            })
 
        send_request = SendItemRequest.objects.create(
            user           = request.user if request.user.is_authenticated else None,
            full_name      = full_name,
            email          = email,
            phone          = phone,
            items_description = items_desc,
            quantity       = quantity,
            deadline       = deadline,
            custom_details = custom_details,
            agreed_terms   = agreed_terms,
            agreed_waiver  = agreed_waiver,
        )
 
        for f in request.FILES.getlist("artwork"):
            SendItemFile.objects.create(
                request           = send_request,
                file              = f,
                original_filename = f.name,
            )
 
        messages.success(
            request,
            "Your request has been submitted! We'll be in touch within 24 hours "
            f"at {email} with a formal quote."
        )
        return redirect("senditems-page")
 
    return render(request, "senditems.html")
