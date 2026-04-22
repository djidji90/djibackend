# musica/views_seo.py
"""
Vistas SEO para renderizado HTML de perfiles públicos.
Googlebot y redes sociales usarán estas vistas para indexar contenido.
"""
from django.views.generic import DetailView, ListView
from django.http import HttpResponse, Http404
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from musica.models import CustomUser
import json


# ============================================
# 🔄 REDIRECCIÓN DE URLs ANTIGUAS (301)
# ============================================

def redirect_legacy_profile(request, identifier):
    """
    Redirige URLs antiguas al nuevo formato con slug.
    Soporta:
    - /perfil/username/   → /perfil/slug/
    - /perfil/id/         → /perfil/slug/
    
    Usa redirección 301 (permanente) para que Google actualice su índice.
    """
    try:
        # Intentar buscar por ID (si identifier es numérico)
        if identifier.isdigit():
            user = get_object_or_404(CustomUser, id=int(identifier), is_public=True)
        else:
            # Intentar buscar por username
            user = get_object_or_404(CustomUser, username=identifier, is_public=True)
        
        # Redirección 301 a la URL canónica con slug
        return redirect(user.get_absolute_url(), permanent=True)
        
    except (ValueError, Http404):
        # Si no se encuentra, devolver 404
        raise Http404("Artista no encontrado")


# ============================================
# 🎨 VISTAS SEO PRINCIPALES
# ============================================

class ArtistDetailSEOView(DetailView):
    """
    Vista HTML para Googlebot y Redes Sociales.
    URL: /perfil/<slug>/
    
    Renderiza contenido estático que los crawlers pueden leer sin JavaScript.
    """
    model = CustomUser
    template_name = "seo/artist_detail.html"
    context_object_name = "artist"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        # Solo mostramos perfiles activos y públicos
        return CustomUser.objects.filter(
            is_active=True, 
            is_public=True
        ).select_related()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        artist = self.object

        # Construir JSON-LD para Schema.org (Rich Snippets)
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": artist.full_name,
            "url": self.request.build_absolute_uri(artist.get_absolute_url()),
            "description": f"Artista en DjidjiMusic. {artist.city or ''}",
            "memberOf": {
                "@type": "Organization",
                "name": "DjidjiMusic",
                "url": self.request.build_absolute_uri('/')
            }
        }

        # Añadir imagen si existe
        if hasattr(artist, 'profile_image') and artist.profile_image:
            json_ld["image"] = self.request.build_absolute_uri(artist.profile_image.url)

        context['page_title'] = f"{artist.full_name} | DjidjiMusic"
        context['meta_description'] = f"Escucha la música de {artist.full_name} en DjidjiMusic. {artist.city or ''}"
        context['json_ld'] = json.dumps(json_ld, ensure_ascii=False)

        # Enlace a la App SPA (para humanos)
        context['spa_profile_url'] = f"/#/perfil/{artist.slug}/"

        return context


class ArtistListSEOView(ListView):
    """
    Listado público de artistas para descubrimiento.
    URL: /artistas/
    
    Página de descubrimiento que Google puede rastrear para encontrar perfiles.
    """
    model = CustomUser
    template_name = "seo/artist_list.html"
    context_object_name = "artists"
    paginate_by = 50

    def get_queryset(self):
        return CustomUser.objects.filter(
            is_active=True, 
            is_public=True
        ).order_by('-date_joined')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # JSON-LD para la página de listado
        json_ld = {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "Artistas en DjidjiMusic",
            "description": "Descubre artistas independientes en DjidjiMusic",
            "url": self.request.build_absolute_uri('/artistas/'),
            "numberOfItems": self.get_queryset().count()
        }

        context['json_ld'] = json.dumps(json_ld, ensure_ascii=False)
        context['page_title'] = "Artistas en DjidjiMusic | Descubre nuevo talento"
        context['meta_description'] = "Explora todos los artistas verificados en DjidjiMusic. Encuentra tu próximo sonido favorito."

        return context


# ============================================
# 🗺️ VISTA PERSONALIZADA DE SITEMAP (100% FUNCIONAL)
# ============================================

