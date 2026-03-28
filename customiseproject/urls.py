from django.contrib import admin
from django.urls import path,include
from customiseapp.views import page_not_found_view


handler404 = page_not_found_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('account/', include('accounts.urls')),
    path('', include('customiseapp.urls')),
    path('orders/', include('orderapp.urls')),
]
