# wallet/filters.py
"""
Filtros para APIs del wallet.
"""
import django_filters
from django_filters import rest_framework as filters
from .models import Transaction, Hold, DepositCode
from .constants import TRANSACTION_TYPES, TRANSACTION_STATUS, HOLD_REASONS, CURRENCIES


class TransactionFilter(filters.FilterSet):
    """
    Filtros para transacciones.
    """
    min_amount = filters.NumberFilter(field_name='amount', lookup_expr='gte')
    max_amount = filters.NumberFilter(field_name='amount', lookup_expr='lte')
    transaction_type = filters.ChoiceFilter(
        choices=TRANSACTION_TYPES,  # Changed from Transaction.TRANSACTION_TYPES
        field_name='transaction_type'
    )
    status = filters.ChoiceFilter(
        choices=TRANSACTION_STATUS,  # Changed from Transaction.TRANSACTION_STATUS
        field_name='status'
    )
    date_from = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    date_to = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    created_by = filters.NumberFilter(field_name='created_by__id', lookup_expr='exact')
    
    class Meta:
        model = Transaction
        fields = ['transaction_type', 'status', 'created_by', 'min_amount', 
                  'max_amount', 'date_from', 'date_to']


class HoldFilter(filters.FilterSet):
    """
    Filtros para retenciones.
    """
    min_amount = filters.NumberFilter(field_name='amount', lookup_expr='gte')
    max_amount = filters.NumberFilter(field_name='amount', lookup_expr='lte')
    is_released = filters.BooleanFilter(field_name='is_released')
    release_date_from = filters.DateFilter(field_name='release_date', lookup_expr='gte')
    release_date_to = filters.DateFilter(field_name='release_date', lookup_expr='lte')
    reason = filters.ChoiceFilter(
        choices=HOLD_REASONS,  # Changed from Hold.HOLD_REASONS
        field_name='reason'
    )
    artist = filters.NumberFilter(field_name='artist__id', lookup_expr='exact')
    
    class Meta:
        model = Hold
        fields = ['is_released', 'reason', 'artist', 'min_amount', 
                  'max_amount', 'release_date_from', 'release_date_to']


class DepositCodeFilter(filters.FilterSet):
    """
    Filtros para códigos de recarga.
    """
    is_used = filters.BooleanFilter(field_name='is_used')
    min_amount = filters.NumberFilter(field_name='amount', lookup_expr='gte')
    max_amount = filters.NumberFilter(field_name='amount', lookup_expr='lte')
    expires_before = filters.DateFilter(field_name='expires_at', lookup_expr='lte')
    expires_after = filters.DateFilter(field_name='expires_at', lookup_expr='gte')
    currency = filters.ChoiceFilter(
        choices=CURRENCIES,  # Added currency filter with choices from constants
        field_name='currency'
    )
    created_by = filters.NumberFilter(field_name='created_by__id', lookup_expr='exact')
    
    class Meta:
        model = DepositCode
        fields = ['is_used', 'currency', 'created_by', 'min_amount', 
                  'max_amount', 'expires_before', 'expires_after']