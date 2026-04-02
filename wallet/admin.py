# wallet/admin.py
"""
Panel de administración para el sistema wallet.
Optimizado con gestión de agentes y ubicaciones.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse, HttpResponseRedirect
from decimal import Decimal
import csv
import json

from .models import Wallet, Transaction, Hold, DepositCode, PhysicalLocation, Agent
from .services import WalletService

User = get_user_model()


# ============================================================================
# UTILIDADES COMPARTIDAS
# ============================================================================

def export_to_csv(modeladmin, request, queryset, fields, filename):
    """Utilidad genérica para exportar a CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(fields)
    
    for obj in queryset:
        row = []
        for field in fields:
            value = getattr(obj, field, '')
            if callable(value):
                value = value()
            row.append(str(value))
        writer.writerow(row)
    
    return response


# ============================================================================
# WALLET ADMIN
# ============================================================================

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """Administración de monederos"""
    
    list_display = [
        'id', 'user_email', 'available_balance_display', 
        'pending_balance_display', 'total_balance_display',
        'currency', 'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'currency', 'created_at']
    search_fields = ['user__email', 'user__username', 'user__phone']
    readonly_fields = [
        'available_balance', 'pending_balance', 
        'total_deposited', 'total_spent', 'total_withdrawn',
        'created_at', 'updated_at', 'user_link', 'transactions_link'
    ]
    fieldsets = (
        ('Usuario', {'fields': ('user_link',)}),
        ('Saldos', {
            'fields': (
                ('available_balance', 'pending_balance'),
                ('total_deposited', 'total_spent', 'total_withdrawn'),
            )
        }),
        ('Configuración', {
            'fields': ('currency', 'is_active', 'custom_daily_limit')
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at', 'transactions_link'),
            'classes': ('collapse',)
        }),
    )
    actions = ['activate_wallets', 'deactivate_wallets', 'export_wallets_csv']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    def has_add_permission(self, request):
        return False
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Usuario'
    user_email.admin_order_field = 'user__email'
    
    def user_link(self, obj):
        try:
            app_label = obj.user._meta.app_label
            model_name = obj.user._meta.model_name
            url = reverse(f'admin:{app_label}_{model_name}_change', args=[obj.user.id])
            return format_html('<a href="{}">{} ({})</a>', url, obj.user.email, obj.user.username)
        except Exception:
            return f"{obj.user.email} ({obj.user.username})"
    user_link.short_description = 'Usuario'
    
    def transactions_link(self, obj):
        url = reverse('admin:wallet_transaction_changelist') + f'?wallet__id={obj.id}'
        count = obj.transactions.count()
        return format_html('<a href="{}">Ver {} transacciones</a>', url, count)
    transactions_link.short_description = 'Transacciones'
    
    def _format_balance(self, value, currency, color=None):
        try:
            balance = float(value)
            balance_str = f"{int(balance):,}" if balance == int(balance) else f"{balance:,.2f}"
        except (TypeError, ValueError):
            balance_str = "0"
        
        if color:
            return format_html('<span style="color: {}; font-weight: bold;">{} {}</span>', color, balance_str, currency)
        return f"{balance_str} {currency}"
    
    def available_balance_display(self, obj):
        color = 'green' if obj.available_balance > 0 else 'gray'
        return self._format_balance(obj.available_balance, obj.currency, color)
    available_balance_display.short_description = 'Disponible'
    
    def pending_balance_display(self, obj):
        return self._format_balance(obj.pending_balance, obj.currency, 'orange')
    pending_balance_display.short_description = 'Pendiente'
    
    def total_balance_display(self, obj):
        try:
            total = float(obj.available_balance) + float(obj.pending_balance)
        except (TypeError, ValueError):
            total = 0
        return self._format_balance(total, obj.currency, 'blue')
    total_balance_display.short_description = 'Total'
    
    @admin.action(description='Activar wallets seleccionados')
    def activate_wallets(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} wallets activados')
    
    @admin.action(description='Desactivar wallets seleccionados')
    def deactivate_wallets(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} wallets desactivados')
    
    @admin.action(description='Exportar wallets a CSV')
    def export_wallets_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="wallets_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Usuario', 'Email', 'Disponible', 'Pendiente', 'Total', 'Moneda', 'Activo', 'Creado'])
        
        for wallet in queryset.select_related('user'):
            writer.writerow([
                wallet.id,
                wallet.user.username,
                wallet.user.email,
                float(wallet.available_balance),
                float(wallet.pending_balance),
                float(wallet.available_balance + wallet.pending_balance),
                wallet.currency,
                'Sí' if wallet.is_active else 'No',
                wallet.created_at.strftime('%Y-%m-%d %H:%M')
            ])
        
        self.message_user(request, f'{queryset.count()} wallets exportados')
        return response


# ============================================================================
# TRANSACTION ADMIN
# ============================================================================

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Administración de transacciones"""
    
    list_display = [
        'reference', 'user_email', 'amount_display', 
        'transaction_type', 'status', 'created_at'
    ]
    list_filter = ['transaction_type', 'status', 'created_at']
    search_fields = ['reference', 'wallet__user__email', 'description']
    readonly_fields = [
        'reference', 'wallet', 'amount', 'balance_before', 'balance_after',
        'transaction_type', 'status', 'metadata_json', 'created_at',
        'user_link', 'formatted_balances'
    ]
    fieldsets = (
        ('Identificación', {'fields': ('reference', 'user_link')}),
        ('Montos', {'fields': ('formatted_balances',)}),
        ('Tipo y Estado', {'fields': ('transaction_type', 'status')}),
        ('Metadatos', {
            'fields': ('metadata_json', 'description'),
            'classes': ('collapse',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )
    actions = ['export_transactions_csv']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wallet__user')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def user_email(self, obj):
        return obj.wallet.user.email
    user_email.short_description = 'Usuario'
    user_email.admin_order_field = 'wallet__user__email'
    
    def user_link(self, obj):
        try:
            user = obj.wallet.user
            app_label = user._meta.app_label
            model_name = user._meta.model_name
            url = reverse(f'admin:{app_label}_{model_name}_change', args=[user.id])
            return format_html('<a href="{}">{}</a>', url, user.email)
        except Exception:
            return obj.wallet.user.email
    user_link.short_description = 'Usuario'
    
    def amount_display(self, obj):
        try:
            amount = float(obj.amount)
        except (TypeError, ValueError):
            amount = 0
        color = 'green' if amount >= 0 else 'red'
        sign = '+' if amount >= 0 else ''
        amount_str = f"{amount:,.2f}"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}{} {}</span>',
            color, sign, amount_str, obj.wallet.currency
        )
    amount_display.short_description = 'Monto'
    
    def formatted_balances(self, obj):
        try:
            before = float(obj.balance_before)
            after = float(obj.balance_after)
            diff = after - before
        except (TypeError, ValueError):
            before = after = diff = 0
        return format_html(
            'Saldo anterior: <strong>{:,.2f} {}</strong><br>'
            'Saldo posterior: <strong>{:,.2f} {}</strong><br>'
            'Diferencia: <strong>{:+,.2f} {}</strong>',
            before, obj.wallet.currency,
            after, obj.wallet.currency,
            diff, obj.wallet.currency
        )
    formatted_balances.short_description = 'Balances'
    
    def metadata_json(self, obj):
        if obj.metadata:
            return format_html(
                '<pre style="max-height: 200px; overflow: auto;">{}</pre>',
                json.dumps(obj.metadata, indent=2, default=str)
            )
        return '-'
    metadata_json.short_description = 'Metadatos'
    
    @admin.action(description='Exportar transacciones a CSV')
    def export_transactions_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="transactions_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Referencia', 'Usuario', 'Monto', 'Tipo', 'Estado', 'Saldo Anterior', 'Saldo Posterior', 'Fecha'])
        
        for tx in queryset.select_related('wallet__user'):
            writer.writerow([
                tx.reference,
                tx.wallet.user.username,
                float(tx.amount),
                tx.get_transaction_type_display(),
                tx.get_status_display(),
                float(tx.balance_before),
                float(tx.balance_after),
                tx.created_at.strftime('%Y-%m-%d %H:%M')
            ])
        
        self.message_user(request, f'{queryset.count()} transacciones exportadas')
        return response


# ============================================================================
# HOLD ADMIN
# ============================================================================

@admin.register(Hold)
class HoldAdmin(admin.ModelAdmin):
    """Administración de retenciones"""
    
    list_display = [
        'id', 'artist_email', 'amount_display', 
        'release_date', 'is_released', 'days_left', 'created_at'
    ]
    list_filter = ['is_released', 'reason', 'release_date']
    search_fields = ['artist__email', 'transaction__reference']
    readonly_fields = [
        'transaction', 'artist', 'amount', 'release_date',
        'is_released', 'released_at', 'released_by', 'created_at',
        'song_info_display', 'transaction_link'
    ]
    actions = ['release_holds', 'export_holds_csv']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'artist', 'transaction__wallet__user'
        )
    
    def has_add_permission(self, request):
        return False
    
    def artist_email(self, obj):
        return obj.artist.email
    artist_email.short_description = 'Artista'
    artist_email.admin_order_field = 'artist__email'
    
    def amount_display(self, obj):
        try:
            amount = float(obj.amount)
        except (TypeError, ValueError):
            amount = 0
        color = 'green' if obj.is_released else 'orange'
        amount_str = f"{amount:,.2f}"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} XAF</span>',
            color, amount_str
        )
    amount_display.short_description = 'Monto'
    
    def days_left(self, obj):
        if obj.is_released:
            return 'Liberado'
        days = obj.days_until_release
        if days == 0:
            return 'Hoy'
        if days < 0:
            return 'Vencido'
        return f'{days} días'
    days_left.short_description = 'Estado'
    
    def transaction_link(self, obj):
        url = reverse('admin:wallet_transaction_change', args=[obj.transaction.id])
        return format_html('<a href="{}">{}</a>', url, obj.transaction.reference)
    transaction_link.short_description = 'Transacción'
    
    def song_info_display(self, obj):
        info = obj.song_info
        if info:
            return format_html(
                '<strong>{}</strong> por {}<br><small>ID: {}</small>',
                info['title'], info['artist'], info['id']
            )
        return '-'
    song_info_display.short_description = 'Canción'
    
    @admin.action(description='Liberar holds seleccionados')
    def release_holds(self, request, queryset):
        count = 0
        errors = 0
        skipped = 0
        
        for hold in queryset.filter(is_released=False):
            try:
                if hold.can_release:
                    WalletService.release_hold(hold.id, request.user.id)
                    count += 1
                else:
                    skipped += 1
            except Exception:
                errors += 1
        
        messages = []
        if count:
            messages.append(f'{count} holds liberados')
        if skipped:
            messages.append(f'{skipped} holds no liberables aún')
        if errors:
            messages.append(f'{errors} errores')
        
        self.message_user(request, ' | '.join(messages))
    
    @admin.action(description='Exportar holds a CSV')
    def export_holds_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="holds_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Artista', 'Monto', 'Liberado', 'Fecha Liberación', 'Días Restantes', 'Canción', 'Creado'])
        
        for hold in queryset.select_related('artist'):
            song_info = hold.song_info
            writer.writerow([
                hold.id,
                hold.artist.username,
                float(hold.amount),
                'Sí' if hold.is_released else 'No',
                hold.release_date.strftime('%Y-%m-%d %H:%M') if hold.release_date else '',
                hold.days_until_release,
                song_info['title'] if song_info else '-',
                hold.created_at.strftime('%Y-%m-%d %H:%M')
            ])
        
        self.message_user(request, f'{queryset.count()} holds exportados')
        return response


# ============================================================================
# DEPOSIT CODE ADMIN
# ============================================================================

@admin.register(DepositCode)
class DepositCodeAdmin(admin.ModelAdmin):
    """Administración de códigos de recarga"""
    
    list_display = [
        'code', 'amount_display', 'is_used', 
        'used_by_email', 'expires_at', 'created_at'
    ]
    list_filter = ['is_used', 'currency', 'created_at']
    search_fields = ['code', 'used_by__email']
    readonly_fields = ['is_used', 'used_at', 'used_by', 'created_at', 'code']
    fieldsets = (
        ('Código', {'fields': ('code', 'amount', 'currency')}),
        ('Estado', {'fields': ('is_used', 'used_by', 'used_at', 'expires_at')}),
        ('Auditoría', {
            'fields': ('created_by', 'created_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
    actions = ['mark_as_used', 'extend_expiration', 'generate_bulk_codes']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('used_by', 'created_by')
    
    def amount_display(self, obj):
        try:
            amount = float(obj.amount)
            amount_str = f"{int(amount):,}" if amount == int(amount) else f"{amount:,.2f}"
        except (TypeError, ValueError):
            amount_str = "0"
        return f"{amount_str} {obj.currency}"
    amount_display.short_description = 'Monto'
    
    def used_by_email(self, obj):
        return obj.used_by.email if obj.used_by else '-'
    used_by_email.short_description = 'Usado por'
    
    @admin.action(description='Marcar como usados (manual)')
    def mark_as_used(self, request, queryset):
        updated = queryset.update(
            is_used=True,
            used_at=timezone.now(),
            used_by=request.user
        )
        self.message_user(request, f'{updated} códigos marcados como usados')
    
    @admin.action(description='Extender expiración +30 días')
    def extend_expiration(self, request, queryset):
        for code in queryset:
            code.expires_at += timezone.timedelta(days=30)
            code.save()
        self.message_user(request, f'Expiración extendida para {queryset.count()} códigos')
    
    @admin.action(description='Generar códigos en lote')
    def generate_bulk_codes(self, request, queryset):
        from django.shortcuts import render
        from django.contrib import messages
        
        if request.method == 'POST':
            amount = Decimal(request.POST.get('amount', 1000))
            quantity = int(request.POST.get('quantity', 10))
            currency = request.POST.get('currency', 'XAF')
            days_valid = int(request.POST.get('days_valid', 30))
            
            from django.core.management import call_command
            call_command(
                'generate_deposit_codes',
                amount=amount,
                quantity=quantity,
                currency=currency,
                days=days_valid
            )
            messages.success(request, f'{quantity} códigos generados')
            return HttpResponseRedirect(request.path_info)
        
        return render(request, 'admin/generate_codes_form.html', {
            'title': 'Generar códigos en lote',
            'amount_default': 1000,
            'quantity_default': 10,
            'currency_choices': [('XAF', 'XAF'), ('EUR', 'EUR'), ('USD', 'USD')]
        })


# ============================================================================
# PHYSICAL LOCATION ADMIN
# ============================================================================


@admin.register(PhysicalLocation)
class PhysicalLocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'country', 'phone', 'is_active', 'created_at']
    list_filter = ['country', 'is_active', 'created_at']
    search_fields = ['name', 'address', 'city', 'phone', 'email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'address', 'city', 'country')
        }),
        ('Contacto', {
            'fields': ('phone', 'email')
        }),
        ('Horario y Ubicación', {
            'fields': ('opening_hours', 'coordinates'),
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('is_active',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user_link', 'location_link', 'total_deposits_made',
        'total_amount_deposited_display', 'daily_deposit_limit_display',
        'is_active', 'verified', 'created_at'
    ]
    list_filter = ['is_active', 'verified', 'created_at']
    search_fields = ['user__email', 'user__username', 'notes']
    readonly_fields = [
        'created_at', 'updated_at', 'total_deposits_made',
        'total_amount_deposited', 'user_link', 'location_link',
        'daily_stats_display'
    ]
    
    # ✅ CORREGIDO: Usar campos reales del modelo, no métodos personalizados
    fieldsets = (
        ('Información del Agente', {
            'fields': ('user', 'location')
        }),
        ('Límites Operativos', {
            'fields': ('daily_deposit_limit', 'max_deposit_per_transaction')
        }),
        ('Estadísticas', {
            'fields': ('total_deposits_made', 'total_amount_deposited'),
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('is_active', 'verified', 'verified_at', 'notes')
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['verify_agents', 'activate_agents', 'deactivate_agents']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'location')
    
    # ✅ Métodos personalizados (solo para mostrar en list_display y readonly_fields)
    def user_link(self, obj):
        """Enlace al usuario"""
        if obj.user:
            try:
                app_label = obj.user._meta.app_label
                model_name = obj.user._meta.model_name
                url = reverse(
                    f'admin:{app_label}_{model_name}_change',
                    args=[obj.user.id]
                )
                return format_html(
                    '<a href="{}">{} ({})</a>',
                    url, obj.user.email, obj.user.username
                )
            except Exception:
                return obj.user.email
        return "-"
    user_link.short_description = 'Usuario'
    
    def location_link(self, obj):
        """Enlace a la ubicación"""
        if obj.location:
            try:
                url = reverse('admin:wallet_physicallocation_change', args=[obj.location.id])
                return format_html('<a href="{}">{}</a>', url, obj.location.name)
            except Exception:
                return obj.location.name
        return "Sin ubicación"
    location_link.short_description = 'Ubicación'
    
    def daily_deposit_limit_display(self, obj):
        """Mostrar límite diario formateado"""
        return f"{obj.daily_deposit_limit:,.2f} XAF"
    daily_deposit_limit_display.short_description = 'Límite Diario'
    daily_deposit_limit_display.admin_order_field = 'daily_deposit_limit'
    
    def total_amount_deposited_display(self, obj):
        """Mostrar monto total depositado"""
        return f"{obj.total_amount_deposited:,.2f} XAF"
    total_amount_deposited_display.short_description = 'Total Depositado'
    total_amount_deposited_display.admin_order_field = 'total_amount_deposited'
    
    def daily_stats_display(self, obj):
        """Mostrar estadísticas del día"""
        stats = obj.get_daily_stats()
        return format_html(
            '<strong>Depósitos hoy:</strong> {}<br>'
            '<strong>Total hoy:</strong> {:.2f} XAF<br>'
            '<strong>Límite restante:</strong> {:.2f} XAF<br>'
            '<strong>Límite alcanzado:</strong> {}',
            stats['count'],
            stats['total'],
            stats['remaining'],
            'Sí' if stats['limit_reached'] else 'No'
        )
    daily_stats_display.short_description = 'Estadísticas del Día'
    
    @admin.action(description='Verificar agentes seleccionados')
    def verify_agents(self, request, queryset):
        from django.utils import timezone
        count = 0
        for agent in queryset:
            if not agent.verified:
                agent.verify(verified_by=request.user)
                count += 1
        self.message_user(request, f'{count} agentes verificados')
    
    @admin.action(description='Activar agentes seleccionados')
    def activate_agents(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} agentes activados')
    
    @admin.action(description='Desactivar agentes seleccionados')
    def deactivate_agents(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} agentes desactivados')