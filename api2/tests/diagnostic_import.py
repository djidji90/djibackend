# diagnostic_import.py
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ddjiback.settings')
django.setup()

from api2 import urls

print("🔍 DIAGNÓSTICO DE IMPORTS DE API2")
print("=" * 50)

# Verificar si las views reales están siendo importadas
try:
    from api2.views import DirectUploadRequestView as RealView
    print("✅ DirectUploadRequestView real importada desde views.py")
    print(f"   Ubicación: {RealView.__module__}")
except ImportError as e:
    print(f"❌ No se puede importar DirectUploadRequestView: {e}")

print("\n📋 URLs registradas:")
for pattern in urls.urlpatterns:
    if hasattr(pattern, 'name') and pattern.name:
        if 'upload' in pattern.name:
            print(f"  - {pattern.name}: {pattern.pattern}")