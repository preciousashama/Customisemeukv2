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
    Handles dict, StripeObject, unexpanded string ID.
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
            name   = _get_attr(fetched, "name", "")
            meta   = dict(_get_attr(fetched, "metadata", {}) or {})
            images = list(_get_attr(fetched, "images", []) or [])
            return name, meta, images
        except stripe.StripeError as e:
            logger.warning("Could not fetch Stripe product %s: %s", stripe_product_obj, e)

    return ("", {}, [])


def _fetch_line_items(session_id):
    """
    Stripe list_line_items returns a ListObject not a plain dict.
    Access .data directly — never .get("data").
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

    if not stripe_price_to_product:
        for p in Product.objects.exclude(stripe_price_id=""):
            stripe_price_to_product[p.stripe_price_id] = p
            product_map[str(p.pk)] = p

    return cart_by_pid, product_map, stripe_price_to_product


def _resolve_product_obj(django_pid, stripe_pid, stripe_name, product_map, stripe_price_to_product):
    product_obj = product_map.get(django_pid) or stripe_price_to_product.get(stripe_pid)

    if not product_obj and django_pid:
        try:
            product_obj = Product.objects.get(pk=django_pid)
        except Product.DoesNotExist:
            pass

    if not product_obj and stripe_name and stripe_name not in ("", "Standard Shipping", "Item"):
        product_obj = Product.objects.filter(name__iexact=stripe_name).first()

    if not product_obj and len(product_map) == 1:
        product_obj = next(iter(product_map.values()))

    return product_obj


def orderconfirmpage(request):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    order      = None
    error      = None
    debug_info = {}

    session_id = request.GET.get("session_id", "").strip()

    if not session_id:
        error = "No payment session found. If your payment was successful, please contact support."
        return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0, "debug_info": {}})

    order = (
        Order.objects
        .prefetch_related("items__product")
        .filter(stripe_session_id=session_id)
        .first()
    )

    if not order:
        debug_info["session_id"] = session_id

        try:
            sess = stripe.checkout.Session.retrieve(
                session_id,
                expand=["line_items.data.price.product"],
            )
            debug_info["payment_status"] = _get_attr(sess, "payment_status")
        except stripe.StripeError as e:
            error = "Could not verify your payment. Please contact support."
            debug_info["stripe_session_error"] = str(e)
            return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0, "debug_info": debug_info})

        if _get_attr(sess, "payment_status") not in ("paid", "no_payment_required"):
            error = "Payment has not been completed. Please try again."
            return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0, "debug_info": debug_info})

        # ── Fetch line items ───────────────────────────────────────────
        stripe_line_items = _fetch_line_items(session_id)
        debug_info["line_items_count"] = len(stripe_line_items)
        debug_info["line_items_raw"]   = []

        for _i, _li in enumerate(stripe_line_items):
            _price_obj  = _get_attr(_li, "price") or {}
            _prod_obj   = _get_attr(_price_obj, "product")
            _sname, _smeta, _simages = _resolve_stripe_product(_price_obj)
            debug_info["line_items_raw"].append({
                "index":            _i,
                "description":      _get_attr(_li, "description"),
                "qty":              _get_attr(_li, "quantity"),
                "unit_amount":      _get_attr(_price_obj, "unit_amount"),
                "price_id":         _get_attr(_price_obj, "id"),
                "product_obj_type": type(_prod_obj).__name__,
                "stripe_name":      _sname,
                "stripe_meta":      _smeta,
                "stripe_images":    _simages,
            })

        shipping  = _get_attr(sess, "shipping_details") or _get_attr(sess, "customer_details") or {}
        addr      = _get_attr(shipping, "address") or {}
        _customer = request.user if request.user.is_authenticated else None
        if _customer is None:
            _uid = (_get_attr(sess, "metadata") or {}).get("user_id")
            if _uid:
                try:
                    _customer = User.objects.get(pk=_uid)
                except User.DoesNotExist:
                    pass

        order = Order.objects.create(
            customer              = _customer,
            guest_name            = _get_attr(shipping, "name") or "",
            guest_email           = _get_attr(sess, "customer_email") or "",
            status                = "confirmed",
            stripe_session_id     = session_id,
            stripe_payment_intent = _get_attr(sess, "payment_intent") or "",
            shipping_name         = _get_attr(shipping, "name") or "",
            shipping_line1        = _get_attr(addr, "line1") or "",
            shipping_line2        = _get_attr(addr, "line2") or "",
            shipping_city         = _get_attr(addr, "city") or "",
            shipping_county       = _get_attr(addr, "state") or "",
            shipping_postcode     = _get_attr(addr, "postal_code") or "",
            shipping_country      = _get_attr(addr, "country") or "GB",
        )

        cart = request.session.pop("pending_cart", None) or request.session.get("cart", [])
        cart_by_pid, product_map, stripe_price_to_product = _build_product_maps(cart)
        debug_info["product_map_keys"]      = list(product_map.keys())
        debug_info["stripe_price_map_keys"] = list(stripe_price_to_product.keys())
        debug_info["cart_by_pid_keys"]      = list(cart_by_pid.keys())
        debug_info["order_items_created"]   = []

        subtotal = Decimal("0.00")

        if stripe_line_items:
            for li in stripe_line_items:
                qty         = _get_attr(li, "quantity") or 1
                price_obj   = _get_attr(li, "price") or {}
                stripe_pid  = _get_attr(price_obj, "id") or ""
                unit_amount = _get_attr(price_obj, "unit_amount") or 0
                price       = Decimal(str(unit_amount)) / 100

                stripe_name, stripe_meta, stripe_images = _resolve_stripe_product(price_obj)
                li_description = (_get_attr(li, "description") or "").strip()

                if stripe_name == "Standard Shipping":
                    continue
                if (stripe_meta.get("is_shipping") or "").lower() in ("true", "1", "yes"):
                    continue
                if li_description.lower() in ("standard shipping", "shipping"):
                    continue

                django_pid  = stripe_meta.get("django_product_id", "")
                product_obj = _resolve_product_obj(
                    django_pid, stripe_pid, stripe_name,
                    product_map, stripe_price_to_product,
                )

                name = (
                    (product_obj.name if product_obj else None)
                    or (stripe_name if stripe_name and stripe_name not in ("Item",) else None)
                    or (li_description if li_description.lower() not in ("item", "") else None)
                    or "Unknown Product"
                )
                sku = (
                    (product_obj.sku if product_obj else None)
                    or stripe_meta.get("sku", "")
                    or ""
                )
                image_url = ""
                if product_obj and product_obj.image:
                    try:
                        image_url = product_obj.image.url
                    except Exception:
                        pass
                if not image_url and stripe_images:
                    image_url = stripe_images[0]

                cart_item = (
                    cart_by_pid.get(django_pid)
                    or cart_by_pid.get(str(product_obj.pk) if product_obj else "")
                )
                variant = (cart_item or {}).get("variant", "") or ""

                debug_info["order_items_created"].append({
                    "django_pid":          django_pid,
                    "stripe_pid":          stripe_pid,
                    "stripe_name":         stripe_name,
                    "stripe_meta":         stripe_meta,
                    "stripe_images":       stripe_images,
                    "resolved_product_pk": str(product_obj.pk) if product_obj else None,
                    "resolved_name":       name,
                    "resolved_image":      image_url,
                    "price":               str(price),
                    "qty":                 qty,
                })

                OrderItem.objects.create(
                    order=order, product=product_obj,
                    name=name, sku=sku, price=price,
                    quantity=qty, variant=variant, image_url=image_url,
                )
                subtotal += price * qty

        else:
            debug_info["fallback"] = "NO Stripe line items — fell back to cart session"
            for item in (cart or []):
                try:
                    price = Decimal(str(item.get("price", "0")))
                except InvalidOperation:
                    price = Decimal("0.00")
                qty = max(1, int(item.get("quantity", 1)))

                if item.get("is_shipping"):
                    continue
                pid = str(item.get("product_id") or item.get("id") or "").strip()
                if not pid and price in (Decimal("4.99"), Decimal("0.00")):
                    continue

                product_obj = product_map.get(pid)
                if not product_obj and pid:
                    try:
                        product_obj = Product.objects.get(pk=pid)
                    except Product.DoesNotExist:
                        pass

                name = (
                    (product_obj.name if product_obj else None)
                    or item.get("name", "").strip()
                    or "Unknown Product"
                )
                sku = (
                    (product_obj.sku if product_obj else None)
                    or item.get("sku", "").strip()
                    or ""
                )
                image_url = ""
                if product_obj and product_obj.image:
                    try:
                        image_url = product_obj.image.url
                    except Exception:
                        pass
                else:
                    image_url = item.get("image_url", "") or ""

                OrderItem.objects.create(
                    order=order, product=product_obj,
                    name=name, sku=sku, price=price,
                    quantity=qty,
                    variant=item.get("variant", "") or "",
                    image_url=image_url,
                )
                subtotal += price * qty

        shipping_cost       = Decimal("0.00") if subtotal >= 100 else Decimal("4.99")
        order.subtotal      = subtotal
        order.shipping_cost = shipping_cost
        order.total         = subtotal + shipping_cost
        order.save(update_fields=["subtotal", "shipping_cost", "total"])

        try:
            send_order_confirmation_email(order)
        except Exception as e:
            logger.error("Order email error for %s: %s", order.order_number, e)

    if order and order.status in ("confirmed", "shipped", "delivered"):
        request.session["cart"] = []
        request.session.modified = True

    if order and order.customer and order.customer != request.user:
        if not getattr(request.user, "is_staff", False):
            order = None
            error = "You do not have permission to view this order."

    return render(request, "order-confirm.html", {
        "order":      order,
        "error":      error,
        "cart_count": 0,
        "debug_info": debug_info,
    })
