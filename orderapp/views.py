import logging
import stripe
from decimal import Decimal
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
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _resolve_stripe_product(price_obj):
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
    try:
        list_obj = stripe.checkout.Session.list_line_items(
            session_id,
            limit=100,
            expand=["data.price.product"],
        )
        return list(list_obj.data)
    except stripe.StripeError as e:
        logger.error("Stripe list_line_items failed for %s: %s", session_id, e)
        return []


def _is_shipping_line_item(stripe_name, item_meta, description):
    shipping_keywords = ("standard shipping", "shipping", "delivery", "postage")

    if stripe_name:
        combined = (stripe_name + " " + description).lower()
        if any(kw in combined for kw in shipping_keywords):
            return True

    if (item_meta.get("is_shipping") or "").lower() in ("true", "1", "yes"):
        return True

    return False


def _resolve_product_obj(django_pid, stripe_price_id, stripe_name,
                         product_map, stripe_price_to_product):
    product_obj = product_map.get(django_pid) or stripe_price_to_product.get(stripe_price_id)

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


def _build_items_from_stripe(session_id, order):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    line_items = _fetch_line_items(session_id)
    if not line_items:
        logger.warning("No line items returned for session %s", session_id)
        return Decimal("0.00"), Decimal("0.00")


    product_map = {}
    stripe_price_to_product = {}
    for p in Product.objects.exclude(stripe_price_id=""):
        stripe_price_to_product[p.stripe_price_id] = p
        product_map[str(p.pk)] = p

    subtotal       = Decimal("0.00")
    shipping_total = Decimal("0.00")

    for item in line_items:
        description = getattr(item, "description", "") or ""
        price_obj   = getattr(item, "price", None)
        item_meta   = dict(getattr(item, "metadata", {}) or {})

        stripe_name, stripe_prod_meta, stripe_images = _resolve_stripe_product(price_obj)

      
        logger.debug(
            "Line item — stripe_name=%r description=%r is_shipping=%s",
            stripe_name, description,
            _is_shipping_line_item(stripe_name, item_meta, description),
        )

       
        if _is_shipping_line_item(stripe_name, item_meta, description):
            amount = getattr(item, "amount_total", 0) or 0
            shipping_total += Decimal(str(amount)) / 100
            continue

       
        sku          = item_meta.get("product_sku", "") or stripe_prod_meta.get("sku", "")
        display_name = stripe_name or item_meta.get("product_name", "") or description or "Product"

       
        django_pid      = stripe_prod_meta.get("django_product_id", "")
        stripe_price_id = price_obj.id if price_obj else ""
        product_obj     = _resolve_product_obj(
            django_pid, stripe_price_id, stripe_name,
            product_map, stripe_price_to_product,
        )
        if not product_obj and sku:
            product_obj = Product.objects.filter(sku=sku).first()

        image_url = ""

        if stripe_images:
            image_url = stripe_images[0]

        if not image_url and product_obj and product_obj.image:
            try:
                image_url = product_obj.image.url
            except Exception:
                pass

        if not image_url:
            image_url = stripe_prod_meta.get("image_url", "") or item_meta.get("image_url", "")

        if not image_url:
            fallback_product = None
            if display_name and display_name not in ("Product", "Item"):
                fallback_product = Product.objects.filter(name__iexact=display_name).first()
            if not fallback_product and sku:
                fallback_product = Product.objects.filter(sku__iexact=sku).first()
            if fallback_product and fallback_product.image:
                try:
                    image_url = fallback_product.image.url
                    # Also set product_obj so it links properly
                    if not product_obj:
                        product_obj = fallback_product
                except Exception:
                    pass

        amount_total = getattr(item, "amount_total", 0) or 0
        quantity     = getattr(item, "quantity", 1) or 1
        price        = Decimal(str(amount_total)) / 100 / quantity

        OrderItem.objects.create(
            order     = order,
            product   = product_obj,
            name      = display_name,
            sku       = sku or (product_obj.sku if product_obj else "N/A"),
            price     = price,
            quantity  = quantity,
            variant   = description if (description and description != stripe_name) else "",
            image_url = image_url,
        )
        subtotal += price * quantity

    return subtotal, shipping_total



