from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import UserVisit

User = get_user_model()

@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['id', 'username', 'email', 'first_name', 'last_name', 'city', 'neighborhood', 'phone', 'is_active', 'is_staff']
    search_fields = ('username', 'email', 'first_name', 'last_name', 'city', 'neighborhood', 'phone')
    list_filter = ('is_active', 'is_staff', 'city', 'neighborhood')

@admin.register(UserVisit)
class UserVisitAdmin(admin.ModelAdmin):
    list_display = ('ip', 'ciudad', 'region', 'pais', 'proveedor', 'navegador', 'sistema_operativo', 'fecha_visita', 'es_recurrente')
    search_fields = ('ip', 'ciudad', 'region', 'pais', 'proveedor', 'navegador', 'sistema_operativo')
    list_filter = ('es_recurrente', 'pais', 'region', 'navegador', 'sistema_operativo')
