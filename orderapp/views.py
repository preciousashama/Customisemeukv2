
import logging
import stripe
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.shortcuts import render # get_object_or_404
from accounts.email_service import send_order_confirmation_email
from .models import Order,OrderItem
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




def _resolve_stripe_product(price_obj):
    stripe_product_obj = price_obj.get("product") if isinstance(price_obj, dict) else getattr(price_obj, "product", None)
 
    if isinstance(stripe_product_obj, dict) and "name" in stripe_product_obj:
        return (
            stripe_product_obj.get("name", ""),
            stripe_product_obj.get("metadata", {}),
        )
 
    if hasattr(stripe_product_obj, "name"):
        return (
            getattr(stripe_product_obj, "name", ""),
            dict(getattr(stripe_product_obj, "metadata", {})),
        )
 
    if isinstance(stripe_product_obj, str) and stripe_product_obj.startswith("prod_"):
        try:
            fetched = stripe.Product.retrieve(stripe_product_obj)
            return (
                fetched.get("name", "") if isinstance(fetched, dict) else getattr(fetched, "name", ""),
                dict(fetched.get("metadata", {}) if isinstance(fetched, dict) else getattr(fetched, "metadata", {})),
            )
        except stripe.StripeError as e:
            logger.warning("Could not fetch Stripe product %s: %s", stripe_product_obj, e)
 
    return ("", {})
 
 
