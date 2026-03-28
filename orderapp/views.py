
import logging

# from django.contrib import messages
from django.shortcuts import render # get_object_or_404

from .models import Order 
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)





 
def orderconfirmpage(request):
    order  = None
    error  = None
    session_id = request.GET.get("session_id", "").strip()
 
    if not session_id:
        return render(request, "order-confirm.html", {"order": None, "error": "No session ID provided."})
 
    order = Order.objects.prefetch_related("items__product").filter(
        stripe_session_id=session_id
    ).first()
 
    if not order:
        try:
            sess = stripe.checkout.Session.retrieve(
                session_id,
                expand=["line_items", "customer_details"],
            )
        except stripe.StripeError as e:
            logger.error("Stripe session retrieve failed: %s", e)
            return render(request, "order-confirm.html", {
                "order": None,
                "error": "Could not verify your payment. Please contact support.",
            })
 
        if sess.get("payment_status") not in ("paid", "no_payment_required"):
            return render(request, "order-confirm.html", {
                "order": None,
                "error": "Payment has not been completed for this session.",
            })
 
 
        shipping_details = sess.get("shipping_details") or sess.get("customer_details") or {}
        addr = (shipping_details.get("address") or {})
 
        order = Order.objects.create(
            customer              = request.user if request.user.is_authenticated else None,
            guest_name            = shipping_details.get("name", "") or "",
            guest_email           = sess.get("customer_email", "") or "",
            status                = "confirmed",
            stripe_session_id     = session_id,
            stripe_payment_intent = sess.get("payment_intent", "") or "",
            shipping_name         = shipping_details.get("name", "") or "",
            shipping_line1        = addr.get("line1", "") or "",
            shipping_line2        = addr.get("line2", "") or "",
            shipping_city         = addr.get("city", "") or "",
            shipping_postcode     = addr.get("postal_code", "") or "",
            shipping_country      = addr.get("country", "") or "GB",
        )
 
        
        cart = request.session.get("cart", [])
        subtotal = Decimal("0.00")
 
        for item in cart:
            try:
                price = Decimal(str(item.get("price", "0")))
            except InvalidOperation:
                price = Decimal("0.00")
            qty = max(1, int(item.get("quantity", 1)))
 
            product_obj = None
            pid = item.get("product_id", "")
            if pid:
                try:
                    product_obj = Product.objects.get(pk=pid)
                except Product.DoesNotExist:
                    pass
 
            OrderItem.objects.create(
                order     = order,
                product   = product_obj,
                name      = item.get("name", ""),
                sku       = (product_obj.sku if product_obj else "") or "",
                price     = price,
                quantity  = qty,
                variant   = item.get("variant", "") or "",
                image_url = item.get("image_url", "") or "",
            )
            subtotal += price * qty
 
        shipping_cost = Decimal("0.00") if subtotal >= 100 else Decimal("4.99")
        order.subtotal      = subtotal
        order.shipping_cost = shipping_cost
        order.total         = subtotal + shipping_cost
        order.save(update_fields=["subtotal", "shipping_cost", "total"])
 
        # Clear the cart — order is now recorded
        request.session["cart"] = []
        request.session.modified = True
 
    
    if order.customer and order.customer != request.user:
        if not request.user.is_staff:
            order = None
            error = "You do not have permission to view this order."
 
    return render(request, "order-confirm.html", {"order": order, "error": error})


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
                    order = None
                    lookup_error = (
                        "No order found with those details. "
                        "Please check your order number and email address."
                    )
 
            except Order.DoesNotExist:
                lookup_error = (
                    "No order found with those details. "
                    "Please check your order number and email address."
                )
 
    context = {
        "order":        order,
        "lookup_error": lookup_error,
        "order_number": order_number,   # repopulates input on failed lookup
        "email":        email,           # repopulates input on failed lookup
        "timeline":     order.get_timeline() if order else [],
    }
    return render(request, "order-tracking.html", context)



def orderconfirmpage(request):
    order = None
    order_id = request.GET.get("order") or request.session.get("last_order_id")

    if order_id:
        try:
            order = Order.objects.prefetch_related("items").get(
                order_number__iexact=str(order_id).lstrip("#")
            )
            if order.customer and order.customer != request.user:
                if not request.user.is_staff:
                    order = None   
        except Order.DoesNotExist:
            pass
        if "last_order_id" in request.session:
            del request.session["last_order_id"]

    context = {
        "order": order,
    }
    return render(request, "order-confirm.html", context)
