
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
                expand=["line_items.data.price.product", "customer_details"],
            )
        except stripe.StripeError as e:
            logger.error("Stripe session retrieve failed: %s", e)
            error = "Could not verify your payment. Please contact support."
            return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0})

        if sess.get("payment_status") not in ("paid", "no_payment_required"):
            error = "Payment has not been completed. Please try again."
            return render(request, "order-confirm.html", {"order": None, "error": error, "cart_count": 0})

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

        subtotal = Decimal("0.00")

        cart = request.session.pop("pending_cart", None) or request.session.get("cart", [])
        cart_by_stripe_price = {}   # stripe_price_id → cart item
        cart_by_pid          = {}   # product_id      → cart item
        for c in cart:
            pid = str(c.get("product_id") or c.get("id") or "").strip()
            if pid:
                cart_by_pid[pid] = c

        product_map = {}  # str(pk) → Product instance
        if cart_by_pid:
            for p in Product.objects.filter(pk__in=cart_by_pid.keys()):
                product_map[str(p.pk)] = p
                # also index by stripe_price_id for Stripe line_item matching
                if p.stripe_price_id:
                    cart_by_stripe_price[p.stripe_price_id] = p

        stripe_line_items = (sess.get("line_items") or {}).get("data", [])

        for li in stripe_line_items:
            qty          = li.get("quantity", 1)
            amount_total = li.get("amount_total", 0)   # pence
            price_obj    = li.get("price") or {}
            stripe_pid   = price_obj.get("id", "")     # Stripe price_id
            unit_amount  = price_obj.get("unit_amount", 0)
            price        = Decimal(unit_amount) / 100

            stripe_product_obj = price_obj.get("product") or {}
            stripe_name        = (
                stripe_product_obj.get("name", "") if isinstance(stripe_product_obj, dict)
                else ""
            )
            stripe_meta        = (
                stripe_product_obj.get("metadata", {}) if isinstance(stripe_product_obj, dict)
                else {}
            )

            if stripe_name == "Standard Shipping" or price == Decimal("4.99") and qty == 1 and not stripe_meta.get("django_product_id"):
                continue

            django_pid  = stripe_meta.get("django_product_id", "")
            product_obj = (
                product_map.get(django_pid)
                or cart_by_stripe_price.get(stripe_pid)
            )

            if not product_obj and len(product_map) == 1:
                product_obj = next(iter(product_map.values()))

            name = (
                (product_obj.name if product_obj else None)
                or stripe_name
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

            cart_item = cart_by_pid.get(django_pid) or cart_by_pid.get(str(product_obj.pk) if product_obj else "")
            variant   = (cart_item or {}).get("variant", "") or ""

            OrderItem.objects.create(
                order     = order,
                product   = product_obj,
                name      = name,
                sku       = sku,
                price     = price,
                quantity  = qty,
                variant   = variant,
                image_url = image_url,
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