def orderconfirmpage(request):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    order          = None
    error          = None
 
    session_id = request.GET.get("session_id", "").strip()
 
    if not session_id:
        error = "No payment session found. If your payment was successful, please contact support."
        return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0})
 
    order = (
        Order.objects
        .prefetch_related("items__product")
        .filter(stripe_session_id=session_id)
        .first()
    )
 
    if not order:
        try:
            sess = stripe.checkout.Session.retrieve(
                session_id,
                expand=["line_items.data.price.product"],
            )
        except stripe.StripeError as e:
            logger.error("Stripe session retrieve failed: %s", e)
            error = "Could not verify your payment. Please contact support."
            return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0})
 
        if sess.get("payment_status") not in ("paid", "no_payment_required"):
            error = "Payment has not been completed. Please try again."
            return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0})
 
        try:
            line_items_resp = stripe.checkout.Session.list_line_items(
                session_id,
                limit=100,
                expand=["data.price.product"],
            )
            stripe_line_items = line_items_resp.get("data", [])
        except stripe.StripeError as e:
            logger.error("Stripe list_line_items failed: %s", e)
            stripe_line_items = []
 
        shipping = sess.get("shipping_details") or sess.get("customer_details") or {}
        addr     = shipping.get("address") or {}
 
        _customer = request.user if request.user.is_authenticated else None
        if _customer is None:
            _uid = (sess.get("metadata") or {}).get("user_id")
            if _uid:
                try:
                    _customer = User.objects.get(pk=_uid)
                except User.DoesNotExist:
                    pass
 
        order = Order.objects.create(
            customer              = _customer,
            guest_name            = shipping.get("name", "") or "",
            guest_email           = sess.get("customer_email", "") or "",
            status                = "confirmed",
            stripe_session_id     = session_id,
            stripe_payment_intent = sess.get("payment_intent", "") or "",
            shipping_name         = shipping.get("name", "") or "",
            shipping_line1        = addr.get("line1", "") or "",
            shipping_line2        = addr.get("line2", "") or "",
            shipping_city         = addr.get("city", "") or "",
            shipping_county       = addr.get("state", "") or "",
            shipping_postcode     = addr.get("postal_code", "") or "",
            shipping_country      = addr.get("country", "") or "GB",
        )
 
        cart = request.session.pop("pending_cart", None) or request.session.get("cart", [])
        cart_by_pid = {}
        for c in cart:
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
            for p in Product.objects.exclude(stripe_price_id="").only(
                "id", "name", "sku", "stripe_price_id", "image"
            ):
                stripe_price_to_product[p.stripe_price_id] = p
                product_map[str(p.pk)] = p
 
        logger.info("stripe_line_items count: %d", len(stripe_line_items))
        logger.info("product_map keys: %s", list(product_map.keys()))
 
        subtotal = Decimal("0.00")
 
        if stripe_line_items:
            for li in stripe_line_items:
                qty        = li.get("quantity", 1)
                price_obj  = li.get("price") or {}
                stripe_pid = price_obj.get("id", "") if isinstance(price_obj, dict) else getattr(price_obj, "id", "")
                unit_amount = price_obj.get("unit_amount", 0) if isinstance(price_obj, dict) else getattr(price_obj, "unit_amount", 0)
                price = Decimal(str(unit_amount)) / 100
 
                stripe_name, stripe_meta = _resolve_stripe_product(price_obj)
 
                li_description = li.get("description", "") or ""
 
                if stripe_name == "Standard Shipping":
                    continue
                is_shipping_meta = (stripe_meta.get("is_shipping") or "").lower() in ("true", "1", "yes")
                if is_shipping_meta:
                    continue
                if li_description.lower() in ("standard shipping", "shipping"):
                    continue
 
                django_pid  = stripe_meta.get("django_product_id", "")
                product_obj = (
                    product_map.get(django_pid)
                    or stripe_price_to_product.get(stripe_pid)
                )
 
                if not product_obj and django_pid:
                    try:
                        product_obj = Product.objects.get(pk=django_pid)
                        logger.info("Resolved product via Stripe metadata: %s", product_obj.name)
                    except Product.DoesNotExist:
                        logger.warning("No product found for django_product_id=%s", django_pid)
 
                if not product_obj and stripe_name and stripe_name not in ("", "Standard Shipping"):
                    matched = Product.objects.filter(name__iexact=stripe_name).first()
                    if matched:
                        product_obj = matched
                        logger.info("Resolved product by name match: %s", product_obj.name)
 
                if not product_obj and len(product_map) == 1:
                    product_obj = next(iter(product_map.values()))
 
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
 
                cart_item = (
                    cart_by_pid.get(django_pid)
                    or cart_by_pid.get(str(product_obj.pk) if product_obj else "")
                )
                variant = (cart_item or {}).get("variant", "") or ""
 
                logger.info(
                    "Creating OrderItem: name=%s sku=%s price=%s qty=%s django_pid=%s stripe_name=%s product_obj=%s",
                    name, sku, price, qty, django_pid, stripe_name,
                    product_obj.pk if product_obj else None,
                )
 
                OrderItem.objects.create(
                    order=order, product=product_obj,
                    name=name, sku=sku, price=price,
                    quantity=qty, variant=variant, image_url=image_url,
                )
                subtotal += price * qty
 
        else:
            logger.warning(
                "No Stripe line items — falling back to cart session for order %s",
                order.order_number
            )
            for item in cart:
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
 
        shipping_cost = Decimal("0.00") if subtotal >= 100 else Decimal("4.99")
        order.subtotal      = subtotal
        order.shipping_cost = shipping_cost
        order.total         = subtotal + shipping_cost
        order.save(update_fields=["subtotal", "shipping_cost", "total"])
 
        logger.info("Order %s created for session %s", order.order_number, session_id)
 
        try:
            sent = send_order_confirmation_email(order)
            if sent:
                logger.info("Confirmation email sent for %s", order.order_number)
            else:
                logger.warning("Confirmation email failed for %s", order.order_number)
        except Exception as e:
            logger.error("Order email error for %s: %s", order.order_number, e)
 
    if order and order.status in ("confirmed", "shipped", "delivered"):
        request.session["cart"] = []
        request.session.modified = True
 
    if order and order.customer and order.customer != request.user:
        if not getattr(request.user, "is_staff", False):
            logger.warning("Unauthorized confirm page access for order %s", order.pk)
            order = None
            error = "You do not have permission to view this order."
 
    return render(request, "order-confirm.html", {"order": order, "error": error, "cart_count": 0})
