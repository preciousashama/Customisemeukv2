
import logging

# from django.contrib import messages
from django.shortcuts import render # get_object_or_404

from .models import Order 

logger = logging.getLogger(__name__)


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