def orderconfirmpage(request):
    session_id = request.GET.get("session_id")
    if not session_id:
        return render(request, "order-confirm.html", {"error": "No session ID provided."})

    request.session["cart"] = []
    request.session.modified = True
    request.session.save()

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        logger.error("Stripe session retrieval failed: %s", e)
        return render(request, "order-confirm.html", {"error": "Could not retrieve order details."})

    customer_details = session.customer_details or {}
    guest_email = _get_attr(customer_details, "email", "")
    guest_name  = _get_attr(customer_details, "name",  "")

    order, created = Order.objects.get_or_create(
        stripe_session_id=session_id,
        defaults={
            "stripe_payment_intent": session.payment_intent or "",
            "status":                "confirmed",
            "guest_email":           guest_email,
            "guest_name":            guest_name,
        }
    )

    if created:
        # Attach shipping address
        shipping_details = session.shipping_details
        if shipping_details:
            addr = shipping_details.address
            if addr:
                order.shipping_name     = _get_attr(shipping_details, "name", "")
                order.shipping_line1    = addr.line1 or ""
                order.shipping_line2    = addr.line2 or ""
                order.shipping_city     = addr.city or ""
                order.shipping_postcode = addr.postal_code or ""
                order.shipping_country  = addr.country or "GB"

        if request.user.is_authenticated:
            order.customer = request.user

        order.save()
        items_built = False
        try:
            subtotal, shipping_total = _build_items_from_stripe(session_id, order)
            items_built = order.items.exists()
        except Exception as exc:
            logger.error(
                "Error building items for order %s (session %s): %s",
                order.order_number, session_id, exc,
            )
            subtotal      = Decimal("0.00")
            shipping_total = Decimal("0.00")

        order.subtotal      = subtotal
        order.total         = Decimal(str(session.amount_total or 0)) / 100
        order.shipping_cost = shipping_total if shipping_total else (order.total - subtotal)
        order.email_confirmation_sent = False
        order.save()
        if items_built:
            order.refresh_from_db()
            _send_confirmation_email(order)
        else:
            logger.error(
                "Order %s created but no items were built — confirmation email "
                "NOT sent. Investigate Stripe line items for session %s.",
                order.order_number, session_id,
            )

    else:
        has_bad_items = order.items.filter(name="Item").exists()
        needs_rebuild = not order.items.exists() or has_bad_items

        if needs_rebuild:
            logger.warning(
                "Order %s already existed but has missing/bad items — "
                "re-fetching from Stripe.",
                order.order_number,
            )
            order.items.filter(name="Item").delete()
            try:
                subtotal, shipping_total = _build_items_from_stripe(session_id, order)
            except Exception as exc:
                logger.error(
                    "Error rebuilding items for order %s: %s",
                    order.order_number, exc,
                )
                subtotal      = Decimal("0.00")
                shipping_total = Decimal("0.00")

            order.subtotal      = subtotal
            order.total         = Decimal(str(session.amount_total or 0)) / 100
            order.shipping_cost = shipping_total if shipping_total else (order.total - subtotal)
            order.save()

        if not getattr(order, "email_confirmation_sent", True):
            order.refresh_from_db()
            if order.items.exists():
                _send_confirmation_email(order)

    return render(request, "order-confirm.html", {"order": order})


def _send_confirmation_email(order):
    try:
        sent = send_order_confirmation_email(order)
    except Exception as exc:
        logger.error(
            "Unexpected exception sending confirmation email for order %s: %s",
            order.order_number, exc,
        )
        sent = False

    if sent:
        try:
            Order.objects.filter(pk=order.pk).update(email_confirmation_sent=True)
            order.email_confirmation_sent = True
        except Exception:
            pass
        logger.info(
            "Order confirmation email sent for %s → %s",
            order.order_number, order.customer_email_addr,
        )
    else:
        logger.error(
            "send_order_confirmation_email returned False for order %s "
            "(to: %s). Check BREVO_API_KEY and Brevo logs.",
            order.order_number, order.customer_email_addr,
        )



