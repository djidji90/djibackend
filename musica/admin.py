# musica/admin.py
"""
Panel de administración para la app de usuarios.
Incluye gestión de CustomUser con campos de wallet, SEO y UserVisit.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import reverse
from .models import UserVisit

User = get_user_model()


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Administración personalizada para CustomUser con campos de wallet y SEO.
    """
    # --- LISTADO PRINCIPAL (CORREGIDO - Incluye todos los campos editables) ---
    list_display = [
        'id', 
        'username', 
        'email', 
        'first_name', 
        'last_name', 
        'city', 
        'neighborhood', 
        'phone',
        'country',
        'default_currency_display',
        'is_verified_display',
        'can_withdraw_display',
        'is_public_display',
        'is_verified',
        'can_withdraw',
        'is_public',
        'is_active', 
        'is_staff',
    ]
    
    list_editable = ('is_verified', 'can_withdraw', 'is_public', 'is_active')
    
    search_fields = (
        'username', 'email', 'first_name', 'last_name', 
        'city', 'neighborhood', 'phone', 'country', 'slug'
    )
    
    list_filter = (
        'is_active', 
        'is_staff', 
        'city', 
        'neighborhood',
        'country',
        'is_verified',
        'can_withdraw',
        'is_public',
    )
    
    # --- CAMPOS EDITABLES DIRECTAMENTE EN LISTADO (CORREGIDO) ---
    # Ahora todos estos campos están en list_display
    list_editable = ('is_verified', 'can_withdraw', 'is_public', 'is_active')
    
    # --- ORDENACIÓN ---
    ordering = ('-is_verified', '-date_joined', 'username')
    
    # --- CAMPOS A MOSTRAR EN EL FORMULARIO DE EDICIÓN ---
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        
        ('Información Personal', {
            'fields': (
                'first_name', 'last_name', 'email', 
                'phone', 'city', 'neighborhood', 'country',
                'gender', 'birth_date'
            )
        }),
        
        # 🆕 SECCIÓN SEO
        ('SEO y Visibilidad', {
            'fields': (
                'slug', 
                'is_public',
                'updated_at',
            ),
            'classes': ('wide',),
            'description': 'Configuración para buscadores. El slug define la URL pública del perfil.'
        }),
        
        ('Verificación y Wallet', {
            'fields': (
                'is_verified', 
                'can_withdraw', 
                'verified_at',
            ),
            'classes': ('wide',),
            'description': 'Gestión de verificación del usuario y permisos de wallet'
        }),
        
        ('Permisos', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        
        ('Fechas importantes', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    # --- CAMPOS DE SOLO LECTURA ---
    readonly_fields = ('verified_at', 'updated_at', 'date_joined', 'last_login')
    
    # --- ACCIONES PERSONALIZADAS ---
    actions = [
        'verify_users', 
        'unverify_users', 
        'enable_withdraw', 
        'disable_withdraw',
        'make_public',
        'make_private',
    ]
    
    # ==================== MÉTODOS DE VISUALIZACIÓN ====================
    
    def default_currency_display(self, obj):
        """Mostrar moneda por defecto con formato bonito"""
        currency = obj.default_currency
        colors = {
            'XAF': 'orange',
            'EUR': 'blue',
            'USD': 'green',
        }
        color = colors.get(currency, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, currency
        )
    default_currency_display.short_description = 'Moneda'
    default_currency_display.admin_order_field = 'country'
    
    def is_verified_display(self, obj):
        """Mostrar badge de verificación con color"""
        if obj.is_verified:
            return format_html(
                '<span style="color: green; font-weight: bold;">✅ Verificado</span>'
            )
        return format_html(
            '<span style="color: orange; font-weight: bold;">⏳ No verificado</span>'
        )
    is_verified_display.short_description = 'Verificación'
    is_verified_display.admin_order_field = 'is_verified'
    
    def can_withdraw_display(self, obj):
        """Mostrar si puede retirar dinero"""
        if obj.can_withdraw:
            return format_html(
                '<span style="color: green;">💰 Sí</span>'
            )
        return format_html(
            '<span style="color: gray;">❌ No</span>'
        )
    can_withdraw_display.short_description = 'Puede retirar'
    can_withdraw_display.admin_order_field = 'can_withdraw'
    
    def is_public_display(self, obj):
        """Mostrar estado de visibilidad pública para SEO"""
        if obj.is_public:
            return format_html(
                '<span style="color: green;">🌐 Público</span>'
            )
        return format_html(
            '<span style="color: gray;">🔒 Privado</span>'
        )
    is_public_display.short_description = 'Visibilidad'
    is_public_display.admin_order_field = 'is_public'
    
    def profile_url_display(self, obj):
        """Mostrar URL pública del perfil"""
        if obj.slug:
            url = obj.get_absolute_url()
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url, url
            )
        return format_html('<span style="color: gray;">Sin slug</span>')
    profile_url_display.short_description = 'URL Pública'
    
    def get_wallet_link(self, obj):
        """Link al wallet del usuario (si existe)"""
        try:
            wallet = obj.wallet
            url = reverse('admin:wallet_wallet_change', args=[wallet.id])
            return format_html(
                '<a href="{}">Ver wallet ({} {})</a>',
                url, wallet.available_balance, wallet.currency
            )
        except:
            return format_html('<span style="color: gray;">Sin wallet</span>')
    get_wallet_link.short_description = 'Wallet'
    
    def get_transactions_count(self, obj):
        """Contar transacciones del usuario"""
        try:
            count = obj.wallet.transactions.count()
            url = reverse('admin:wallet_transaction_changelist') + f'?wallet__user__id={obj.id}'
            return format_html('<a href="{}">{} transacciones</a>', url, count)
        except:
            return '0'
    get_transactions_count.short_description = 'Transacciones'
    
    def get_holds_count(self, obj):
        """Contar holds pendientes del usuario como artista"""
        try:
            from wallet.models import Hold
            count = Hold.objects.filter(artist=obj, is_released=False).count()
            if count > 0:
                url = reverse('admin:wallet_hold_changelist') + f'?artist__id={obj.id}&is_released__exact=0'
                return format_html(
                    '<a href="{}" style="color: orange;">{} pendientes</a>',
                    url, count
                )
            return '0'
        except:
            return '0'
    get_holds_count.short_description = 'Holds pendientes'
    
    # ==================== ACCIONES PERSONALIZADAS ====================
    
    @admin.action(description='✅ Verificar usuarios seleccionados')
    def verify_users(self, request, queryset):
        """Acción para verificar múltiples usuarios"""
        count = 0
        for user in queryset:
            if not user.is_verified:
                user.verify()
                count += 1
        self.message_user(request, f'{count} usuarios verificados exitosamente.')
    
    @admin.action(description='❌ Desmarcar verificación de usuarios')
    def unverify_users(self, request, queryset):
        """Acción para quitar verificación de usuarios"""
        count = 0
        for user in queryset:
            if user.is_verified:
                user.unverify()
                count += 1
        self.message_user(request, f'Verificación removida para {count} usuarios.')
    
    @admin.action(description='💰 Habilitar retiros para usuarios')
    def enable_withdraw(self, request, queryset):
        """Habilitar retiros para usuarios seleccionados"""
        count = 0
        for user in queryset:
            if not user.can_withdraw:
                user.can_withdraw = True
                user.save(update_fields=['can_withdraw', 'updated_at'])
                count += 1
        self.message_user(request, f'Retiros habilitados para {count} usuarios.')
    
    @admin.action(description='🔒 Deshabilitar retiros para usuarios')
    def disable_withdraw(self, request, queryset):
        """Deshabilitar retiros para usuarios seleccionados"""
        count = 0
        for user in queryset:
            if user.can_withdraw:
                user.can_withdraw = False
                user.save(update_fields=['can_withdraw', 'updated_at'])
                count += 1
        self.message_user(request, f'Retiros deshabilitados para {count} usuarios.')
    
    @admin.action(description='🌐 Hacer perfiles públicos (indexables)')
    def make_public(self, request, queryset):
        """Hacer perfiles visibles para buscadores"""
        count = 0
        for user in queryset:
            if not user.is_public:
                user.is_public = True
                user.save(update_fields=['is_public', 'updated_at'])
                count += 1
        self.message_user(request, f'{count} perfiles ahora son públicos.')
    
    @admin.action(description='🔒 Hacer perfiles privados (no indexables)')
    def make_private(self, request, queryset):
        """Ocultar perfiles de buscadores"""
        count = 0
        for user in queryset:
            if user.is_public:
                user.is_public = False
                user.save(update_fields=['is_public', 'updated_at'])
                count += 1
        self.message_user(request, f'{count} perfiles ahora son privados.')
    
    # ==================== MÉTODOS PARA INCLUIR EN EL FORMULARIO ====================
    
    def get_fieldsets(self, request, obj=None):
        """Personalizar fieldsets para usuarios existentes vs nuevos"""
        fieldsets = super().get_fieldsets(request, obj)
        
        if obj:  # Usuario existente
            # Agregar sección de wallet
            wallet_section = (
                'Información de Wallet', {
                    'fields': ('get_wallet_link', 'get_transactions_count', 'get_holds_count'),
                    'classes': ('collapse',),
                    'description': 'Información financiera del usuario'
                }
            )
            # Agregar sección de SEO (información adicional)
            seo_info_section = (
                'Información SEO', {
                    'fields': ('profile_url_display',),
                    'classes': ('collapse',),
                    'description': 'URL pública del perfil para buscadores'
                }
            )
            # Insertar después de la sección de Verificación
            fieldsets = list(fieldsets)
            fieldsets.insert(4, wallet_section)
            fieldsets.insert(5, seo_info_section)
        
        return fieldsets
    
    def get_readonly_fields(self, request, obj=None):
        """Slug solo editable al crear, después es solo lectura"""
        readonly = super().get_readonly_fields(request, obj)
        if obj:  # Si es edición (no creación)
            readonly = list(readonly) + [
                'slug',
                'get_wallet_link', 
                'get_transactions_count', 
                'get_holds_count',
                'profile_url_display',
            ]
        return readonly


@admin.register(UserVisit)
class UserVisitAdmin(admin.ModelAdmin):
    """
    Administración para visitas de usuarios.
    """
    list_display = (
        'ip', 
        'user_link', 
        'ciudad', 
        'region', 
        'pais', 
        'proveedor', 
        'navegador', 
        'sistema_operativo', 
        'es_recurrente',
        'fecha_visita'
    )
    
    search_fields = (
        'ip', 'ciudad', 'region', 'pais', 'proveedor', 
        'navegador', 'sistema_operativo', 'user__email', 'user__username'
    )
    
    list_filter = (
        'es_recurrente', 
        'pais', 
        'region', 
        'navegador', 
        'sistema_operativo',
        'fecha_visita'
    )
    
    readonly_fields = (
        'user', 'ip', 'ciudad', 'region', 'pais', 'latitud', 'longitud',
        'proveedor', 'user_agent', 'navegador', 'sistema_operativo',
        'es_recurrente', 'url_referencia', 'fecha_visita'
    )
    
    fieldsets = (
        ('Información de Ubicación', {
            'fields': ('ip', 'ciudad', 'region', 'pais', 'latitud', 'longitud')
        }),
        ('Información de Conexión', {
            'fields': ('proveedor', 'user_agent', 'navegador', 'sistema_operativo')
        }),
        ('Información de Visita', {
            'fields': ('user', 'es_recurrente', 'url_referencia', 'fecha_visita')
        }),
    )
    
    ordering = ('-fecha_visita',)
    date_hierarchy = 'fecha_visita'
    
    def user_link(self, obj):
        """Link al usuario asociado"""
        if obj.user:
            url = reverse('admin:musica_customuser_change', args=[obj.user.id])
            return format_html(
                '<a href="{}">{}</a>',
                url, obj.user.email
            )
        return 'Anónimo'
    user_link.short_description = 'Usuario'
    user_link.admin_order_field = 'user__email'
    
    def get_queryset(self, request):
        """Optimizar consulta con select_related"""
        return super().get_queryset(request).select_related('user')