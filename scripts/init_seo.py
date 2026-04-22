#!/usr/bin/env python
"""
Script de inicialización SEO para DjidjiMusic.
Genera slugs para usuarios existentes y verifica la configuración.

Ejecutar: python manage.py shell < scripts/init_seo.py
"""

import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djidji_music.settings')
django.setup()

from musica.models import CustomUser
from django.utils.text import slugify
from django.db import transaction


def generate_slugs():
    """Genera slugs únicos para usuarios existentes que no tengan uno."""
    print("\n" + "="*60)
    print("🚀 INICIALIZANDO SLUGS PARA SEO")
    print("="*60)
    
    users_without_slug = CustomUser.objects.filter(slug='')
    total = users_without_slug.count()
    
    if total == 0:
        print("\n✅ Todos los usuarios ya tienen slug.")
        return
    
    print(f"\n📊 Procesando {total} usuarios sin slug...")
    print("-" * 40)
    
    processed = 0
    errors = 0
    
    for user in users_without_slug.iterator(chunk_size=100):
        try:
            with transaction.atomic():
                base = user.full_name or user.username
                slug = slugify(base)
                
                # Evitar duplicados
                original_slug = slug
                counter = 1
                while CustomUser.objects.filter(slug=slug).exists():
                    slug = f"{original_slug}-{counter}"
                    counter += 1
                
                user.slug = slug
                user.save(update_fields=['slug'])
                processed += 1
                
                if processed % 100 == 0:
                    print(f"   ✅ Procesados {processed}/{total}...")
                    
        except Exception as e:
            errors += 1
            print(f"   ❌ Error con usuario {user.id}: {str(e)}")
    
    print("-" * 40)
    print(f"\n📈 RESULTADO:")
    print(f"   ✅ Procesados exitosamente: {processed}")
    if errors > 0:
        print(f"   ❌ Errores: {errors}")
    print(f"\n✨ Slugs generados correctamente.")


def verify_configuration():
    """Verifica que la configuración SEO esté correcta."""
    print("\n" + "="*60)
    print("🔍 VERIFICANDO CONFIGURACIÓN SEO")
    print("="*60)
    
    # Verificar primer usuario
    test_user = CustomUser.objects.filter(is_public=True).first()
    
    if test_user:
        print(f"\n✅ Usuario de prueba encontrado:")
        print(f"   Nombre: {test_user.full_name}")
        print(f"   Slug: {test_user.slug}")
        print(f"   URL: {test_user.get_absolute_url()}")
        print(f"   Público: {test_user.is_public}")
        print(f"   Indexable: {test_user.is_indexable}")
    else:
        print("\n⚠️ No hay usuarios públicos. Crea algunos para probar.")
    
    # Estadísticas
    total_users = CustomUser.objects.count()
    public_users = CustomUser.objects.filter(is_public=True).count()
    indexable_users = sum(1 for u in CustomUser.objects.all() if u.is_indexable)
    
    print(f"\n📊 ESTADÍSTICAS:")
    print(f"   Total usuarios: {total_users}")
    print(f"   Perfiles públicos: {public_users}")
    print(f"   Perfiles indexables: {indexable_users}")
    
    print("\n" + "="*60)
    print("✨ VERIFICACIÓN COMPLETADA")
    print("="*60 + "\n")


if __name__ == "__main__":
    generate_slugs()
    verify_configuration()