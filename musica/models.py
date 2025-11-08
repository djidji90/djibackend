from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models

class CustomUser(AbstractUser):
    first_name = models.CharField(max_length=200, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(unique=True)
    city = models.CharField(max_length=100, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    groups = models.ManyToManyField(Group, related_name="custom_users", blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name="custom_users_permissions", blank=True)

    def __str__(self):
        return self.email

class UserVisit(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="visitas")
    ip = models.GenericIPAddressField('0.0.0.0.0')
    ciudad = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    pais = models.CharField(max_length=100, blank=True, null=True)
    latitud = models.CharField(max_length=50, blank=True, null=True)
    longitud = models.CharField(max_length=50, blank=True, null=True)
    proveedor = models.CharField(max_length=200, blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    navegador = models.CharField(max_length=100, blank=True, null=True)
    sistema_operativo = models.CharField(max_length=100, blank=True, null=True)
    es_recurrente = models.BooleanField(default=False)
    url_referencia = models.URLField(blank=True, null=True)
    fecha_visita = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ip} - {self.pais} ({self.ciudad}) - {self.fecha_visita}"


    












    