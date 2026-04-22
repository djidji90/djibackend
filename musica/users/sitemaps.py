# musica/sitemaps.py
"""
Sitemaps dinámicos para SEO.
Genera sitemaps indexados automáticamente para escalar a millones de perfiles.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from musica.models import CustomUser


class ArtistSitemap(Sitemap):
    """
    Sitemap para perfiles de artistas.
    Se divide automáticamente en chunks de 1000 URLs.
    """
    changefreq = "weekly"
    priority = 0.8
    protocol = "https"
    limit = 1000
    
    def items(self):
        return CustomUser.objects.filter(
            is_active=True, 
            is_public=True
        ).order_by('id')
    
    def lastmod(self, obj):
        return obj.updated_at
    
    def location(self, obj):
        return obj.get_absolute_url()


class StaticViewSitemap(Sitemap):
    """
    Sitemap para páginas estáticas importantes.
    """
    priority = 0.5
    changefreq = "monthly"
    protocol = "https"

    def items(self):
        return ['artist_list_seo']
    
    def location(self, item):
        return reverse(f'musica:{item}')  # ← CORREGIDO: musica, no users, y sin coma