def custom_sitemap_view(request):
    """
    Vista personalizada para sitemap que NO usa templates.
    Genera XML directamente y es compatible con Google Search Console.
    """
    # Obtener dominio base
    protocol = 'https' if request.is_secure() else 'http'
    domain = f"{protocol}://{request.get_host()}"

    # Construir XML
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # 1. Página de inicio
    xml_lines.append('  <url>')
    xml_lines.append(f'    <loc>{domain}/</loc>')
    xml_lines.append('    <changefreq>daily</changefreq>')
    xml_lines.append('    <priority>1.0</priority>')
    xml_lines.append('  </url>')

    # 2. Página de artistas (listado)
    xml_lines.append('  <url>')
    xml_lines.append(f'    <loc>{domain}/musica/artistas/</loc>')
    xml_lines.append('    <changefreq>daily</changefreq>')
    xml_lines.append('    <priority>0.9</priority>')
    xml_lines.append('  </url>')

    # 3. Perfiles de artistas públicos
    public_artists = CustomUser.objects.filter(
        is_active=True, 
        is_public=True
    ).exclude(slug='')

    for artist in public_artists:
        url = f"{domain}/musica/perfil/{artist.slug}/"
        xml_lines.append('  <url>')
        xml_lines.append(f'    <loc>{url}</loc>')
        xml_lines.append('    <changefreq>weekly</changefreq>')
        xml_lines.append('    <priority>0.8</priority>')
        if artist.updated_at:
            xml_lines.append(f'    <lastmod>{artist.updated_at.date().isoformat()}</lastmod>')
        xml_lines.append('  </url>')

    xml_lines.append('</urlset>')

    # Devolver como XML
    return HttpResponse('\n'.join(xml_lines), content_type='application/xml')


# ============================================
# 📊 SITEMAP INDEXADO (PARA MILLONES DE PERFILES)
# ============================================

def custom_sitemap_index_view(request):
    """
    Sitemap indexado para escalar a millones de perfiles.
    Divide el sitemap en chunks de 1000 URLs.
    """
    protocol = 'https' if request.is_secure() else 'http'
    domain = f"{protocol}://{request.get_host()}"

    # Contar total de artistas públicos
    total_artists = CustomUser.objects.filter(
        is_active=True, 
        is_public=True
    ).exclude(slug='').count()

    # Calcular número de chunks (1000 por archivo)
    chunk_size = 1000
    num_chunks = (total_artists // chunk_size) + (1 if total_artists % chunk_size > 0 else 0)

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # Añadir sitemap de páginas estáticas
    xml_lines.append('  <sitemap>')
    xml_lines.append(f'    <loc>{domain}/musica/sitemap-static.xml</loc>')
    xml_lines.append('  </sitemap>')

    # Añadir sitemaps de artistas (chunks)
    for i in range(num_chunks):
        xml_lines.append('  <sitemap>')
        xml_lines.append(f'    <loc>{domain}/musica/sitemap-artists-{i}.xml</loc>')
        xml_lines.append('  </sitemap>')

    xml_lines.append('</sitemapindex>')

    return HttpResponse('\n'.join(xml_lines), content_type='application/xml')


def custom_sitemap_static_view(request):
    """
    Sitemap para páginas estáticas.
    """
    protocol = 'https' if request.is_secure() else 'http'
    domain = f"{protocol}://{request.get_host()}"

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # Páginas estáticas
    static_urls = [
        ('/', 'daily', '1.0'),
        ('/musica/artistas/', 'daily', '0.9'),
    ]

    for url, freq, priority in static_urls:
        xml_lines.append('  <url>')
        xml_lines.append(f'    <loc>{domain}{url}</loc>')
        xml_lines.append(f'    <changefreq>{freq}</changefreq>')
        xml_lines.append(f'    <priority>{priority}</priority>')
        xml_lines.append('  </url>')

    xml_lines.append('</urlset>')

    return HttpResponse('\n'.join(xml_lines), content_type='application/xml')


def custom_sitemap_artists_chunk_view(request, chunk):
    """
    Sitemap para un chunk específico de artistas.
    """
    protocol = 'https' if request.is_secure() else 'http'
    domain = f"{protocol}://{request.get_host()}"

    chunk_size = 1000
    offset = int(chunk) * chunk_size

    artists = CustomUser.objects.filter(
        is_active=True, 
        is_public=True
    ).exclude(slug='').order_by('id')[offset:offset + chunk_size]

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for artist in artists:
        xml_lines.append('  <url>')
        xml_lines.append(f'    <loc>{domain}/musica/perfil/{artist.slug}/</loc>')
        xml_lines.append('    <changefreq>weekly</changefreq>')
        xml_lines.append('    <priority>0.8</priority>')
        if artist.updated_at:
            xml_lines.append(f'    <lastmod>{artist.updated_at.date().isoformat()}</lastmod>')
        xml_lines.append('  </url>')

    xml_lines.append('</urlset>')

    return HttpResponse('\n'.join(xml_lines), content_type='application/xml')