
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CarouselSlide, Category, Product, Wishlist,
    DesignSubmission, DesignSubmissionFile,SendItemRequest,SendItemFile
)



@admin.register(CarouselSlide)
class CarouselSlideAdmin(admin.ModelAdmin):
    list_display    = ("title", "position", "is_active", "image_preview", "updated_at")
    list_editable   = ("position", "is_active")
    list_per_page   = 20
    ordering        = ("position", "id")
    readonly_fields = ("image_preview", "created_at", "updated_at")

    fieldsets = (
        (None,        {"fields": ("title", "subtitle", "image", "image_preview")}),
        ("Display",   {"fields": ("position", "is_active")}),
        ("Timestamps",{"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:4px;object-fit:cover;"/>',
                obj.image.url,
            )
        return "—"
    image_preview.short_description = "Preview"




@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display        = ("name", "slug")
    search_fields       = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering            = ("name",)




@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = (
        "name", "sku", "category", "price", "compare_at_price",
        "stock", "stock_status_badge", "is_active",
        "stripe_ids_display",        # shows prod_... / price_... IDs
        "image_preview", "updated_at",
    )
    list_editable = ("price", "compare_at_price", "stock", "is_active")
    list_filter   = ("is_active", "category")
    search_fields = ("name", "sku", "category", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = (
        "id", "image_preview",
        "stripe_product_id", "stripe_price_id",   # set by signal — not editable
        "created_at", "updated_at",
    )
    list_per_page = 25
    ordering      = ("name",)

    fieldsets = (
        ("Core", {
            "fields": (
                "id", "name", "slug", "sku", "category", "description",
            ),
        }),
        ("Pricing & Stock", {
            "fields": ("price", "compare_at_price", "stock"),
        }),
        ("Media", {
            "fields": ("image", "image_preview"),
        }),
        ("Status", {
            "fields": ("is_active",),
        }),
        ("Stripe (read-only — auto-synced on save)", {
            "classes": ("collapse",),
            "fields":  ("stripe_product_id", "stripe_price_id"),
            "description": (
                "These IDs are populated automatically when you save a product. "
                "Do not edit them manually."
            ),
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields":  ("created_at", "updated_at"),
        }),
    )

    # ── Computed columns ──────────────────────────────────────

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:4px;object-fit:cover;"/>',
                obj.image.url,
            )
        return "—"
    image_preview.short_description = "Preview"

    def stock_status_badge(self, obj):
        if obj.is_out_of_stock:
            colour, label = "#c0392b", "Out of Stock"
        elif obj.is_low_stock:
            colour, label = "#e67e22", f"Low ({obj.stock})"
        else:
            colour, label = "#27ae60", "In Stock"
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            colour, label,
        )
    stock_status_badge.short_description = "Stock"

    def stripe_ids_display(self, obj):
        """
        Shows a green tick + last 12 chars of the Stripe IDs,
        or a red 'Not synced' label when the product hasn't been synced yet.
        """
        if obj.stripe_product_id:
            return format_html(
                '<span style="font-size:10px;line-height:1.6;">'
                '<span style="color:#27ae60;font-weight:600;">&#10003; Synced</span><br/>'
                '<span style="color:#888;">prod …{}</span><br/>'
                '<span style="color:#888;">price …{}</span>'
                '</span>',
                obj.stripe_product_id[-12:],
                obj.stripe_price_id[-12:] if obj.stripe_price_id else "—",
            )
        return format_html(
            '<span style="font-size:10px;color:#c0392b;font-weight:600;">'
            '&#10007; Not synced</span>'
        )
    stripe_ids_display.short_description = "Stripe"

    # ── Bulk actions ──────────────────────────────────────────

    actions = ["mark_active", "mark_inactive", "sync_to_stripe"]

    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} product(s) marked active.")
    mark_active.short_description = "Mark selected products as active"

    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} product(s) marked inactive.")
    mark_inactive.short_description = "Mark selected products as inactive"

    def sync_to_stripe(self, request, queryset):
        from customiseapp.stripe_sync import sync_product_to_stripe
        ok = fail = skipped = 0
        for product in queryset:
            if not product.price or product.price <= 0:
                skipped += 1
                continue
            pid, price_id = sync_product_to_stripe(product)
            if pid and price_id:
                ok += 1
            else:
                fail += 1
        if ok:
            self.message_user(request, f"✓ {ok} product(s) synced to Stripe.")
        if skipped:
            self.message_user(
                request,
                f"{skipped} product(s) skipped (price is £0).",
                level="warning",
            )
        if fail:
            self.message_user(
                request,
                f"✗ {fail} product(s) failed — check STRIPE_SECRET_KEY and server logs.",
                level="error",
            )
    sync_to_stripe.short_description = "↑ Sync selected products to Stripe"




