# backend/credit_approval/urls.py
from django.contrib import admin
from django.urls import path, include # <-- Add 'include' here
from rest_framework.authtoken.views import obtain_auth_token # Import this for login token

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')), # <-- Add this line for your core app's URLs
    # You can add a default DRF token endpoint here if you want, but we're handling login custom
    # path('api-token-auth/', obtain_auth_token, name='api_token_auth'),
]