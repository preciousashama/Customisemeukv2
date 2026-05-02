
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


def _firebase_storage():
    from customiseapp.firebase_storage import FirebaseStorage
    return FirebaseStorage()


class CarouselSlide(models.Model):
    title      = models.CharField(max_length=200)
    subtitle   = models.CharField(max_length=400, blank=True)
    image      = models.ImageField(
        upload_to="carousel/",
        storage=_firebase_storage,  
        blank=True,
    )
    position   = models.PositiveSmallIntegerField(default=0)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.title


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

CATEGORY_CHOICES = [
    ("Apparel",           "Apparel"),
    ("Accessories",       "Accessories"),
    ("Party Essentials",  "Party Essentials"),
    ("Stickers & Labels", "Stickers & Labels"),
    ("Other",             "Other"),
]

class Product(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=200)
    slug        = models.SlugField(max_length=220, unique=True)
    sku         = models.CharField(max_length=60, unique=True)
    category = models.CharField(
            max_length=100,
            blank=True,
            choices=CATEGORY_CHOICES,
        )
    description = models.TextField(blank=True)
    price       = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Original price before discount — shown as strikethrough",
    )
    stock     = models.PositiveIntegerField(default=0)
    image     = models.ImageField(
        upload_to="products/",
        storage=_firebase_storage, 
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    # Stripe IDs — auto-populated by stripe_sync signal
    stripe_product_id = models.CharField(
        max_length=100, blank=True, editable=False,
        help_text="Stripe Product ID (prod_...) — auto-synced on save",
    )
    stripe_price_id = models.CharField(
        max_length=100, blank=True, editable=False,
        help_text="Stripe Price ID (price_...) — auto-synced on save",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def is_low_stock(self):
        return 0 < self.stock <= 5

    @property
    def is_out_of_stock(self):
        return self.stock == 0

    @property
    def is_on_sale(self):
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    @property
    def stock_label(self):
        if self.is_out_of_stock:
            return "out_of_stock"
        if self.is_low_stock:
            return f"only_{self.stock}_left"
        return "in_stock"


class Wishlist(models.Model):
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="wishlisted_by",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "product")]
        ordering        = ["-added_at"]

    def __str__(self):
        return f"{self.user} ❤ {self.product.name}"


SUBMISSION_STATUS = [
    ("pending",     "Pending"),
    ("in_review",   "In Review"),
    ("in_progress", "In Progress"),
    ("completed",   "Completed"),
    ("rejected",    "Rejected"),
]

SERVICE_TYPES = [
    ("logo_brand",    "Logo & Brand Identity"),
    ("embroidery",    "Custom Embroidery Design"),
    ("print_merch",   "Print & Merchandise Design"),
    ("social_media",  "Social Media Graphics"),
    ("sticker_label", "Sticker & Label Design"),
    ("other",         "Other Custom Request"),
]

BUDGET_RANGES = [
    ("under_50",  "Under £50"),
    ("50_150",    "£50 – £150"),
    ("150_500",   "£150 – £500"),
    ("500_1000",  "£500 – £1,000"),
    ("over_1000", "Over £1,000"),
]

SUBMISSION_ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/svg+xml", "application/pdf",
    "application/postscript", "application/illustrator",
}
SUBMISSION_MAX_MB = 25


class DesignSubmission(models.Model):
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user          = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="design_submissions",
    )
    contact_name  = models.CharField(max_length=200)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30, blank=True)
    service_type  = models.CharField(max_length=30, choices=SERVICE_TYPES, default="other")
    brief_text    = models.TextField()
    colour_palette   = models.CharField(max_length=200, blank=True)
    budget_range  = models.CharField(max_length=20, choices=BUDGET_RANGES, blank=True)
    deadline      = models.DateField(null=True, blank=True)
    additional_notes = models.TextField(blank=True)
    status        = models.CharField(max_length=20, choices=SUBMISSION_STATUS, default="pending")
    admin_note    = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Submission #{str(self.id)[:8]} — {self.contact_name}"


class DesignSubmissionFile(models.Model):
    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission        = models.ForeignKey(
        DesignSubmission, on_delete=models.CASCADE, related_name="files"
    )
    file              = models.FileField(
        upload_to="design_submissions/",
        storage=_firebase_storage, 
    )
    original_filename = models.CharField(max_length=255)
    mime_type         = models.CharField(max_length=100, blank=True)
    file_size_bytes   = models.PositiveBigIntegerField(default=0)
    uploaded_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_filename

    @property
    def file_size_mb(self):
        return round(self.file_size_bytes / (1024 * 1024), 2)
    



