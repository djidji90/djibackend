#!/usr/bin/env python
"""
Script de testing para endpoints API de artistas.
Ejecutar: python manage.py shell < scripts/test_api_artistas.py
"""

import os
import sys
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djidji_music.settings')
django.setup()

from django.test import RequestFactory
from django.urls import reverse
from musica.models import CustomUser
from musica.views_api import PublicArtistListView, PublicArtistDetailView
from musica.serializers import PublicArtistSerializer

print("\n" + "="*70)
print("🧪 TESTING - API DE ARTISTAS")
print("="*70)

# ============================================
# TEST 1: Verificar imports
# ============================================
print("\n📦 TEST 1: Verificando imports...")

try:
    from musica.views_api import PublicArtistListView, PublicArtistDetailView
    print("   ✅ PublicArtistListView importado")
    print("   ✅ PublicArtistDetailView importado")
except ImportError as e:
    print(f"   ❌ Error importando views_api: {e}")
    sys.exit(1)

try:
    from musica.serializers import PublicArtistSerializer
    print("   ✅ PublicArtistSerializer importado")
except ImportError as e:
    print(f"   ❌ Error importando serializer: {e}")
    sys.exit(1)

# ============================================
# TEST 2: Verificar Serializer
# ============================================
print("\n📝 TEST 2: Verificando PublicArtistSerializer...")

# Obtener un usuario de prueba
user = CustomUser.objects.filter(is_public=True).first()
if not user:
    user = CustomUser.objects.first()

if user:
    serializer = PublicArtistSerializer(user)
    data = serializer.data
    
    print(f"   Usuario: {user.username}")
    print(f"   Campos serializados: {list(data.keys())}")
    
    # Verificar campos requeridos
    required_fields = ['id', 'username', 'slug', 'full_name', 'is_verified', 'is_public', 'profile_url']
    missing = [f for f in required_fields if f not in data]
    
    if missing:
        print(f"   ⚠️ Faltan campos: {missing}")
    else:
        print(f"   ✅ Todos los campos requeridos presentes")
    
    # Verificar que NO expone datos sensibles
    sensitive_fields = ['email', 'phone', 'password', 'can_withdraw']
    exposed = [f for f in sensitive_fields if f in data]
    
    if exposed:
        print(f"   ❌ EXPONE DATOS SENSIBLES: {exposed}")
    else:
        print(f"   ✅ No expone datos sensibles")
else:
    print("   ⚠️ No hay usuarios para probar")

# ============================================
# TEST 3: Simular petición a la API
# ============================================
print("\n🌐 TEST 3: Simulando peticiones API...")

factory = RequestFactory()

# 3.1 Lista de artistas
print("\n   📋 Probando GET /musica/artistas/")
request = factory.get('/musica/artistas/')
view = PublicArtistListView.as_view()

try:
    response = view(request)
    print(f"      Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.data
        if 'results' in data:
            count = len(data['results'])
            print(f"      Artistas devueltos: {count}")
            if count > 0:
                first = data['results'][0]
                print(f"      Primer artista: {first.get('full_name')} (@{first.get('username')})")
        else:
            count = len(data)
            print(f"      Artistas devueltos: {count}")
    else:
        print(f"      ❌ Error: {response.status_code}")
except Exception as e:
    print(f"      ❌ Excepción: {str(e)[:100]}")

# 3.2 Detalle de artista
if user and user.slug:
    print(f"\n   🔍 Probando GET /musica/artistas/{user.slug}/")
    request = factory.get(f'/musica/artistas/{user.slug}/')
    view = PublicArtistDetailView.as_view()
    
    try:
        response = view(request, slug=user.slug)
        print(f"      Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.data
            print(f"      Artista: {data.get('full_name')}")
            print(f"      Slug: {data.get('slug')}")
            print(f"      Profile URL: {data.get('profile_url')}")
        else:
            print(f"      ❌ Error: {response.status_code}")
    except Exception as e:
        print(f"      ❌ Excepción: {str(e)[:100]}")

# ============================================
# TEST 4: Verificar URLs en el router
# ============================================
print("\n🔗 TEST 4: Verificando URLs...")

try:
    list_url = reverse('musica:api_artistas_list')
    print(f"   ✅ URL lista: {list_url}")
except Exception as e:
    print(f"   ❌ URL lista no encontrada: {e}")

if user and user.slug:
    try:
        detail_url = reverse('musica:api_artista_detail', kwargs={'slug': user.slug})
        print(f"   ✅ URL detalle: {detail_url}")
    except Exception as e:
        print(f"   ❌ URL detalle no encontrada: {e}")

# ============================================
# TEST 5: Estadísticas
# ============================================
print("\n📊 TEST 5: Estadísticas de artistas...")

total_users = CustomUser.objects.count()
public_users = CustomUser.objects.filter(is_public=True).count()
verified_users = CustomUser.objects.filter(is_verified=True, is_public=True).count()
users_with_slug = CustomUser.objects.exclude(slug='').count()

print(f"   👤 Total usuarios: {total_users}")
print(f"   🌐 Usuarios públicos: {public_users}")
print(f"   ✅ Usuarios verificados: {verified_users}")
print(f"   🔗 Usuarios con slug: {users_with_slug}")

if public_users == 0:
    print("   ⚠️ No hay usuarios públicos. La API devolverá lista vacía.")

# ============================================
# RESULTADO FINAL
# ============================================
print("\n" + "="*70)
print("✅ TESTS COMPLETADOS")
print("="*70 + "\n"), 