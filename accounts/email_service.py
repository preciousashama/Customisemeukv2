import logging
from typing import Optional

from django.conf import settings

logger = logging.getLogger("accounts")


def _brevo_api():
    try:
        import sib_api_v3_sdk  # type: ignore
        cfg = sib_api_v3_sdk.Configuration()
        cfg.api_key["api-key"] = settings.BREVO_API_KEY
        return sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(cfg)), sib_api_v3_sdk
    except ImportError:
        return None, None


def _send(to_email: str, to_name: str, subject: str, html: str) -> bool:
    if not getattr(settings, "BREVO_API_KEY", None):
        logger.info("[DEV EMAIL] To:%s | Subject:%s\n%s", to_email, subject, html)
        return True
    api, sdk = _brevo_api()
    if api is None:
        logger.error("Brevo SDK unavailable for %s", to_email)
        return False
    try:
        api.send_transac_email(sdk.SendSmtpEmail(
            to=[{"email": to_email, "name": to_name}],
            sender={"name": settings.DEFAULT_FROM_NAME,
                    "email": settings.DEFAULT_FROM_EMAIL},
            subject=subject,
            html_content=html,
        ))
        logger.info("Email sent → %s (%s)", to_email, subject)
        return True
    except Exception as exc:
        logger.error("Brevo error for %s: %s", to_email, exc)
        return False


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _wrap(body: str) -> str:
    return f"""
    <div style="font-family:DM Sans,sans-serif;max-width:600px;margin:0 auto;
                padding:40px 24px;background:#f2f2f0;">
      <div style="background:#0a0a0a;padding:24px 32px;margin-bottom:32px;">
        <h1 style="font-family:Georgia,serif;color:#f8f8f6;font-size:24px;
                   font-weight:300;margin:0;letter-spacing:.1em;">
          CUSTOMISE<em>ME</em> UK
        </h1>
      </div>
      <div style="background:#f8f8f6;padding:40px 32px;border:1px solid #e8e8e6;">
        {body}
      </div>
      <p style="color:#b0b0b0;font-size:11px;text-align:center;margin-top:24px;">
        © 2026 CustomiseMe UK · All rights reserved.
      </p>
    </div>"""


def _btn(url: str, label: str) -> str:
    return (
        f'<a href="{url}" style="display:inline-block;background:#0a0a0a;'
        f'color:#f8f8f6;padding:16px 36px;font-size:11px;font-weight:600;'
        f'letter-spacing:.18em;text-transform:uppercase;text-decoration:none;">'
        f'{label} →</a>'
    )


# ── Public send functions ──────────────────────────────────────────────────────

def send_pending_verification_email(email: str, full_name: str, token: str) -> bool:
    """
    NEW — used by the email-first registration flow.

    Sends an activation link to an address that is NOT yet in the database.
    The token is a Django signed payload (not a DB model), so the link is
    the sole proof of email ownership.  The link points to:

        GET /activate/<token>/

    which is handled by activate_account() in views.py.

    Parameters
    ----------
    email      : the address to verify (not yet a User row)
    full_name  : optional display name from the registration form
    token      : django.core.signing.dumps() output
    """
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    url      = f"{site_url}/account/activate/{token}/"
    ttl_h    = getattr(settings, "REGISTRATION_TOKEN_MAX_AGE", 86_400) // 3600
    greeting = f"Hello {full_name}," if full_name else "Hello,"

    body = f"""
      <h2 style="font-family:Georgia,serif;font-size:28px;font-weight:300;
                 color:#0a0a0a;margin-bottom:16px;">Activate your account</h2>
      <p style="color:#4a4a4a;font-size:14px;line-height:1.7;margin-bottom:8px;">
        {greeting}
      </p>
      <p style="color:#4a4a4a;font-size:14px;line-height:1.7;margin-bottom:32px;">
        You're almost there. Click the button below to verify your email address
        and create your CustomiseMe UK account.
        This link expires in <strong>{ttl_h} hour{"s" if ttl_h != 1 else ""}</strong>.
      </p>
      {_btn(url, "Activate My Account")}
      <p style="color:#888;font-size:12px;margin-top:32px;line-height:1.6;">
        If you did not register for CustomiseMe UK, simply ignore this email —
        no account will be created.<br/><br/>
        Can't click the button? Copy this link:<br/>
        <a href="{url}" style="color:#0a0a0a;word-break:break-all;">{url}</a>
      </p>"""

    display_name = full_name or email
    return _send(email, display_name,
                 "Activate your CustomiseMe UK account", _wrap(body))