class SendItemRequest(models.Model):
    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending Review"
        QUOTED    = "quoted",    "Quote Sent"
        CONFIRMED = "confirmed", "Confirmed"
        IN_WORK   = "in_work",   "In Production"
        SHIPPED   = "shipped",   "Shipped Back"
        COMPLETE  = "complete",  "Complete"
        CANCELLED = "cancelled", "Cancelled"
 
    user          = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="send_item_requests",
        help_text="Logged-in user who submitted (null if guest).",
    )
    full_name     = models.CharField(max_length=255)
    email         = models.EmailField()
    phone         = models.CharField(max_length=40, blank=True)
 

    items_description = models.TextField(
        help_text="Free-text description of the garments/accessories being sent."
    )
    quantity      = models.PositiveSmallIntegerField(null=True, blank=True)
    deadline      = models.DateField(null=True, blank=True)
 
    
    custom_details = models.TextField(
        blank=True,
        help_text="Design brief: placement, method (print/embroidery), colours, etc.",
    )
 
    
    status        = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    admin_notes   = models.TextField(
        blank=True,
        help_text="Internal notes for the team (not visible to the customer).",
    )
    quoted_price  = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        help_text="Price quoted to the customer in GBP.",
    )
 
    created_at    = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at    = models.DateTimeField(auto_now=True)
    agreed_terms  = models.BooleanField(default=False)
    agreed_waiver = models.BooleanField(default=False)
 
    class Meta:
        verbose_name        = "Send Item Request"
        verbose_name_plural = "Send Item Requests"
        ordering            = ["-created_at"]
 
    def __str__(self):
        return f"#{self.pk} — {self.full_name} ({self.status}) — {self.created_at:%d %b %Y}"
 
 
class SendItemFile(models.Model):
    request   = models.ForeignKey(
        SendItemRequest,
        on_delete=models.CASCADE,
        related_name="files",
    )
    file      = models.FileField(
        storage=_firebase_storage,
        upload_to="send-item-requests/",
    )
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at       = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name        = "Send Item File"
        verbose_name_plural = "Send Item Files"
        ordering            = ["uploaded_at"]
 
    def __str__(self):
        return self.original_filename or str(self.file)
    


class ProductCustomisation(models.Model):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user            = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="product_customisations",
    )
    session_key     = models.CharField(max_length=64, blank=True, db_index=True,
                                       help_text="Django session key for guest users.")
    product         = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="customisations",
    )
 
    # Customisation choices
    colour          = models.CharField(max_length=80, blank=True)
    size            = models.CharField(max_length=20, blank=True)
    artwork_size    = models.CharField(max_length=20, blank=True,
                                       help_text="Small / Medium / Large")
    placement       = models.CharField(max_length=50, blank=True,
                                       help_text="e.g. Front Centre, Back Full")
    printing_side   = models.CharField(max_length=30, blank=True,
                                       help_text="Front Only / Back Only / Front & Back")
 
    artwork_file    = models.FileField(
        upload_to="product-customisations/",
        storage=_firebase_storage,
        blank=True, null=True,
        help_text="Front artwork (or only artwork for single-side products).",
    )
    artwork_filename = models.CharField(max_length=255, blank=True)
 
    artwork_file_back = models.FileField(
        upload_to="product-customisations/back/",
        storage=_firebase_storage,
        blank=True, null=True,
        help_text="Back artwork — populated only when printing side is 'Front & Back'.",
    )
    artwork_filename_back = models.CharField(max_length=255, blank=True)
 
    # Quantity — used for Stickers & Labels and Party Essentials categories
    quantity = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Selected quantity (stickers, party items, etc.).",
    )
 
    # Additional free-text field — used for Party Essentials
    additional_info = models.TextField(
        blank=True,
        help_text="Extra info provided by customer (e.g. party text, font choice).",
    )
 
    # Final calculated price passed from the form
    final_price     = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
 
    variant_summary = models.TextField(blank=True)
 
    # Admin-facing fields
    FULFILMENT_STATUS = [
        ("pending",       "Pending"),
        ("in_production", "In Production"),
        ("completed",     "Completed"),
        ("on_hold",       "On Hold"),
        ("cancelled",     "Cancelled"),
    ]
    fulfilment_status = models.CharField(
        max_length=20, choices=FULFILMENT_STATUS, default="pending",
        help_text="Admin-set production status visible in the dashboard.",
    )
    admin_note        = models.TextField(blank=True,
                                         help_text="Internal note — not shown to customer.")
 
    created_at      = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Product Customisation"
        verbose_name_plural = "Product Customisations"
 
    def __str__(self):
        return (
            f"{self.product.name if self.product else '?'} — "
            f"{self.colour} / {self.size} — {self.created_at:%d %b %Y}"
        )