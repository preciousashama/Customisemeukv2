

from django.urls import path
from . import views


urlpatterns = [
    path("",                   views.landing,           name="landing-page"),
    path("home/",             views.homepage,           name="home-page"),
    path("about/",             views.aboutpage,           name="about-page"),
    path("privacy/",           views.privacypage,         name="privacy-page"),
    path("contact/",           views.contactpage,         name="contact-page"),
    path("faq/",               views.faqpage,             name="faq-page"),
    path("conditions/",        views.conditionpage,       name="conditions-page"),
    path("workshop/",          views.workshoppage,        name="workshop-page"),
    path("subscriptions/",     views.subscriptionpage,    name="subscriptions-page"),
    path("send-items/",        views.senditempage,        name="senditems-page"),
    # path("gift/",              views.giftpage,            name="gift-page"),
    path("design-studio/",     views.designstudiopage,    name="design-studio-page"),

    path("shop/",              views.shoppage,            name="shop-page"),
    path("shop/<slug:slug>/",  views.productpage,         name="product-page"),

    path("products/",            views.productpage,  name="product-page"),        
    path("products/<slug:slug>/",views.productpage,  name="product-page-detail"),
 
    path("cart/",              views.cartpage,            name="cart-page"),
    path("cart/checkout/",     views.create_checkout_session, name="checkout"),
    path("stripe/webhook/",    views.stripe_webhook,      name="stripe-webhook"),
 
    path("wishlist/",          views.wishlistpage,        name="wishlist-page"),
 
    path("design-service/",    views.designservicepage,   name="design-service-page"),
    # path('design-studio', views.designstudiopage, name='desgn-studio-page'),

]