def email_debug_view(request):
    lines = []
 
    def log(label, value="", ok=True):
        icon = "✅" if ok else "❌"
        lines.append(f"<tr><td>{icon} <strong>{label}</strong></td><td><code>{value}</code></td></tr>")
 
    lines.append("<h2>Email Debug Report</h2><table border='1' cellpadding='6'>")
 
    # ── 1. Check settings ──────────────────────────────────────────────────
    brevo_key = getattr(settings, "BREVO_API_KEY", None)
    log("BREVO_API_KEY set", bool(brevo_key), ok=bool(brevo_key))
    if brevo_key:
        log("BREVO_API_KEY value (masked)", brevo_key[:8] + "..." + brevo_key[-4:], ok=True)
 
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    from_name  = getattr(settings, "DEFAULT_FROM_NAME",  None)
    log("DEFAULT_FROM_EMAIL", from_email or "NOT SET", ok=bool(from_email))
    log("DEFAULT_FROM_NAME",  from_name  or "NOT SET", ok=bool(from_name))
 
    site_url = getattr(settings, "SITE_URL", None)
    log("SITE_URL", site_url or "NOT SET", ok=bool(site_url))
 
    # ── 2. Check sib_api_v3_sdk installed ─────────────────────────────────
    try:
        import sib_api_v3_sdk
        log("sib_api_v3_sdk installed", sib_api_v3_sdk.__version__, ok=True)
    except ImportError:
        log("sib_api_v3_sdk installed", "NOT INSTALLED — run: pip install sib-api-v3-sdk", ok=False)
        lines.append("</table>")
        return HttpResponse("<br>".join(lines))
 
    # ── 3. Try initialising Brevo client ──────────────────────────────────
    try:
        cfg = sib_api_v3_sdk.Configuration()
        cfg.api_key["api-key"] = brevo_key
        api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(cfg))
        log("Brevo API client created", "OK", ok=True)
    except Exception as e:
        log("Brevo API client creation", f"FAILED: {e}", ok=False)
        lines.append("</table>")
        return HttpResponse("<br>".join(lines))
 
    # ── 4. Send a real test email ──────────────────────────────────────────
    to_addr = request.GET.get("to", from_email)  # default to sender itself
    if not to_addr:
        log("Test recipient", "No ?to= param and no DEFAULT_FROM_EMAIL", ok=False)
        lines.append("</table>")
        return HttpResponse("<br>".join(lines))
 
    log("Sending test email to", to_addr, ok=True)
    try:
        api.send_transac_email(sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_addr, "name": "Debug Test"}],
            sender={"name": from_name or "CustomiseMe UK", "email": from_email},
            subject="[DEBUG] CustomiseMe UK Email Test",
            html_content=(
                "<h2>Email test successful</h2>"
                "<p>If you received this, Brevo is configured correctly.</p>"
            ),
        ))
        log("Test email sent", f"→ {to_addr}", ok=True)
    except Exception as e:
        log("Test email FAILED", str(e), ok=False)
        lines.append(f"<tr><td colspan='2'><pre>{traceback.format_exc()}</pre></td></tr>")
 
    # ── 5. Test with a real Order if order_number provided ────────────────
    order_number = request.GET.get("order_number")
    if order_number:
        lines.append(f"<tr><td colspan='2'><strong>Testing real order: {order_number}</strong></td></tr>")
        try:
            from orderapp.models import Order
            order = Order.objects.prefetch_related("items").get(
                order_number__iexact=order_number
            )
            log("Order found", str(order.pk), ok=True)
 
            # Check email resolution
            try:
                addr = order.customer_email_addr
                log("order.customer_email_addr", addr or "EMPTY", ok=bool(addr))
            except Exception as e:
                log("order.customer_email_addr", f"ERROR: {e}", ok=False)
 
            # Check guest_email directly
            guest = getattr(order, "guest_email", "N/A")
            log("order.guest_email", guest or "EMPTY", ok=bool(guest))
 
            # Check customer FK
            if order.customer_id:
                try:
                    log("order.customer.email", order.customer.email, ok=True)
                except Exception as e:
                    log("order.customer.email", f"ERROR: {e}", ok=False)
            else:
                log("order.customer", "No FK — guest order", ok=True)
 
            # Check items
            items = list(order.items.all())
            log("order.items count", str(len(items)), ok=len(items) > 0)
            for item in items:
                log(f"  item: {item.name}", f"qty={item.quantity} price=£{item.price}", ok=True)
 
            # Check totals
            log("order.subtotal",      str(order.subtotal),      ok=bool(order.subtotal))
            log("order.total",         str(order.total),         ok=bool(order.total))
            log("order.shipping_cost", str(order.shipping_cost), ok=True)
 
            # Check shipping fields
            log("order.shipping_name",     getattr(order, "shipping_name",     "N/A"), ok=True)
            log("order.shipping_line1",    getattr(order, "shipping_line1",    "N/A"), ok=True)
            log("order.shipping_city",     getattr(order, "shipping_city",     "N/A"), ok=True)
            log("order.shipping_postcode", getattr(order, "shipping_postcode", "N/A"), ok=True)
            log("order.shipping_country",  getattr(order, "shipping_country",  "N/A"), ok=True)
 
            # Check email_confirmation_sent flag
            sent_flag = getattr(order, "email_confirmation_sent", "FIELD MISSING")
            log("order.email_confirmation_sent", str(sent_flag), ok=True)
 
            # Now actually try sending the real confirmation email
            lines.append("<tr><td colspan='2'><strong>Attempting send_order_confirmation_email()...</strong></td></tr>")
            from accounts.email_service import send_order_confirmation_email
            try:
                result = send_order_confirmation_email(order)
                log("send_order_confirmation_email() returned", str(result), ok=result)
            except Exception as e:
                log("send_order_confirmation_email() raised", str(e), ok=False)
                lines.append(f"<tr><td colspan='2'><pre>{traceback.format_exc()}</pre></td></tr>")
 
        except Exception as e:
            log(f"Order lookup for {order_number}", f"FAILED: {e}", ok=False)
 
    lines.append("</table>")
    lines.append("<br><p style='color:red'><strong>REMOVE THIS VIEW BEFORE DEPLOYING TO PRODUCTION.</strong></p>")
    return HttpResponse("\n".join(lines))