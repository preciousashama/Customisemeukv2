





from django.urls import path
from . import views

urlpatterns = [
    path("confirm/", views.orderconfirmpage, name='order-page'),
    path("track/", views.ordertrackingpage, name="order-tracking-page")
]
