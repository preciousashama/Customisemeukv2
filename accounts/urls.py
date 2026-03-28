from django.urls import path
from . import views
from customiseapp import views as v


urlpatterns = [
    
    path("register/",   views.registerpage,  name="register-page"),
    path("login/",      views.loginpage,     name="login-page"),
    path("logout/",     views.user_logout,   name="logout"),
    path("admin-logout/",     views.admin_logout,   name="admin-logout"),
 
    path("activate/<path:token>/", views.activate_account, name="activate-account"),
 
    # ── Legacy email verification (for resend flow) ──────────────────────────
    path("verify-email/<uuid:token>/", views.verify_email, name="verify-email"),
    path("resend-verification/",       views.resend_verification, name="resend-verification"),
 
    # ── Admin ────────────────────────────────────────────────────────────────
    path("admin-domain-login/", views.admin_login_page,          name="admin-login-page"),
    path("admin-domain/",       views.admin_dashboard_data, name="admin-page"),
 
    # ── Current user / profile ───────────────────────────────────────────────
    path("me/",              views.profilepage,             name="me"),
    path("profile/update/",  views.profile_update, name="profile-update"),
 
    # ── Password management ──────────────────────────────────────────────────
    # path("password/reset/",              views.password_reset_request,  name="password-reset"),
    # path("reset-password/<uuid:token>/", views.password_reset_confirm,  name="password-reset-confirm"),
    path("account/password/change/", views.changepasswordpage, name="password-change"),
 
    # ── Content pages ────────────────────────────────────────────────────────
    path("wishlist/",        views.whishlistpage,   name="wishlist-page"),
    path("workshop/",        views.workshoppage,    name="workshop-page"),
    path("premium-service/", views.premiumpage,     name="premium-page"),
    path("installation/",    views.installationpage,name="installation-page"),
    path("contact-us/",      views.contactpage,     name="contact-page"),


   #from customiseapp app url
    path("design-studio/", v.designstudiopage, name='design-studio-page'),
    path("design-service/", v.designservicepage, name='design-service-page'),
    path("faq/", v.faqpage, name='faq-page'),
    path("subscription/", v.subscriptionpage, name='subscriptions-page'),
    path("privacy/", v.privacypage, name='privacy-page'),
    path("condition/", v.conditionpage, name='conditions-page'),
]