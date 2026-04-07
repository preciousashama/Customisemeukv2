import logging
import stripe
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.shortcuts import render
from accounts.email_service import send_order_confirmation_email
from .models import Order, OrderItem
from customiseapp.models import Product

logger = logging.getLogger(__name__)

from django.contrib.auth import get_user_model
User = get_user_model()


def ordertrackingpage(request):
    order        = None
    lookup_error = None
    order_number = ""
    email        = ""

    if request.method == "POST":
        order_number = request.POST.get("order_number", "").strip().lstrip("#").upper()
        email        = request.POST.get("email", "").strip().lower()

        if not order_number or not email:
            lookup_error = "Please enter both your order ID and email address."
        else:
            try:
                order = Order.objects.prefetch_related("items").get(
                    order_number__iexact=order_number,
                )
                owner_email = (order.customer_email_addr or "").lower()
                if not owner_email or owner_email != email:
                    order        = None
                    lookup_error = (
                        "No order found with those details. "
                        "Please check your order number and email address."
                    )
            except Order.DoesNotExist:
                lookup_error = (
                    "No order found with those details. "
                    "Please check your order number and email address."
                )

    return render(request, "order-tracking.html", {
        "order":        order,
        "lookup_error": lookup_error,
        "order_number": order_number,
        "email":        email,
        "timeline":     order.get_timeline() if order else [],
    })


