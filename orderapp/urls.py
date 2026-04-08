





from django.urls import path
from . import views

urlpatterns = [
    path("confirm/", views.orderconfirmpage, name='order-page'),
    path("track/", views.ordertrackingpage, name="order-tracking-page"),
    # path("debug/email-test/", views.email_debug_view, name="email-debug"),
]
