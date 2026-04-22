# musica/urls.py
"""
URLs para la app de musica (API + SEO).
"""
from django.urls import path
from django.views.generic import TemplateView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from musica.views import (
    RegisterView, CustomTokenObtainPairView, UserProfileView,
    UserDetailView, RegisterUserVisit, VerifyUserView,
    UnverifyUserView, ProtectedView, LogoutView,
)

# 🆕 Vistas SEO
from musica.users.views_seo import (
    ArtistDetailSEOView, 
    ArtistListSEOView,
    custom_sitemap_view,
    custom_sitemap_index_view,
    custom_sitemap_static_view,
    custom_sitemap_artists_chunk_view,
)

app_name = 'musica'

urlpatterns = [
    # ============================================
    # API ENDPOINTS
    # ============================================
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair_jwt'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/<int:user_id>/', UserDetailView.as_view(), name='user_detail'),
    path('register-visit/', RegisterUserVisit.as_view(), name='register_visit'),
    path('verify/<int:user_id>/', VerifyUserView.as_view(), name='verify_user'),
    path('unverify/<int:user_id>/', UnverifyUserView.as_view(), name='unverify_user'),
    path('protected/', ProtectedView.as_view(), name='protected'),
    
    # ============================================
    # 🆕 SEO PÚBLICO
    # ============================================
    path('artistas/', ArtistListSEOView.as_view(), name='artist_list_seo'),
    path('perfil/<slug:slug>/', ArtistDetailSEOView.as_view(), name='artist_detail_seo'),
    
    # ============================================
    # 🆕 SITEMAP (VISTA PERSONALIZADA - 100% FUNCIONAL)
    # ============================================
    path('sitemap.xml', custom_sitemap_view, name='sitemap'),
    
    # Opcional: Sitemap indexado para escalar
    path('sitemap-index.xml', custom_sitemap_index_view, name='sitemap_index'),
    path('sitemap-static.xml', custom_sitemap_static_view, name='sitemap_static'),
    path('sitemap-artists-<int:chunk>.xml', custom_sitemap_artists_chunk_view, name='sitemap_artists_chunk'),
    
    # ============================================
    # 🆕 ROBOTS.TXT
    # ============================================
    path('robots.txt', TemplateView.as_view(
        template_name="robots.txt", 
        content_type="text/plain"
    ), name='robots_txt'),
]