# wallet/pagination.py
"""
Paginación personalizada para APIs del wallet.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class WalletPagination(PageNumberPagination):
    """
    Paginación estándar para transacciones.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('total', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('page_size', self.page_size),
            ('results', data)
        ]))


class TransactionPagination(PageNumberPagination):
    """
    Paginación específica para transacciones (con más metadata).
    """
    page_size = 30
    page_size_query_param = 'limit'
    max_page_size = 200
    
    def get_paginated_response(self, data):
        # Calcular resumen de montos en la página actual
        total_amount = sum(float(item.get('amount', 0)) for item in data)
        
        return Response(OrderedDict([
            ('total', self.page.paginator.count),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('page_size', len(data)),
            ('total_amount_page', round(total_amount, 2)),
            ('results', data)
        ]))


class SmallPagination(PageNumberPagination):
    """
    Paginación pequeña para recursos ligeros.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50# wallet/pagination.py
"""
Paginación personalizada para APIs del wallet.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class WalletPagination(PageNumberPagination):
    """
    Paginación estándar para transacciones.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('total', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('page_size', self.page_size),
            ('results', data)
        ]))


class TransactionPagination(PageNumberPagination):
    """
    Paginación específica para transacciones (con más metadata).
    """
    page_size = 30
    page_size_query_param = 'limit'
    max_page_size = 200
    
    def get_paginated_response(self, data):
        # Calcular resumen de montos en la página actual
        total_amount = sum(float(item.get('amount', 0)) for item in data)
        
        return Response(OrderedDict([
            ('total', self.page.paginator.count),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('page_size', len(data)),
            ('total_amount_page', round(total_amount, 2)),
            ('results', data)
        ]))


class SmallPagination(PageNumberPagination):
    """
    Paginación pequeña para recursos ligeros.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50# wallet/pagination.py
"""
Paginación personalizada para APIs del wallet.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class WalletPagination(PageNumberPagination):
    """
    Paginación estándar para transacciones.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('total', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('page_size', self.page_size),
            ('results', data)
        ]))


class TransactionPagination(PageNumberPagination):
    """
    Paginación específica para transacciones (con más metadata).
    """
    page_size = 30
    page_size_query_param = 'limit'
    max_page_size = 200
    
    def get_paginated_response(self, data):
        # Calcular resumen de montos en la página actual
        total_amount = sum(float(item.get('amount', 0)) for item in data)
        
        return Response(OrderedDict([
            ('total', self.page.paginator.count),
            ('page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('page_size', len(data)),
            ('total_amount_page', round(total_amount, 2)),
            ('results', data)
        ]))


class SmallPagination(PageNumberPagination):
    """
    Paginación pequeña para recursos ligeros.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50