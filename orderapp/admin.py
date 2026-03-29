# =====================================================================
#  orderapp/admin.py
# =====================================================================
from django.contrib import admin
from django.utils.html import format_html

from .models import Order, OrderItem


# ─────────────────────────────────────────────────────────────
# OrderItem inline
# ─────────────────────────────────────────────────────────────

class OrderItemInline(admin.TabularInline):
    model         = OrderItem
    extra         = 0
    readonly_fields = (
        "product", "name", "sku", "variant",
        "price", "quantity", "line_total_display", "image_preview",
    )
    fields        = (
        "product", "name", "sku", "variant",
        "price", "quantity", "line_total_display", "image_preview",
    )
    can_delete    = False

    def line_total_display(self, obj):
        return f"£{obj.line_total:.2f}"
    line_total_display.short_description = "Line Total"

    def image_preview(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" style="height:44px;border-radius:3px;object-fit:cover;"/>',
                obj.image_url,
            )
        return "—"
    image_preview.short_description = "Image"

    def has_add_permission(self, request, obj=None):
        return False


# ─────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = (
        "order_number", "customer_display", "status", "status_badge",
        "total_display", "item_count",
        "tracking_number", "created_at",
    )
    list_filter   = ("status", "created_at", "shipping_country")
    search_fields = (
        "order_number", "guest_name", "guest_email",
        "customer__email", "customer__first_name", "customer__last_name",
        "tracking_number", "stripe_session_id", "stripe_payment_intent",
    )
    list_editable = ("status",)
    ordering      = ("-created_at",)
    list_per_page = 25
    date_hierarchy = "created_at"
    inlines       = [OrderItemInline]
    save_on_top   = True

    readonly_fields = (
        "id", "order_number", "customer",
        "guest_name", "guest_email",
        "subtotal", "shipping_cost", "tax", "total",
        "stripe_session_id", "stripe_payment_intent",
        "created_at", "updated_at",
        "shipping_address_block",
    )

    fieldsets = (
        ("Order", {
            "fields": (
                "id", "order_number", "status",
                "customer", "guest_name", "guest_email",
            ),
        }),
        ("Financials", {
            "fields": ("subtotal", "shipping_cost", "tax", "total"),
        }),
        ("Shipping Address", {
            "fields": ("shipping_address_block",),
        }),
        ("Fulfilment", {
            "fields": ("tracking_number", "carrier", "estimated_delivery"),
        }),
        ("Stripe", {
            "classes": ("collapse",),
            "fields":  ("stripe_session_id", "stripe_payment_intent"),
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields":  ("created_at", "updated_at"),
        }),
    )

    # ── computed columns ──────────────────────────────────────

    def customer_display(self, obj):
        if obj.customer:
            name  = getattr(obj.customer, "full_name", None) or obj.customer.email
            email = obj.customer.email
            return format_html("{}<br/><small style='color:#888;'>{}</small>", name, email)
        return format_html(
            "{}<br/><small style='color:#888;'>{}</small>",
            obj.guest_name or "Guest",
            obj.guest_email or "—",
        )
    customer_display.short_description = "Customer"
    customer_display.admin_order_field = "guest_email"

    def status_badge(self, obj):
        colours = {
            "processing": "#888",
            "confirmed":  "#2980b9",
            "shipped":    "#8e44ad",
            "delivered":  "#27ae60",
            "cancelled":  "#c0392b",
            "refunded":   "#e67e22",
        }
        colour = colours.get(obj.status, "#888")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 9px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def total_display(self, obj):
        return f"£{obj.total:.2f}"
    total_display.short_description = "Total"
    total_display.admin_order_field = "total"

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = "Items"

    def shipping_address_block(self, obj):
        lines = filter(None, [
            obj.shipping_name,
            obj.shipping_line1,
            obj.shipping_line2,
            obj.shipping_city,
            obj.shipping_county,
            obj.shipping_postcode,
            obj.shipping_country,
        ])
        return format_html("<br/>".join(lines))
    shipping_address_block.short_description = "Shipping Address"

    # ── bulk actions ──────────────────────────────────────────

    actions = [
        "mark_confirmed", "mark_shipped",
        "mark_delivered", "mark_cancelled",
    ]

    def mark_confirmed(self, request, qs):
        n = qs.filter(status="processing").update(status="confirmed")
        self.message_user(request, f"{n} order(s) confirmed.")
    mark_confirmed.short_description = "→ Mark as Confirmed"

    def mark_shipped(self, request, qs):
        n = qs.filter(status__in=("processing", "confirmed")).update(status="shipped")
        self.message_user(request, f"{n} order(s) marked Shipped.")
    mark_shipped.short_description = "→ Mark as Shipped"

    def mark_delivered(self, request, qs):
        n = qs.filter(status="shipped").update(status="delivered")
        self.message_user(request, f"{n} order(s) marked Delivered.")
    mark_delivered.short_description = "→ Mark as Delivered"

    def mark_cancelled(self, request, qs):
        n = qs.filter(status__in=("processing", "confirmed")).update(status="cancelled")
        self.message_user(request, f"{n} order(s) cancelled.")
    mark_cancelled.short_description = "→ Mark as Cancelled"