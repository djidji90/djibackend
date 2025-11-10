
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
      path('musica/', include('musica.urls')),
       path('api2/', include('api2.urls')),
]