def send_verification_email(user, token: str) -> bool:
    """Legacy flow — sends to an existing (inactive) User row."""
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    url  = f"{site_url}/auth/verify-email/{token}/"
    ttl  = getattr(settings, "EMAIL_VERIFICATION_TIMEOUT_HOURS", 24)
    body = f"""
      <h2 style="font-family:Georgia,serif;font-size:28px;font-weight:300;
                 color:#0a0a0a;margin-bottom:16px;">Verify your email</h2>
      <p style="color:#4a4a4a;font-size:14px;line-height:1.7;margin-bottom:8px;">
        Hello {user.full_name or "there"},
      </p>
      <p style="color:#4a4a4a;font-size:14px;line-height:1.7;margin-bottom:32px;">
        Click below to verify your email address and activate your account.
        This link expires in <strong>{ttl} hours</strong>.
      </p>
      {_btn(url, "Verify Email Address")}
      <p style="color:#888;font-size:12px;margin-top:32px;line-height:1.6;">
        If you did not create an account, please ignore this email.<br/>
        Or copy: <a href="{url}" style="color:#0a0a0a;">{url}</a>
      </p>"""
    return _send(user.email, user.full_name or user.email,
                 "Verify your CustomiseMe UK account", _wrap(body))


def send_welcome_email(user) -> bool:
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    url  = f"{site_url}/shop/"
    body = f"""
      <h2 style="font-family:Georgia,serif;font-size:28px;font-weight:300;
                 color:#0a0a0a;margin-bottom:16px;">
        Welcome, {user.full_name or "there"} ✦
      </h2>
      <p style="color:#4a4a4a;font-size:14px;line-height:1.7;margin-bottom:24px;">
        Your account is now active. Every stitch tells a story — and yours begins today.
      </p>
      {_btn(url, "Start Shopping")}"""
    return _send(user.email, user.full_name or user.email,
                 "Welcome to CustomiseMe UK 🎉", _wrap(body))


def send_password_reset_email(user, token: str) -> bool:
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    url  = f"{site_url}/auth/reset-password/{token}/"
    ttl  = getattr(settings, "PASSWORD_RESET_TIMEOUT_HOURS", 2)
    body = f"""
      <h2 style="font-family:Georgia,serif;font-size:28px;font-weight:300;
                 color:#0a0a0a;margin-bottom:16px;">Password Reset</h2>
      <p style="color:#4a4a4a;font-size:14px;line-height:1.7;margin-bottom:32px;">
        We received a request to reset the password for
        <strong>{user.email}</strong>.
        This link expires in <strong>{ttl} hours</strong>.
      </p>
      {_btn(url, "Reset Password")}
      <p style="color:#888;font-size:12px;margin-top:32px;line-height:1.6;">
        If you did not request this, ignore this email.<br/>
        Or copy: <a href="{url}" style="color:#0a0a0a;">{url}</a>
      </p>"""
    return _send(user.email, user.full_name or user.email,
                 "Reset your CustomiseMe UK password", _wrap(body))


def send_admin_login_alert(user, ip: Optional[str] = None) -> bool:
    from django.utils import timezone as tz
    body = f"""
      <h2 style="font-family:Georgia,serif;font-size:22px;font-weight:300;
                 color:#0a0a0a;margin-bottom:16px;">New Admin Login Detected</h2>
      <table style="width:100%;border-collapse:collapse;font-size:13px;color:#4a4a4a;">
        <tr><td style="padding:8px 0;border-bottom:1px solid #e8e8e6;font-weight:600;">Account</td>
            <td style="padding:8px 0;border-bottom:1px solid #e8e8e6;">{user.email}</td></tr>
        <tr><td style="padding:8px 0;border-bottom:1px solid #e8e8e6;font-weight:600;">Time</td>
            <td style="padding:8px 0;border-bottom:1px solid #e8e8e6;">
              {tz.now().strftime("%d %b %Y, %H:%M %Z")}</td></tr>
        <tr><td style="padding:8px 0;font-weight:600;">IP Address</td>
            <td style="padding:8px 0;">{ip or "Unknown"}</td></tr>
      </table>
      <p style="color:#888;font-size:12px;margin-top:24px;">
        If this was not you, contact your system administrator immediately.
      </p>"""
    return _send(user.email, user.full_name or user.email,
                 "Admin Login Alert — CustomiseMe UK", _wrap(body))




