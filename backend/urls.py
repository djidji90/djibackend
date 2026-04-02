from django.contrib import admin
from django.urls import path, include
from api2.endpoint_inspector import api_home

urlpatterns = [
    path('admin/', admin.site.urls),
    path('musica/', include('musica.urls')),
    path('api2/', include('api2.urls')),
    # path('wallet/', include('wallet.urls')),
   #  path('notifications/', include('notifications.urls')),
    # 👉 raíz personalizada que lista todos los endpoints
    path('', api_home, name='api-home'),
     path('artist/dashboard/', include('artist_dashboard.urls')),
]