@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display    = ("user", "product_name", "product_price", "added_at")
    list_filter     = ("added_at",)
    search_fields   = ("user__email", "user__username", "product__name", "product__sku")
    readonly_fields = ("id", "user", "product", "added_at")
    ordering        = ("-added_at",)
    list_per_page   = 30

    def has_add_permission(self, request):
        return False

    def product_name(self, obj):
        return obj.product.name
    product_name.short_description  = "Product"
    product_name.admin_order_field  = "product__name"

    def product_price(self, obj):
        return f"£{obj.product.price}"
    product_price.short_description = "Price"




class DesignSubmissionFileInline(admin.TabularInline):
    model           = DesignSubmissionFile
    extra           = 0
    readonly_fields = ("original_filename", "mime_type", "file_size_display", "file_link", "uploaded_at")
    fields          = ("original_filename", "mime_type", "file_size_display", "file_link", "uploaded_at")
    can_delete      = True

    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.file.url)
        return "—"
    file_link.short_description = "File"

    def file_size_display(self, obj):
        return f"{obj.file_size_mb} MB"
    file_size_display.short_description = "Size"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DesignSubmission)
class DesignSubmissionAdmin(admin.ModelAdmin):
    list_display  = (
        "short_id", "contact_name", "contact_email",
        "service_type", "budget_range", "status", "status_badge",
        "deadline", "created_at",
    )
    list_filter   = ("status", "service_type", "budget_range")
    search_fields = ("contact_name", "contact_email", "contact_phone", "brief_text")
    list_editable = ("status",)
    readonly_fields = (
        "id", "user", "contact_name", "contact_email", "contact_phone",
        "service_type", "brief_text", "colour_palette", "budget_range",
        "deadline", "additional_notes", "created_at", "updated_at",
    )
    ordering      = ("-created_at",)
    list_per_page = 25
    inlines       = [DesignSubmissionFileInline]
    save_on_top   = True

    fieldsets = (
        ("Contact",         {"fields": ("id", "user", "contact_name", "contact_email", "contact_phone")}),
        ("Project Brief",   {"fields": ("service_type", "brief_text", "colour_palette", "budget_range", "deadline", "additional_notes")}),
        ("Status & Note",   {"fields": ("status", "admin_note")}),
        ("Timestamps",      {"classes": ("collapse",), "fields": ("created_at", "updated_at")}),
    )

    def short_id(self, obj):
        return str(obj.id)[:8].upper()
    short_id.short_description = "ID"

    def status_badge(self, obj):
        colours = {
            "pending": "#888", "in_review": "#2980b9",
            "in_progress": "#e67e22", "completed": "#27ae60", "rejected": "#c0392b",
        }
        colour = colours.get(obj.status, "#888")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 9px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    actions = ["mark_in_review", "mark_in_progress", "mark_completed", "mark_rejected"]

    def mark_in_review(self, request, qs):
        qs.update(status="in_review")
        self.message_user(request, f"{qs.count()} submission(s) marked In Review.")
    mark_in_review.short_description = "→ Mark as In Review"

    def mark_in_progress(self, request, qs):
        qs.update(status="in_progress")
        self.message_user(request, f"{qs.count()} submission(s) marked In Progress.")
    mark_in_progress.short_description = "→ Mark as In Progress"

    def mark_completed(self, request, qs):
        qs.update(status="completed")
        self.message_user(request, f"{qs.count()} submission(s) marked Completed.")
    mark_completed.short_description = "→ Mark as Completed"

    def mark_rejected(self, request, qs):
        qs.update(status="rejected")
        self.message_user(request, f"{qs.count()} submission(s) marked Rejected.")
    mark_rejected.short_description = "→ Mark as Rejected"



class SendItemFileInline(admin.TabularInline):
    """Shows uploaded files inline within the request detail page."""
    model       = SendItemFile
    extra       = 0
    readonly_fields = ("original_filename", "file", "uploaded_at")
    can_delete  = False
 
    def has_add_permission(self, request, obj=None):
        return False
 
 
@admin.register(SendItemRequest)
class SendItemRequestAdmin(admin.ModelAdmin):
    list_display   = (
        "id", "full_name", "email", "phone",
        "quantity", "deadline", "status", "quoted_price", "created_at",
    )
    list_filter    = ("status", "created_at", "agreed_terms", "agreed_waiver")
    search_fields  = ("full_name", "email", "phone", "items_description")
    list_editable  = ("status",)        
    date_hierarchy = "created_at"
    ordering       = ("-created_at",)
 
    readonly_fields = ("user", "full_name", "email", "phone",
                       "items_description", "quantity", "deadline",
                       "custom_details", "agreed_terms", "agreed_waiver",
                       "created_at", "updated_at")
 
    fieldsets = (
        ("Customer", {
            "fields": ("user", "full_name", "email", "phone"),
        }),
        ("What They're Sending", {
            "fields": ("items_description", "quantity", "deadline"),
        }),
        ("Customisation Brief", {
            "fields": ("custom_details",),
        }),
        ("Agreements", {
            "fields": ("agreed_terms", "agreed_waiver"),
        }),
        ("Admin", {
            "fields": ("status", "quoted_price", "admin_notes"),
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )
 
    inlines = [SendItemFileInline]
 
    def has_add_permission(self, request):
        return False