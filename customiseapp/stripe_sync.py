
import logging

import stripe
from django.conf import settings
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def sync_product_to_stripe(product):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    if not stripe.api_key:
        logger.warning("STRIPE_SECRET_KEY not set — skipping Stripe sync for %s", product)
        return None, None

    # ── Firebase image URL — only include if it's a real public HTTPS URL ──
    images = []
    try:
        if product.image:
            url = product.image.url
            if url.startswith("https://"):
                images = [url]
    except Exception:
        pass  # image not yet available on first save

    # ── Stripe Product kwargs ──────────────────────────────────────────
    # Do NOT use stripe.UNSET — not available in stripe-python < 5.x.
    # Only add 'images' key when we have actual images.
    product_kwargs = dict(
        name=product.name,
        description=product.description[:500] if product.description else "",
        metadata={
            "django_product_id": str(product.id),
            "sku":               product.sku,
            "category":          product.category,
        },
        active=product.is_active,
    )
    if images:
        product_kwargs["images"] = images

    # ── Step 1: Create or update Stripe Product ────────────────────────
    try:
        if product.stripe_product_id:
            stripe_product = stripe.Product.modify(
                product.stripe_product_id, **product_kwargs
            )
        else:
            stripe_product = stripe.Product.create(**product_kwargs)
    except stripe.StripeError as e:
        logger.error("Stripe Product sync failed for %s: %s", product, e)
        return None, None

    stripe_product_id = stripe_product.id

    # ── Step 2: Create or update Stripe Price ─────────────────────────
    unit_amount = int(product.price * 100)  # £ to pence

    try:
        need_new_price = True

        if product.stripe_price_id:
            try:
                existing = stripe.Price.retrieve(product.stripe_price_id)
                if (
                    existing.unit_amount == unit_amount
                    and existing.currency == "gbp"
                    and existing.active
                ):
                    need_new_price = False
                else:
                    stripe.Price.modify(product.stripe_price_id, active=False)
            except stripe.StripeError:
                pass

        if need_new_price:
            new_price = stripe.Price.create(
                product=stripe_product_id,
                unit_amount=unit_amount,
                currency="gbp",
                metadata={
                    "django_product_id": str(product.id),
                    "sku":               product.sku,
                },
            )
            stripe_price_id = new_price.id
        else:
            stripe_price_id = product.stripe_price_id

    except stripe.StripeError as e:
        logger.error("Stripe Price sync failed for %s: %s", product, e)
        return stripe_product_id, None

    # ── Step 3: Write IDs back via .update() (NOT .save()) ────────────
    # Import is here — NOT at the top of the file — so it only runs
    # after Django is fully initialised and FirebaseStorage is active.
    from customiseapp.models import Product as ProductModel
    ProductModel.objects.filter(pk=product.pk).update(
        stripe_product_id=stripe_product_id,
        stripe_price_id=stripe_price_id,
    )

    logger.info(
        "Stripe sync OK — product=%s  stripe_product=%s  stripe_price=%s",
        product.name, stripe_product_id, stripe_price_id,
    )
    return stripe_product_id, stripe_price_id


# ─────────────────────────────────────────────────────────────
# Signals — registered by apps.py ready()
# ─────────────────────────────────────────────────────────────

@receiver(post_save, sender="customiseapp.Product")
def on_product_saved(sender, instance, created, **kwargs):
    """Fires after every Product.save(). Skips £0 products."""
    if not instance.price or instance.price <= 0:
        logger.debug("Skipping Stripe sync for %s — price is £0", instance)
        return
    sync_product_to_stripe(instance)


@receiver(pre_delete, sender="customiseapp.Product")
def on_product_deleted(sender, instance, **kwargs):
    """Archives the Stripe Product when the Django Product is deleted."""
    if not instance.stripe_product_id:
        return
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        stripe.Product.modify(instance.stripe_product_id, active=False)
        logger.info("Archived Stripe product %s", instance.stripe_product_id)
    except stripe.StripeError as e:
        logger.warning(
            "Could not archive Stripe product %s: %s",
            instance.stripe_product_id, e,
        )