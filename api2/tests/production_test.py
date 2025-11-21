# production_test.py
import os
import django
from django.test import TestCase

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ddjiback.settings')
django.setup()

def test_production_environment():
    """Verificar que todo está listo para producción"""
    
    from django.conf import settings
    from api2.r2_utils import check_file_exists, generate_presigned_url
    
    print("🧪 PRUEBAS DE CONFIGURACIÓN PRODUCCIÓN")
    print("=" * 50)
    
    # 1. Verificar variables críticas
    critical_vars = [
        'SECRET_KEY',
        'DATABASE_URL', 
        'R2_ACCOUNT_ID',
        'R2_ACCESS_KEY_ID',
        'R2_SECRET_ACCESS_KEY'
    ]
    
    for var in critical_vars:
        value = getattr(settings, var, None) or os.environ.get(var)
        if value and len(str(value)) > 10:
            print(f"✅ {var}: Configurado")
            # Mostrar solo primeros y últimos caracteres por seguridad
            masked_value = f"{str(value)[:5]}...{str(value)[-3:]}" if len(str(value)) > 10 else "***"
            print(f"   Valor: {masked_value}")
        else:
            print(f"❌ {var}: NO configurado correctamente")
    
    # 2. Verificar R2
    try:
        # Probar con una key que no debería existir (solo probamos conexión)
        test_key = "test-connection-prod-12345.txt"
        exists = check_file_exists(test_key)
        # Si no hay excepción, la conexión funciona
        print(f"✅ R2 Connection: Funcional")
    except Exception as e:
        print(f"❌ R2 Connection: Error - {e}")
    
    # 3. Verificar base de datos
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("✅ Database Connection: Funcional")
        
        # Verificar tipo de base de datos
        db_engine = settings.DATABASES['default']['ENGINE']
        print(f"   Motor DB: {db_engine}")
        
    except Exception as e:
        print(f"❌ Database Connection: Error - {e}")
    
    # 4. Verificar modo debug y seguridad
    print(f"🔧 DEBUG Mode: {settings.DEBUG}")
    print(f"🛡️ ALLOWED_HOSTS: {getattr(settings, 'ALLOWED_HOSTS', ['No configurado'])}")
    
    # 5. Verificar aplicaciones instaladas
    required_apps = [
        'rest_framework',
        'corsheaders', 
        'django_filters',
        'drf_spectacular',
        'api2',
        'musica'
    ]
    
    print("\n📦 Aplicaciones Requeridas:")
    for app in required_apps:
        if app in settings.INSTALLED_APPS:
            print(f"   ✅ {app}")
        else:
            print(f"   ❌ {app} - FALTANTE")
    
    print("=" * 50)
    
    # Resumen final
    print("🎯 RESUMEN DE PREPARACIÓN PARA PRODUCCIÓN:")
    
    # Contar configuraciones correctas
    critical_ok = sum(1 for var in critical_vars 
                     if getattr(settings, var, None) or os.environ.get(var))
    
    if critical_ok == len(critical_vars) and not settings.DEBUG:
        print("✅✅✅ LISTO PARA PRODUCCIÓN ✅✅✅")
    elif critical_ok == len(critical_vars) and settings.DEBUG:
        print("⚠️  Configuración OK, pero DEBUG=True (cambiar en producción)")
    else:
        print(f"❌ Faltan {len(critical_vars) - critical_ok} configuraciones críticas")

if __name__ == "__main__":
    test_production_environment()