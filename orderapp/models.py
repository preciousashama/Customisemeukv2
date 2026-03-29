from django.db import models
from customiseapp.models import Product
import uuid
from django.conf import settings
from decimal import Decimal
# Create your models here.

ORDER_STATUSES = [
    ("processing", "Processing"),
    ("confirmed",  "Confirmed"),
    ("shipped",    "Shipped"),
    ("delivered",  "Delivered"),
    ("cancelled",  "Cancelled"),
    ("refunded",   "Refunded"),
]


class Order(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number   = models.CharField(max_length=20, unique=True, editable=False)
    customer       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="orders",
    )
    # Guest details stored if no account
    guest_name     = models.CharField(max_length=200, blank=True)
    guest_email    = models.EmailField(blank=True)
 
    status         = models.CharField(max_length=20, choices=ORDER_STATUSES, default="processing")
    subtotal       = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    shipping_cost  = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tax            = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total          = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
 
    # Shipping address
    shipping_name    = models.CharField(max_length=200, blank=True)
    shipping_line1   = models.CharField(max_length=200, blank=True)
    shipping_line2   = models.CharField(max_length=200, blank=True)
    shipping_city    = models.CharField(max_length=100, blank=True)
    shipping_county  = models.CharField(max_length=100, blank=True)
    shipping_postcode = models.CharField(max_length=20, blank=True)
    shipping_country = models.CharField(max_length=100, blank=True, default="United Kingdom")
 
    # Tracking
    tracking_number  = models.CharField(max_length=100, blank=True)
    carrier          = models.CharField(max_length=100, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
 
    stripe_session_id     = models.CharField(max_length=200, blank=True, db_index=True,
                                          help_text="Stripe Checkout Session ID (cs_...)")
    stripe_payment_intent = models.CharField(max_length=200, blank=True,
                                          help_text="Stripe PaymentIntent ID (pi_...)")
 
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ["-created_at"]
 
    def __str__(self):
        return f"Order {self.order_number}"
 
    @property
    def customer_name(self):
        if self.customer:
            return self.customer.full_name or self.customer.email
        return self.guest_name or self.guest_email or "Guest"
 
    @property
    def customer_email_addr(self):
        if self.customer:
            return self.customer.email
        return self.guest_email
 
    def save(self, *args, **kwargs):
        if not self.order_number:
            import random, string
            self.order_number = "ORD-" + "".join(
                random.choices(string.digits, k=6)
            )
        super().save(*args, **kwargs)
 
    def get_timeline(self):
        steps = ["processing", "confirmed", "shipped", "delivered"]
        labels = {"processing": "Order Placed", "confirmed": "Confirmed",
                  "shipped": "Shipped", "delivered": "Delivered"}
        try:
            current_idx = steps.index(self.status)
        except ValueError:
            current_idx = -1
        result = []
        for i, step in enumerate(steps):
            result.append({
                "label":  labels[step],
                "done":   i < current_idx,
                "active": i == current_idx,
                "time":   "",
            })
        return result
 
 
class OrderItem(models.Model):
    order    = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product  = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    name     = models.CharField(max_length=200)
    sku      = models.CharField(max_length=60)
    price    = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    variant  = models.CharField(max_length=200, blank=True,
                                help_text="e.g. 'Size M · Navy'")
    image_url = models.URLField(blank=True)
 
    def __str__(self):
        return f"{self.name} × {self.quantity}"
 
    @property
    def line_total(self):
        return self.price * self.quantity