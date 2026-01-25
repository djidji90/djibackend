import os
import django
from django.urls import get_resolver, URLPattern, URLResolver

# Configuración de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

OUTPUT_FILE = 'urls_list.txt'

def list_urls(lis, parent_pattern=''):
    """
    Función recursiva que recorre URLs y devuelve tuplas:
    (ruta, view_name, nombre_url)
    """
    url_list = []

    for entry in lis:
        if isinstance(entry, URLPattern):
            pattern = parent_pattern + str(entry.pattern)
            view = f"{entry.lookup_str}" if hasattr(entry, 'lookup_str') else str(entry.callback)
            name = entry.name if entry.name else ''
            url_list.append((pattern, view, name))
        elif isinstance(entry, URLResolver):
            nested_pattern = parent_pattern + str(entry.pattern)
            url_list.extend(list_urls(entry.url_patterns, nested_pattern))
    return url_list

# Obtener todas las URLs
resolver = get_resolver()
all_urls = list_urls(resolver.url_patterns)

# Guardar en archivo
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    for pattern, view, name in all_urls:
        f.write(f"{pattern}\t{view}\t{name}\n")

print(f"✅ Todas las URLs se exportaron a {OUTPUT_FILE}")