def send_order_confirmation_email(order) -> bool:  
    to_email = (order.customer_email_addr or "").strip()
    if not to_email:
        logger.warning("Order %s has no email — skipping confirmation email", order.order_number)
        return False
 
    to_name  = order.customer_name or to_email
    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
 
    items_html = ""
    try:
        for item in order.items.all():
            line_total = item.price * item.quantity
            image_tag = ""
            if hasattr(item, "image_url") and item.image_url:
                image_tag = f'<img src="{item.image_url}" width="48" height="48" style="object-fit:cover;border-radius:4px;margin-right:12px;vertical-align:middle;" />'
            
            items_html += f"""
            <tr>
              <td style="padding:12px 0;border-bottom:1px solid #e8e8e6;font-size:13px;color:#1a1a1a;">
                <div style="display:flex;align-items:center;">
                  {image_tag}
                  <span>
                    {item.name}
                    {"<br/><span style='font-size:11px;color:#888;'>" + item.variant + "</span>" if item.variant else ""}
                  </span>
                </div>
              </td>
              <td style="padding:12px 0;border-bottom:1px solid #e8e8e6;font-size:13px;color:#888;text-align:center;">
                {item.quantity}
              </td>
              <td style="padding:12px 0;border-bottom:1px solid #e8e8e6;font-size:13px;color:#1a1a1a;text-align:right;">
                £{line_total:.2f}
              </td>
            </tr>"""
    except Exception as e:
        logger.warning("Could not build items table for order %s: %s", order.order_number, e)
 
    
    shipping_parts = filter(None, [
        order.shipping_name,
        order.shipping_line1,
        order.shipping_line2,
        f"{order.shipping_city} {order.shipping_postcode}".strip(),
        order.shipping_country,
    ])
    shipping_html = "<br/>".join(shipping_parts) or "Not provided"
 
    # Totals
    shipping_label = "Complimentary" if order.shipping_cost == 0 else f"£{order.shipping_cost:.2f}"
 
    tracking_url = f"{site_url}/order/tracking/"
 
    body = f"""
      <h2 style="font-family:Georgia,serif;font-size:28px;font-weight:300;
                 color:#0a0a0a;margin-bottom:8px;">
        Your order is confirmed ✦
      </h2>
      <p style="font-size:13px;color:#888;letter-spacing:.1em;text-transform:uppercase;
                margin-bottom:32px;">Order #{order.order_number}</p>
 
      <p style="color:#4a4a4a;font-size:14px;line-height:1.8;margin-bottom:28px;">
        Hello {to_name},<br/><br/>
        Thank you for your order. We've received your payment and your items are
        now being prepared with care in our studio.
        We'll send you another email when your order ships.
      </p>
 
      <!-- Order Items -->
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
        <thead>
          <tr>
            <th style="font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
                       color:#888;padding-bottom:10px;border-bottom:2px solid #0a0a0a;text-align:left;">
              Item
            </th>
            <th style="font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
                       color:#888;padding-bottom:10px;border-bottom:2px solid #0a0a0a;text-align:center;">
              Qty
            </th>
            <th style="font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
                       color:#888;padding-bottom:10px;border-bottom:2px solid #0a0a0a;text-align:right;">
              Price
            </th>
          </tr>
        </thead>
        <tbody>
          {items_html}
        </tbody>
      </table>
 
      <!-- Totals -->
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr>
          <td style="padding:8px 0;font-size:13px;color:#888;">Subtotal</td>
          <td style="padding:8px 0;font-size:13px;color:#1a1a1a;text-align:right;">£{order.subtotal:.2f}</td>
        </tr>
        <tr>
          <td style="padding:8px 0;font-size:13px;color:#888;">Shipping</td>
          <td style="padding:8px 0;font-size:13px;color:#1a1a1a;text-align:right;">{shipping_label}</td>
        </tr>
        <tr style="border-top:1px solid #e8e8e6;">
          <td style="padding:12px 0 4px;font-size:14px;font-weight:600;color:#0a0a0a;">Total</td>
          <td style="padding:12px 0 4px;font-family:Georgia,serif;font-size:20px;
                     font-weight:400;color:#0a0a0a;text-align:right;">£{order.total:.2f}</td>
        </tr>
      </table>
 
      <!-- Shipping Address -->
      <div style="background:#f2f2f0;border:1px solid #e8e8e6;padding:20px 24px;margin-bottom:32px;">
        <p style="font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;
                  color:#888;margin-bottom:10px;">Shipping To</p>
        <p style="font-size:13px;color:#4a4a4a;line-height:1.7;">{shipping_html}</p>
        <p style="font-size:12px;color:#888;margin-top:8px;">Estimated delivery: 3–5 business days</p>
      </div>
 
      <p style="color:#888;font-size:12px;margin-top:32px;line-height:1.6;">
        Questions? Reply to this email or visit
        <a href="{site_url}/contact/" style="color:#0a0a0a;">{site_url}/contact/</a>
      </p>
    """
 
    return _send(
        to_email,
        to_name,
        f"Order Confirmed — #{order.order_number} | CustomiseMe UK",
        _wrap(body),
    )