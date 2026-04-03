# wallet/admin.py - VERSIÓN PRODUCCIÓN READY
"""
Panel de administración para el sistema wallet.
VERSIÓN PRODUCCIÓN - Con todos los modelos registrados y optimizado.
"""
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse, HttpResponseRedirect
from decimal import Decimal
import csv
import json
from django.db import models

from .models import (
    Wallet, Transaction, Hold, DepositCode, PhysicalLocation, Agent,
    IdempotencyKey, AuditLog, SuspiciousActivity , Office ,OfficeStaff, OfficeWithdrawal, ArtistMuniAccount # ✅ NUEVOS MODELOS
)
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
# FILTROS PERSONALIZADOS
# ============================================================================

class HasPendingBalanceFilter(SimpleListFilter):
    """Filtro para wallets con saldo pendiente"""
    title = 'saldo pendiente'
    parameter_name = 'has_pending'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Con saldo pendiente'),
            ('no', 'Sin saldo pendiente'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(pending_balance__gt=0)
        if self.value() == 'no':
            return queryset.filter(pending_balance=0)
        return queryset


class IsOverdueFilter(SimpleListFilter):
    """Filtro para holds vencidos"""
    title = 'estado vencimiento'
    parameter_name = 'is_overdue'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Vencidos (sin liberar)'),
            ('no', 'No vencidos'),
        )

    def queryset(self, request, queryset):
        from django.db import models  # ✅ O asegurar que models está importado arriba
        if self.value() == 'yes':
            return queryset.filter(
                is_released=False,
                release_date__lt=timezone.now()
            )
        if self.value() == 'no':
            return queryset.filter(
                models.Q(is_released=True) | models.Q(release_date__gte=timezone.now())
            )
        return queryset


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
    list_filter = ['is_active', 'currency', 'created_at', HasPendingBalanceFilter]
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
    list_filter = ['is_released', 'reason', 'release_date', IsOverdueFilter]
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
        """Obtener info de canción desde metadata de la transacción - CORREGIDO"""
        if obj.transaction and obj.transaction.metadata:
            song_id = obj.transaction.metadata.get('song_id')
            song_title = obj.transaction.metadata.get('song_title')
            if song_title:
                return format_html(
                    '<strong>{}</strong><br><small>ID: {}</small>',
                    song_title, song_id
                )
            elif song_id:
                return format_html('<small>ID Canción: {}</small>', song_id)
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
            except Exception as e:
                errors += 1
                self.message_user(request, f'Error en hold {hold.id}: {str(e)}', level='ERROR')

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
            song_info = self.song_info_display(hold)
            # Limpiar HTML tags para CSV
            import re
            song_clean = re.sub(r'<[^>]+>', '', str(song_info)) if song_info else '-'
            
            writer.writerow([
                hold.id,
                hold.artist.username,
                float(hold.amount),
                'Sí' if hold.is_released else 'No',
                hold.release_date.strftime('%Y-%m-%d %H:%M') if hold.release_date else '',
                hold.days_until_release,
                song_clean,
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
    
    # ✅ LISTA (corchetes)
    readonly_fields = ['is_used', 'used_at', 'used_by', 'created_at']
    
    fieldsets = (
        ('Código', {'fields': ('code', 'amount', 'currency')}),
        ('Estado', {'fields': ('is_used', 'used_by', 'used_at', 'expires_at')}),
        ('Auditoría', {
            'fields': ('created_by', 'created_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
    actions = ['mark_as_used', 'extend_expiration', 'generate_bulk_codes']

    def get_readonly_fields(self, request, obj=None):
        if obj:
            # ✅ Convertir a lista y concatenar
            return list(self.readonly_fields) + ['code']
        return self.readonly_fields

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
        from django.http import HttpResponseRedirect
        from decimal import Decimal
        import secrets
        from django.utils import timezone

        if request.method == 'POST':
            amount = Decimal(request.POST.get('amount', 1000))
            quantity = int(request.POST.get('quantity', 10))
            currency = request.POST.get('currency', 'XAF')
            days_valid = int(request.POST.get('days_valid', 30))
            
            codes_created = []
            for _ in range(quantity):
                while True:
                    code = f"{currency}{secrets.token_hex(4).upper()}"
                    if not DepositCode.objects.filter(code=code).exists():
                        break
                
                deposit_code = DepositCode.objects.create(
                    code=code,
                    amount=amount,
                    currency=currency,
                    created_by=request.user,
                    expires_at=timezone.now() + timezone.timedelta(days=days_valid),
                    notes=f"Generado por admin {request.user.username}"
                )
                codes_created.append(deposit_code.code)
            
            messages.success(request, f'{quantity} códigos generados: {", ".join(codes_created[:5])}{"..." if quantity > 5 else ""}')
            return HttpResponseRedirect(request.path_info)

        return render(request, 'admin/generate_codes_form.html', {
            'title': 'Generar códigos en lote',
            'amount_default': 1000,
            'quantity_default': 10,
            'currency_choices': [('XAF', 'XAF'), ('EUR', 'EUR'), ('USD', 'USD')]
        })

# ============================================================================
# IDEMPOTENCY KEY ADMIN (NUEVO)
# ============================================================================

@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    """Administración de claves de idempotencia - SOLO LECTURA"""
    
    list_display = ['key_truncated', 'wallet_link', 'transaction_link', 'created_at']
    list_filter = ['created_at']
    search_fields = ['key', 'wallet__user__email']
    readonly_fields = ['key', 'wallet', 'transaction', 'created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wallet__user', 'transaction')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def key_truncated(self, obj):
        return obj.key[:16] + '...' if len(obj.key) > 16 else obj.key
    key_truncated.short_description = 'Clave (truncada)'
    
    def wallet_link(self, obj):
        if obj.wallet:
            try:
                url = reverse('admin:wallet_wallet_change', args=[obj.wallet.id])
                return format_html('<a href="{}">Wallet #{}</a>', url, obj.wallet.id)
            except Exception:
                return f"Wallet #{obj.wallet.id}"
        return '-'
    wallet_link.short_description = 'Wallet'
    
    def transaction_link(self, obj):
        if obj.transaction:
            try:
                url = reverse('admin:wallet_transaction_change', args=[obj.transaction.id])
                return format_html('<a href="{}">{}</a>', url, obj.transaction.reference)
            except Exception:
                return obj.transaction.reference
        return '-'
    transaction_link.short_description = 'Transacción'


# ============================================================================
# AUDIT LOG ADMIN (NUEVO)
# ============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Administración de logs de auditoría - SOLO LECTURA"""
    
    list_display = ['action', 'user_link', 'entity_type', 'entity_id', 'ip_address', 'created_at']
    list_filter = ['action', 'entity_type', 'created_at']
    search_fields = ['user__email', 'entity_type', 'ip_address']
    readonly_fields = ['user', 'action', 'entity_type', 'entity_id', 'before', 'after', 'ip_address', 'user_agent', 'created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def user_link(self, obj):
        if obj.user:
            try:
                app_label = obj.user._meta.app_label
                model_name = obj.user._meta.model_name
                url = reverse(f'admin:{app_label}_{model_name}_change', args=[obj.user.id])
                return format_html('<a href="{}">{}</a>', url, obj.user.email)
            except Exception:
                return obj.user.email
        return '-'
    user_link.short_description = 'Usuario'
    
    def before_display(self, obj):
        if obj.before:
            return format_html('<pre style="max-height: 100px; overflow: auto;">{}</pre>', json.dumps(obj.before, indent=2))
        return '-'
    before_display.short_description = 'Estado anterior'
    
    def after_display(self, obj):
        if obj.after:
            return format_html('<pre style="max-height: 100px; overflow: auto;">{}</pre>', json.dumps(obj.after, indent=2))
        return '-'
    after_display.short_description = 'Estado posterior'


# ============================================================================
# SUSPICIOUS ACTIVITY ADMIN (NUEVO)
# ============================================================================

@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
    """Administración de actividades sospechosas - SOLO LECTURA"""
    
    list_display = ['user_link', 'activity_type', 'is_reviewed', 'created_at']
    list_filter = ['activity_type', 'is_reviewed', 'created_at']
    search_fields = ['user__email', 'details']
    readonly_fields = ['user', 'wallet', 'activity_type', 'details', 'created_at', 'reviewed_by', 'reviewed_at']
    
    # ✅ NO permitir crear nuevos registros manualmente
    def has_add_permission(self, request):
        return False
    
    # ✅ NO permitir eliminar (opcional, para auditoría)
    def has_delete_permission(self, request, obj=None):
        return False
    
    # ✅ NO permitir modificar (opcional)
    def has_change_permission(self, request, obj=None):
        # Permitir cambiar solo is_reviewed
        return True
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'wallet', 'reviewed_by')
    
    def user_link(self, obj):
        if obj.user:
            try:
                app_label = obj.user._meta.app_label
                model_name = obj.user._meta.model_name
                url = reverse(f'admin:{app_label}_{model_name}_change', args=[obj.user.id])
                return format_html('<a href="{}">{}</a>', url, obj.user.email)
            except Exception:
                return obj.user.email
        return '-'
    user_link.short_description = 'Usuario'
    
    # ✅ Acción para marcar como revisadas
    @admin.action(description='Marcar como revisadas')
    def mark_as_reviewed(self, request, queryset):
        updated = queryset.update(
            is_reviewed=True, 
            reviewed_by=request.user, 
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{updated} actividades marcadas como revisadas')


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


# ============================================================================
# AGENT ADMIN
# ============================================================================

@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    """Administración de agentes"""

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
    fieldsets = (
        ('Información del Agente', {
            'fields': ('user', 'location')  # ✅ Usar campos reales
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

    def user_link(self, obj):
        """Enlace al usuario - SOLO PARA LIST_DISPLAY"""
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
        """Enlace a la ubicación - SOLO PARA LIST_DISPLAY"""
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

# wallet/admin.py - AÑADIR AL FINAL (después de AgentAdmin)

# ============================================================================
# OFFICE ADMIN
# ============================================================================

@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    """Administración de oficinas"""
    
    list_display = ['name', 'city', 'phone', 'is_active', 'daily_cash_limit', 'today_withdrawn_cached', 'created_at']
    list_filter = ['is_active', 'city', 'created_at']
    search_fields = ['name', 'city', 'address', 'phone', 'manager_name']
    readonly_fields = ['created_at', 'updated_at', 'today_withdrawals_total', 'remaining_daily_limit']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'address', 'city', 'phone', 'email')
        }),
        ('Responsable', {
            'fields': ('manager_name',)
        }),
        ('Límites Operativos', {
            'fields': ('daily_cash_limit', 'max_withdrawal_per_artist')
        }),
        ('Estado', {
            'fields': ('is_active',)
        }),
        ('Estadísticas del Día', {
            'fields': ('today_withdrawals_total', 'remaining_daily_limit'),
            'classes': ('collapse',)
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['activate_offices', 'deactivate_offices', 'reset_daily_cache']
    
    def get_queryset(self, request):
        return super().get_queryset(request)
    
    def today_withdrawals_total(self, obj):
        return f"{obj.today_withdrawals_total:,.2f} XAF"
    today_withdrawals_total.short_description = 'Total retirado hoy'
    
    def remaining_daily_limit(self, obj):
        return f"{obj.remaining_daily_limit:,.2f} XAF"
    remaining_daily_limit.short_description = 'Límite restante'
    
    @admin.action(description='Activar oficinas seleccionadas')
    def activate_offices(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} oficinas activadas')
    
    @admin.action(description='Desactivar oficinas seleccionadas')
    def deactivate_offices(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} oficinas desactivadas')
    
    @admin.action(description='Resetear cache diario')
    def reset_daily_cache(self, request, queryset):
        for office in queryset:
            office.reset_daily_cache_if_needed()
        self.message_user(request, f'Cache reseteado para {queryset.count()} oficinas')


@admin.register(OfficeStaff)
class OfficeStaffAdmin(admin.ModelAdmin):
    """Administración de personal de oficina"""
    
    list_display = ['user_link', 'office_link', 'employee_id', 'position', 'is_active', 'today_operations_total_display']
    list_filter = ['is_active', 'office', 'position']
    search_fields = ['user__email', 'user__username', 'employee_id']
    readonly_fields = ['created_at', 'last_activity_at', 'today_operations_total_display']
    
    fieldsets = (
        ('Información del Empleado', {
            'fields': ('user', 'office', 'employee_id', 'position')
        }),
        ('Límites', {
            'fields': ('daily_operation_limit',)
        }),
        ('Estado', {
            'fields': ('is_active',)
        }),
        ('Estadísticas', {
            'fields': ('today_operations_total_display', 'last_activity_at'),
            'classes': ('collapse',)
        }),
        ('Auditoría', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    actions = ['activate_staff', 'deactivate_staff']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'office')
    
    def user_link(self, obj):
        if obj.user:
            try:
                url = reverse(f'admin:{obj.user._meta.app_label}_{obj.user._meta.model_name}_change', args=[obj.user.id])
                return format_html('<a href="{}">{}</a>', url, obj.user.email)
            except Exception:
                return obj.user.email
        return '-'
    user_link.short_description = 'Usuario'
    
    def office_link(self, obj):
        if obj.office:
            try:
                url = reverse('admin:wallet_office_change', args=[obj.office.id])
                return format_html('<a href="{}">{}</a>', url, obj.office.name)
            except Exception:
                return obj.office.name
        return '-'
    office_link.short_description = 'Oficina'
    
    def today_operations_total_display(self, obj):
        return f"{obj.today_operations_total:,.2f} XAF"
    today_operations_total_display.short_description = 'Total operado hoy'
    
    @admin.action(description='Activar personal seleccionado')
    def activate_staff(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} empleados activados')
    
    @admin.action(description='Desactivar personal seleccionado')
    def deactivate_staff(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} empleados desactivados')


@admin.register(OfficeWithdrawal)
class OfficeWithdrawalAdmin(admin.ModelAdmin):
    """Administración de retiros en oficina"""
    
    list_display = ['reference', 'artist_link', 'amount_display', 'withdrawal_method', 'status', 'paid_at']
    list_filter = ['status', 'withdrawal_method', 'paid_at', 'office']
    search_fields = ['reference', 'artist__email', 'artist__username', 'id_number_verified']
    readonly_fields = ['reference', 'requested_at', 'paid_at', 'artist', 'wallet', 'office', 'processed_by']
    
    fieldsets = (
        ('Identificación', {
            'fields': ('reference', 'idempotency_key')
        }),
        ('Artista y Oficina', {
            'fields': ('artist', 'office', 'processed_by')
        }),
        ('Montos', {
            'fields': ('amount', 'fee', 'net_amount')
        }),
        ('Método y Estado', {
            'fields': ('withdrawal_method', 'muni_phone', 'status')
        }),
        ('Verificación', {
            'fields': ('id_number_verified', 'id_type_verified', 'receipt_signed')
        }),
        ('Registro', {
            'fields': ('requested_at', 'paid_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
    actions = ['mark_as_completed', 'mark_as_cancelled', 'export_withdrawals_csv']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('artist', 'office', 'processed_by__user', 'wallet')
    
    def artist_link(self, obj):
        if obj.artist:
            try:
                url = reverse(f'admin:{obj.artist._meta.app_label}_{obj.artist._meta.model_name}_change', args=[obj.artist.id])
                return format_html('<a href="{}">{}</a>', url, obj.artist.email)
            except Exception:
                return obj.artist.email
        return '-'
    artist_link.short_description = 'Artista'
    
    def amount_display(self, obj):
        color = 'green' if obj.status == 'completed' else 'orange'
        return format_html('<span style="color: {}; font-weight: bold;">{:,.2f} XAF</span>', color, float(obj.amount))
    amount_display.short_description = 'Monto'
    
    @admin.action(description='Marcar como completados')
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='completed', paid_at=timezone.now())
        self.message_user(request, f'{updated} retiros marcados como completados')
    
    @admin.action(description='Marcar como cancelados')
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} retiros cancelados')
    
    @admin.action(description='Exportar retiros a CSV')
    def export_withdrawals_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="office_withdrawals_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Referencia', 'Artista', 'Monto', 'Comisión', 'Neto', 'Método', 'Estado', 'Oficina', 'Fecha'])
        
        for w in queryset.select_related('artist', 'office'):
            writer.writerow([
                w.reference,
                w.artist.email,
                float(w.amount),
                float(w.fee),
                float(w.net_amount),
                w.get_withdrawal_method_display(),
                w.get_status_display(),
                w.office.name,
                w.paid_at.strftime('%Y-%m-%d %H:%M') if w.paid_at else ''
            ])
        
        self.message_user(request, f'{queryset.count()} retiros exportados')
        return response


@admin.register(ArtistMuniAccount)
class ArtistMuniAccountAdmin(admin.ModelAdmin):
    """Administración de cuentas Muni Dinero"""
    
    list_display = ['artist_link', 'phone_number', 'is_default', 'is_verified', 'created_at']
    list_filter = ['is_default', 'is_verified', 'created_at']
    search_fields = ['artist__email', 'artist__username', 'phone_number']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Artista', {
            'fields': ('artist',)
        }),
        ('Cuenta Muni', {
            'fields': ('phone_number', 'is_default', 'is_verified', 'verified_at')
        }),
        ('Auditoría', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['mark_as_verified', 'unverify_account']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('artist')
    
    def artist_link(self, obj):
        if obj.artist:
            try:
                url = reverse(f'admin:{obj.artist._meta.app_label}_{obj.artist._meta.model_name}_change', args=[obj.artist.id])
                return format_html('<a href="{}">{}</a>', url, obj.artist.email)
            except Exception:
                return obj.artist.email
        return '-'
    artist_link.short_description = 'Artista'
    
    @admin.action(description='Marcar como verificadas')
    def mark_as_verified(self, request, queryset):
        updated = queryset.update(is_verified=True, verified_at=timezone.now())
        self.message_user(request, f'{updated} cuentas verificadas')
    
    @admin.action(description='Desmarcar verificación')
    def unverify_account(self, request, queryset):
        updated = queryset.update(is_verified=False, verified_at=None)
        self.message_user(request, f'{updated} cuentas desverificadas')