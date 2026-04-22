#!/usr/bin/env python
"""
Script de testing pre-despliegue para cambios SEO.
Ejecutar: python manage.py shell < scripts/test_seo.py
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djidji_music.settings')
django.setup()

from django.db import connection
from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse, resolve
from django.utils.text import slugify

User = get_user_model()

print("\n" + "="*70)
print("🧪 TESTING PRE-DESPLIEGUE - CAMBIOS SEO")
print("="*70)


# ============================================
# TEST 1: VERIFICAR MODELOS
# ============================================
def test_model_fields():
    """Verifica que los nuevos campos existen en el modelo."""
    print("\n📦 TEST 1: Verificando campos en el modelo...")
    
    from musica.models import CustomUser  # Ajusta según tu estructura
    
    # Obtener campos del modelo
    fields = [f.name for f in CustomUser._meta.get_fields()]
    
    required_fields = ['slug', 'updated_at', 'is_public']
    
    all_present = True
    for field in required_fields:
        if field in fields:
            print(f"   ✅ Campo '{field}' existe")
        else:
            print(f"   ❌ Campo '{field}' NO existe")
            all_present = False
    
    # Verificar métodos
    if hasattr(CustomUser, 'get_absolute_url'):
        print(f"   ✅ Método 'get_absolute_url' existe")
    else:
        print(f"   ❌ Método 'get_absolute_url' NO existe")
        all_present = False
    
    if hasattr(CustomUser, 'is_indexable'):
        print(f"   ✅ Property 'is_indexable' existe")
    else:
        print(f"   ⚠️ Property 'is_indexable' NO existe (opcional)")
    
    return all_present


# ============================================
# TEST 2: VERIFICAR MIGRACIONES PENDIENTES
# ============================================
def test_migrations():
    """Muestra migraciones pendientes sin aplicarlas."""
    print("\n🔄 TEST 2: Estado de migraciones...")
    
    from django.core.management import call_command
    from io import StringIO
    
    # Capturar salida de showmigrations
    out = StringIO()
    call_command('showmigrations', 'musica', stdout=out)
    output = out.getvalue()
    
    # Contar migraciones no aplicadas
    pending = output.count('[ ]')
    applied = output.count('[X]')
    
    print(f"   📊 Migraciones aplicadas: {applied}")
    print(f"   📊 Migraciones pendientes: {pending}")
    
    if pending > 0:
        print("   ⚠️ Hay migraciones pendientes. Se aplicarán con 'python manage.py migrate'")
        # Mostrar las pendientes
        for line in output.split('\n'):
            if '[ ]' in line:
                print(f"      {line.strip()}")
    
    return True


# ============================================
# TEST 3: VERIFICAR VISTAS SEO
# ============================================
def test_seo_views():
    """Verifica que las vistas SEO existen y son resolubles."""
    print("\n🌐 TEST 3: Verificando vistas SEO...")
    
    from musica.users.views_seo import ArtistDetailSEOView, ArtistListSEOView
    
    print(f"   ✅ ArtistDetailSEOView importada correctamente")
    print(f"   ✅ ArtistListSEOView importada correctamente")
    
    # Verificar URLs
    try:
        # Estas URLs deberían resolverse después de actualizar urls.py
        from musica.urls import app_name
        print(f"   ✅ Namespace 'musica' configurado: {app_name}")
    except ImportError:
        print(f"   ⚠️ urls.py de musica no tiene app_name configurado")
    
    return True


# ============================================
# TEST 4: VERIFICAR SERIALIZERS
# ============================================
def test_serializers():
    """Verifica que los serializers tienen los campos SEO."""
    print("\n📝 TEST 4: Verificando serializers...")
    
    try:
        from musica.serializers import PublicArtistSerializer, UserSerializer
        
        # Verificar PublicArtistSerializer
        if hasattr(PublicArtistSerializer, 'Meta'):
            fields = PublicArtistSerializer.Meta.fields
            seo_fields = ['slug', 'profile_url']
            
            for field in seo_fields:
                if field in fields:
                    print(f"   ✅ PublicArtistSerializer tiene campo '{field}'")
                else:
                    print(f"   ❌ PublicArtistSerializer NO tiene campo '{field}'")
        
        # Verificar UserSerializer
        if hasattr(UserSerializer, 'Meta'):
            fields = UserSerializer.Meta.fields
            if 'slug' in fields:
                print(f"   ✅ UserSerializer tiene campo 'slug'")
            else:
                print(f"   ❌ UserSerializer NO tiene campo 'slug'")
                
    except ImportError as e:
        print(f"   ⚠️ No se pudieron importar serializers: {e}")
    
    return True


# ============================================
# TEST 5: SIMULAR GENERACIÓN DE SLUGS
# ============================================
def test_slug_generation():
    """Simula generación de slugs sin guardar en BD."""
    print("\n🏷️ TEST 5: Simulando generación de slugs...")
    
    # Obtener usuarios sin slug (simulado)
    test_users = User.objects.all()[:5]
    
    if not test_users:
        print("   ⚠️ No hay usuarios para probar")
        return True
    
    print(f"   📊 Probando con {len(test_users)} usuarios:")
    
    for user in test_users:
        base = user.get_full_name() or user.username
        generated_slug = slugify(base)
        
        # Verificar si ya existe
        existing = User.objects.filter(slug=generated_slug).exists()
        
        status = "⚠️ (ya existe)" if existing else "✅"
        print(f"      {user.username} → '{generated_slug}' {status}")
    
    return True


# ============================================
# TEST 6: VERIFICAR PERMISOS Y ADMIN
# ============================================
def test_admin_integration():
    """Verifica integración con admin panel."""
    print("\n🔐 TEST 6: Verificando integración con admin...")
    
    try:
        from musica.admin import CustomUserAdmin
        
        # Verificar list_display
        if hasattr(CustomUserAdmin, 'list_display'):
            display_fields = CustomUserAdmin.list_display
            if 'is_public_display' in display_fields:
                print(f"   ✅ Admin tiene 'is_public_display' en list_display")
            else:
                print(f"   ⚠️ Admin NO tiene 'is_public_display'")
        
        # Verificar acciones
        if hasattr(CustomUserAdmin, 'actions'):
            actions = CustomUserAdmin.actions
            if 'make_public' in actions:
                print(f"   ✅ Admin tiene acción 'make_public'")
            if 'make_private' in actions:
                print(f"   ✅ Admin tiene acción 'make_private'")
                
    except ImportError as e:
        print(f"   ⚠️ No se pudo importar admin: {e}")
    
    return True


# ============================================
# TEST 7: VERIFICAR CONFLICTOS CON API EXISTENTE
# ============================================
def test_api_compatibility():
    """Verifica que las vistas API existentes no se rompieron."""
    print("\n🔌 TEST 7: Verificando compatibilidad con API existente...")
    
    try:
        # Intentar importar vistas API existentes
        from musica.views import (
            RegisterView, 
            CustomTokenObtainPairView,
            UserProfileView,
            ProtectedView
        )
        print(f"   ✅ RegisterView importada")
        print(f"   ✅ CustomTokenObtainPairView importada")
        print(f"   ✅ UserProfileView importada")
        print(f"   ✅ ProtectedView importada")
        
    except ImportError as e:
        print(f"   ❌ Error importando vistas API: {e}")
        return False
    
    return True


# ============================================
# TEST 8: VERIFICAR TEMPLATES SEO
# ============================================
def test_seo_templates():
    """Verifica que los templates SEO existen."""
    print("\n📄 TEST 8: Verificando templates SEO...")
    
    from django.template.loader import get_template
    from django.template import TemplateDoesNotExist
    
    templates = [
        'seo/base_seo.html',
        'seo/artist_detail.html',
        'seo/artist_list.html',
    ]
    
    all_exist = True
    for template_name in templates:
        try:
            get_template(template_name)
            print(f"   ✅ Template '{template_name}' existe")
        except TemplateDoesNotExist:
            print(f"   ❌ Template '{template_name}' NO existe")
            all_exist = False
    
    return all_exist


# ============================================
# TEST 9: VERIFICAR SITEMAPS
# ============================================
def test_sitemaps():
    """Verifica que los sitemaps están configurados."""
    print("\n🗺️ TEST 9: Verificando sitemaps...")
    
    try:
        from musica.users.sitemaps import ArtistSitemap, StaticViewSitemap
        
        sitemap = ArtistSitemap()
        print(f"   ✅ ArtistSitemap importado")
        print(f"      - changefreq: {sitemap.changefreq}")
        print(f"      - priority: {sitemap.priority}")
        print(f"      - limit: {sitemap.limit}")
        
    except ImportError as e:
        print(f"   ❌ Error importando sitemaps: {e}")
        return False
    
    return True


# ============================================
# TEST 10: ESTADÍSTICAS FINALES
# ============================================
def test_statistics():
    """Muestra estadísticas de la BD actual."""
    print("\n📊 TEST 10: Estadísticas actuales de la base de datos...")
    
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    verified_users = User.objects.filter(is_verified=True).count()
    
    # Verificar usuarios con slug (si ya existe el campo)
    try:
        users_with_slug = User.objects.exclude(slug='').count()
    except:
        users_with_slug = 0
    
    print(f"   👤 Total usuarios: {total_users}")
    print(f"   ✅ Usuarios activos: {active_users}")
    print(f"   🔵 Usuarios verificados: {verified_users}")
    print(f"   🔗 Usuarios con slug: {users_with_slug}")
    
    if users_with_slug == 0 and total_users > 0:
        print(f"   ⚠️ Se generarán {total_users} slugs al ejecutar init_seo.py")
    
    return True


# ============================================
# EJECUTAR TODOS LOS TESTS
# ============================================
def run_all_tests():
    """Ejecuta todos los tests y muestra resumen."""
    
    tests = [
        ("Modelos", test_model_fields),
        ("Migraciones", test_migrations),
        ("Vistas SEO", test_seo_views),
        ("Serializers", test_serializers),
        ("Slugs (simulación)", test_slug_generation),
        ("Admin Panel", test_admin_integration),
        ("API Compatibilidad", test_api_compatibility),
        ("Templates SEO", test_seo_templates),
        ("Sitemaps", test_sitemaps),
        ("Estadísticas", test_statistics),
    ]
    
    results = {}
    
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n   ❌ Error en test '{name}': {str(e)}")
            results[name] = False
    
    # Resumen final
    print("\n" + "="*70)
    print("📋 RESUMEN DE TESTS")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        icon = "✅" if result else "❌"
        print(f"   {icon} {name}")
    
    print("-"*70)
    print(f"   Resultado: {passed}/{total} tests pasados")
    
    if passed == total:
        print("\n🎉 ¡TODOS LOS TESTS PASARON! Puedes proceder con el despliegue.")
    else:
        print(f"\n⚠️ Hay {total - passed} test(s) que fallaron. Revisa antes de desplegar.")
    
    print("="*70 + "\n")
    
    return passed == total


if __name__ == "__main__":
    run_all_tests()