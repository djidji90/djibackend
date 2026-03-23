# pagination.py
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class CommentPagination(PageNumberPagination):
    page_size = 10  # Aumentado de 3 a 10
    page_size_query_param = 'page_size'
    max_page_size = 50
    
    def get_paginated_response(self, data):
        """Respuesta paginada con metadata útil"""
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'page_size': self.get_page_size(self.request),
            'results': data
        })