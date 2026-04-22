# musica/views_api.py
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from .models import CustomUser
from .serializers import PublicArtistSerializer, ArtistProfileSerializer


class StandardResultsPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 100


class PublicArtistListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicArtistSerializer
    pagination_class = StandardResultsPagination
    
    def get_queryset(self):
        return CustomUser.objects.filter(
            is_active=True,
            is_public=True
        ).order_by('-is_verified', '-date_joined')


class PublicArtistDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicArtistSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'
    
    def get_queryset(self):
        return CustomUser.objects.filter(is_active=True, is_public=True)


class ArtistProfileDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ArtistProfileSerializer
    lookup_field = 'slug'
    lookup_url_kwarg = 'slug'
    
    def get_queryset(self):
        return CustomUser.objects.filter(is_active=True, is_public=True)