def _get_attr(obj, key, default=""):
    """Safely get a value from either a dict or a Stripe object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _resolve_stripe_product(price_obj):
    """
    Given an expanded price object, return (product_name, metadata_dict, images_list).
    Handles dict, StripeObject, or unexpanded string product ID.
    """
    stripe_product_obj = _get_attr(price_obj, "product")

    if isinstance(stripe_product_obj, dict) and "name" in stripe_product_obj:
        return (
            stripe_product_obj.get("name", ""),
            stripe_product_obj.get("metadata", {}),
            stripe_product_obj.get("images", []),
        )

    if hasattr(stripe_product_obj, "name"):
        return (
            getattr(stripe_product_obj, "name", ""),
            dict(getattr(stripe_product_obj, "metadata", {})),
            list(getattr(stripe_product_obj, "images", []) or []),
        )

    if isinstance(stripe_product_obj, str) and stripe_product_obj.startswith("prod_"):
        try:
            fetched = stripe.Product.retrieve(stripe_product_obj)
            return (
                _get_attr(fetched, "name", ""),
                dict(_get_attr(fetched, "metadata", {}) or {}),
                list(_get_attr(fetched, "images", []) or []),
            )
        except stripe.StripeError as e:
            logger.warning("Could not fetch Stripe product %s: %s", stripe_product_obj, e)

    return ("", {}, [])


def _fetch_line_items(session_id):
    """
    Stripe list_line_items returns a ListObject — access .data directly,
    never .get("data") which always silently returns [].
    """
    try:
        list_obj = stripe.checkout.Session.list_line_items(
            session_id,
            limit=100,
            expand=["data.price.product"],
        )
        return list(list_obj.data)
    except stripe.StripeError as e:
        logger.error("Stripe list_line_items failed: %s", e)
        return []


def _build_product_maps(cart):
    """
    Build product_map and stripe_price_to_product from cart session.
    Falls back to full DB load if cart is empty/expired (common after Stripe redirect).
    """
    cart_by_pid = {}
    for c in (cart or []):
        pid = str(c.get("product_id") or c.get("id") or "").strip()
        if pid:
            cart_by_pid[pid] = c

    product_map = {}
    stripe_price_to_product = {}

    if cart_by_pid:
        for p in Product.objects.filter(pk__in=cart_by_pid.keys()):
            product_map[str(p.pk)] = p
            if p.stripe_price_id:
                stripe_price_to_product[p.stripe_price_id] = p

    # Always ensure stripe_price_to_product is populated —
    # cart session is often expired by the time customer hits confirm page
    if not stripe_price_to_product:
        for p in Product.objects.exclude(stripe_price_id=""):
            stripe_price_to_product[p.stripe_price_id] = p
            product_map[str(p.pk)] = p

    return cart_by_pid, product_map, stripe_price_to_product


def _resolve_product_obj(django_pid, stripe_pid, stripe_name, product_map, stripe_price_to_product):
    """Try every available strategy to resolve the Django Product for a line item."""

    # 1. Match by django_product_id from Stripe metadata (fastest, most reliable)
    product_obj = product_map.get(django_pid) or stripe_price_to_product.get(stripe_pid)

    # 2. Direct DB lookup by django_product_id
    if not product_obj and django_pid:
        try:
            product_obj = Product.objects.get(pk=django_pid)
        except Product.DoesNotExist:
            pass

    # 3. Case-insensitive name match
    if not product_obj and stripe_name and stripe_name not in ("", "Standard Shipping", "Item"):
        product_obj = Product.objects.filter(name__iexact=stripe_name).first()

    # 4. Last resort: only one product exists
    if not product_obj and len(product_map) == 1:
        product_obj = next(iter(product_map.values()))

    return product_obj


def _is_shipping_line_item(stripe_name, stripe_meta, li_description):
    shipping_keywords = ("standard shipping", "shipping", "delivery", "postage")
    if stripe_name.lower() in shipping_keywords:
        return True
    if (stripe_meta.get("is_shipping") or "").lower() in ("true", "1", "yes"):
        return True
    if li_description.lower() in shipping_keywords:
        return True
    return False


def orderconfirmpage(request):
    session_id = request.GET.get("session_id")
    if not session_id:
        return render(request, "order-confirm.html", {"error": "No session ID provided."})

    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["line_items.data.price.product"]
        )
    except Exception as e:
        logger.error("Stripe session retrieval failed: %s", e)
        return render(request, "order-confirm.html", {"error": "Could not retrieve order details."})

    order, created = Order.objects.get_or_create(
        stripe_session_id=session_id,
        defaults={
            "stripe_payment_intent": session.payment_intent,
            "status": "confirmed",
            "guest_email": session.customer_details.email or "",
            "guest_name": session.customer_details.name or "",
        }
    )

    if created:
        addr = session.shipping_details.address if session.shipping_details else None
        if addr:
            order.shipping_name    = session.shipping_details.name or ""
            order.shipping_line1   = addr.line1 or ""
            order.shipping_line2   = addr.line2 or ""
            order.shipping_city    = addr.city or ""
            order.shipping_postcode = addr.postal_code or ""
            order.shipping_country = addr.country or "GB"

        if request.user.is_authenticated:
            order.customer = request.user
        order.save()

        line_items = session.line_items.data
        subtotal = Decimal("0.00")

        for item in line_items:
            description = getattr(item, "description", "") or ""

            if "shipping" in description.lower():
                continue

            price_obj    = getattr(item, "price", None)
            product_data = getattr(price_obj, "product", None) if price_obj else None

            item_metadata = dict(getattr(item, "metadata", {}) or {})
            meta_name     = item_metadata.get("product_name", "")
            sku           = item_metadata.get("product_sku", "")

            if not meta_name and product_data is not None:
                stripe_product_name = getattr(product_data, "name", "") or ""
            else:
                stripe_product_name = ""

            display_name = meta_name or stripe_product_name or description or "Product"

            product_obj = None
            if sku:
                product_obj = Product.objects.filter(sku=sku).first()
            if not product_obj and product_data is not None:
                # Try matching via django_product_id stored in Stripe product metadata
                stripe_prod_meta = dict(getattr(product_data, "metadata", {}) or {})
                django_pid = stripe_prod_meta.get("django_product_id", "")
                if django_pid:
                    try:
                        product_obj = Product.objects.get(pk=django_pid)
                    except Product.DoesNotExist:
                        pass
            if not product_obj and display_name:
                product_obj = Product.objects.filter(name__iexact=display_name).first()

            # ── FIX 3: read images via getattr, not .get() ──
            image_url = ""
            if product_data is not None:
                images = getattr(product_data, "images", None) or []
                if images:
                    image_url = images[0]
            if not image_url and product_obj and product_obj.image:
                try:
                    image_url = product_obj.image.url
                except Exception:
                    pass

            amount_total = getattr(item, "amount_total", 0) or 0
            quantity     = getattr(item, "quantity", 1) or 1
            price        = Decimal(str(amount_total / 100)) / quantity

            OrderItem.objects.create(
                order     = order,
                product   = product_obj,
                name      = display_name,
                sku       = sku or (product_obj.sku if product_obj else "N/A"),
                price     = price,
                quantity  = quantity,
                variant   = description if meta_name else "",
                image_url = image_url,
            )
            subtotal += price * quantity

        order.subtotal     = subtotal
        order.total        = Decimal(str((session.amount_total or 0) / 100))
        order.shipping_cost = order.total - subtotal
        order.save()

        # Clear cart
        request.session["cart"] = []
        request.session.modified = True

    return render(request, "order-confirm.html", {"order": order})