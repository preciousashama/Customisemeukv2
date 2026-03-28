





from django.urls import path
from . import views

urlpatterns = [
    path("", views.orderconfirmpage, name='order-page'),
    path("track/", views.ordertrackingpage, name="order-tracking-page"),
    path("confirm/", views.orderconfirmpage,   name="order-confirm-page")
]
