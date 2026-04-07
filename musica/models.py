# users/models.py
"""
Modelos de usuarios para Eco-Music Platform
"""
from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.utils import timezone


class CustomUser(AbstractUser):
    """
    Modelo de usuario personalizado para Eco-Music.
    """
    # --- DATOS PERSONALES ---
    first_name = models.CharField(
        max_length=200, 
        blank=True,
        verbose_name='Nombre'
    )
    last_name = models.CharField(
        max_length=100, 
        blank=True,
        verbose_name='Apellidos'
    )
    email = models.EmailField(
        unique=True,
        verbose_name='Correo electrónico'
    )
    city = models.CharField(
        max_length=100, 
        blank=True,
        verbose_name='Ciudad'
    )
    neighborhood = models.CharField(
        max_length=100, 
        blank=True,
        verbose_name='Barrio'
    )
    phone = models.CharField(
        max_length=15, 
        blank=True,
        verbose_name='Teléfono'
    )
    
    # 🆕 NUEVOS CAMPOS PARA REGISTRO
    GENDER_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Femenino'),
        ('O', 'Otro'),
    ]
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True,
        null=True,
        verbose_name='Género'
    )
    birth_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Fecha de nacimiento'
    )
    terms_accepted = models.BooleanField(
        default=False,
        verbose_name='Términos aceptados'
    )
    terms_accepted_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Fecha de aceptación de términos'
    )
    
    # --- VERIFICACIÓN Y ROLES ---
    is_verified = models.BooleanField(
        default=False,
        help_text="Usuario verificado con badge azul",
        verbose_name='Verificado'
    )
    
    # --- CAMPOS PARA WALLET ---
    # ✅ MODIFICADO: ahora es texto libre, sin choices
    country = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='País',
        help_text='País de residencia (ej: Guinea Ecuatorial, España, etc.)'
    )
    
    can_withdraw = models.BooleanField(
        default=False,
        verbose_name='Puede retirar dinero',
        help_text='Solo usuarios verificados pueden retirar dinero'
    )
    
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de verificación'
    )
    
    # --- PERMISOS DJANGO (sobrescritos para evitar conflictos) ---
    groups = models.ManyToManyField(
        Group, 
        related_name="custom_users", 
        blank=True
    )
    user_permissions = models.ManyToManyField(
        Permission, 
        related_name="custom_users_permissions", 
        blank=True
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['is_verified']),
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        """Auto-setear fecha de aceptación de términos"""
        if self.terms_accepted and not self.terms_accepted_at:
            self.terms_accepted_at = timezone.now()
        super().save(*args, **kwargs)

    # --- PROPIEDADES ÚTILES ---
    @property
    def full_name(self):
        """Nombre completo del usuario"""
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def default_currency(self):
        """Moneda por defecto según país (detección por texto)"""
        country_lower = (self.country or "").lower()
        
        # Detección de países que usan Euro
        euro_countries = ['españa', 'es', 'spain', 'francia', 'france', 
                          'italia', 'italy', 'alemania', 'germany', 
                          'portugal', 'belgica', 'belgium', 'paises bajos', 
                          'netherlands', 'austria', 'grecia', 'greece',
                          'irlanda', 'ireland', 'finlandia', 'finland']
        
        # Detección de países que usan Dólar
        usd_countries = ['estados unidos', 'usa', 'us', 'united states', 
                         'america', 'eeuu', 'ee.uu.']
        
        # Detección de países que usan Franco CFA (XAF)
        xaf_countries = ['guinea ecuatorial', 'guinea', 'ecuatorial', 'gq',
                         'camerún', 'cameroon', 'cm', 'gabón', 'gabon', 'ga',
                         'congo', 'cg', 'chad', 'td', 'republica centroafricana',
                         'república centroafricana', 'cf']
        
        if any(country in country_lower for country in euro_countries):
            return 'EUR'
        elif any(country in country_lower for country in usd_countries):
            return 'USD'
        elif any(country in country_lower for country in xaf_countries):
            return 'XAF'
        else:
            return 'XAF'  # Por defecto Franco CFA

    @property
    def can_receive_payments(self):
        """¿Puede recibir pagos como artista?"""
        return self.is_verified and self.can_withdraw

    # --- MÉTODOS ---
    def verify(self, verified_by=None):
        """Marcar usuario como verificado"""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.can_withdraw = True
        self.save(update_fields=['is_verified', 'verified_at', 'can_withdraw'])
        
    def unverify(self):
        """Quitar verificación"""
        self.is_verified = False
        self.can_withdraw = False
        self.save(update_fields=['is_verified', 'can_withdraw'])


class UserVisit(models.Model):
    """
    Registro de visitas de usuarios para analytics.
    """
    user = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="visitas",
        verbose_name='Usuario'
    )
    ip = models.GenericIPAddressField(
        default='0.0.0.0',
        verbose_name='Dirección IP'
    )
    ciudad = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name='Ciudad'
    )
    region = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name='Región'
    )
    pais = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name='País'
    )
    latitud = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name='Latitud'
    )
    longitud = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        verbose_name='Longitud'
    )
    proveedor = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        verbose_name='Proveedor ISP'
    )
    user_agent = models.TextField(
        blank=True, 
        null=True,
        verbose_name='User Agent'
    )
    navegador = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name='Navegador'
    )
    sistema_operativo = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        verbose_name='Sistema Operativo'
    )
    es_recurrente = models.BooleanField(
        default=False,
        verbose_name='¿Es recurrente?'
    )
    url_referencia = models.URLField(
        blank=True, 
        null=True,
        verbose_name='URL de referencia'
    )
    fecha_visita = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de visita'
    )

    class Meta:
        verbose_name = 'Visita de usuario'
        verbose_name_plural = 'Visitas de usuarios'
        indexes = [
            models.Index(fields=['fecha_visita']),
            models.Index(fields=['pais']),
            models.Index(fields=['user']),
        ]
        ordering = ['-fecha_visita']

    def __str__(self):
        return f"{self.ip} - {self.pais} ({self.ciudad}) - {self.fecha_visita}"