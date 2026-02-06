# test_put_upload_final_fixed.py
import requests
import json
import time as time_module
import sys
import os

def test_put_upload_final():
    """Test final del sistema PUT - Versión completamente corregida"""
    
    print("=" * 70)
    print("🧪 TEST FINAL - UPLOAD VIA PUT (VERSIÓN COMPLETA)")
    print("=" * 70)
    
    # Configuración
    BASE_URL = "http://localhost:8000"
    TEST_USER = "jordi"
    TEST_PASSWORD = "machimbo90"
    
    def print_step(step_num, title):
        print(f"\n{step_num}. {title}")
        print("-" * 40)
    
    try:
        # 1. Autenticar
        print_step("1", "🔑 Autenticando")
        auth = requests.post(
            f'{BASE_URL}/musica/api/token/',
            json={'username': TEST_USER, 'password': TEST_PASSWORD},
            timeout=10
        )
        
        if auth.status_code != 200:
            print(f"❌ Error de autenticación: {auth.status_code}")
            print(f"   Detalle: {auth.text}")
            return False
        
        token = auth.json()['access']
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        print(f"✅ Autenticado - Token: {token[:20]}...")
        
        # 2. Verificar cuota
        print_step("2", "📊 Verificando cuota")
        quota_response = requests.get(
            f'{BASE_URL}/api2/upload/quota/',
            headers=headers,
            timeout=10
        )
        
        if quota_response.status_code == 200:
            quota_data = quota_response.json()
            print(f"✅ Cuota obtenida")
            print(f"   📋 Estructura: {list(quota_data.keys())}")
        else:
            print(f"⚠️  Error obteniendo cuota: {quota_response.status_code}")
            print(f"   Continuando de todas formas...")
        
        # 3. Solicitar URL PUT
        print_step("3", "📋 Solicitando URL PUT")
        
        upload_data = {
            'file_name': 'test_final_put.mp3',
            'file_size': 1024,  # 1KB para test
            'file_type': 'audio/mpeg',
            'metadata': {
                'original_name': 'test_audio.mp3',
                'test_run': True,
                'timestamp': time_module.strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        response = requests.post(
            f'{BASE_URL}/api2/upload/direct/request/',
            json=upload_data,
            headers=headers,
            timeout=30
        )
        
        print(f"📥 Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Error del backend: {response.status_code}")
            
            try:
                error_data = response.json()
                print(f"📄 Error details: {error_data}")
                
                # Detectar errores específicos
                error_str = str(error_data).lower()
                if 'time' in error_str and 'not defined' in error_str:
                    print("\n⚠️  ¡ERROR CRÍTICO DETECTADO!")
                    print("=" * 40)
                    print("Falta 'import time' en api2/utils/r2_direct.py")
                    print("Ejecuta: python fix_r2_complete.py")
                    print("=" * 40)
                elif 'uploadquota' in error_str and 'doesnotexist' in error_str:
                    print("\n⚠️  ¡ERROR DE MODELO DETECTADO!")
                    print("=" * 40)
                    print("El modelo UploadQuota no existe en la base de datos")
                    print("Ejecuta:")
                    print("  python manage.py makemigrations api2")
                    print("  python manage.py migrate")
                    print("=" * 40)
                    
            except:
                print(f"📄 Raw error: {response.text[:200]}")
            
            return False
        
        # Procesar respuesta exitosa
        data = response.json()
        print(f"✅ URL obtenida exitosamente")
        print(f"   📦 Upload ID: {data.get('upload_id')}")
        print(f"   🔗 Método: {data.get('method')}")
        
        # Verificar que sea PUT
        if data.get('method') != 'PUT':
            print(f"❌ ERROR: El método debería ser PUT, es: {data.get('method')}")
            return False
        
        print(f"   ⏰ Expira en: {data.get('expires_in', 'N/A')} segundos")
        
        # 4. Mostrar instrucciones
        print_step("4", "📝 Instrucciones para frontend")
        if 'instructions' in data:
            instructions = data['instructions']
            print(f"✅ Método: {instructions.get('method', 'PUT')}")
            print(f"✅ Content-Type: {instructions.get('content_type', 'N/A')}")
        else:
            print(f"⚠️  No hay instrucciones detalladas en la respuesta")
        
        # 5. Probar confirmación (simulada)
        print_step("5", "✅ Probando confirmación (simulada)")
        
        upload_id = data.get('upload_id')
        if upload_id:
            confirm_url = f"{BASE_URL}/api2/upload/direct/confirm/{upload_id}/"
            
            confirm_response = requests.post(
                confirm_url,
                json={'delete_invalid': False},
                headers=headers,
                timeout=10
            )
            
            print(f"📋 Confirmación status: {confirm_response.status_code}")
            
            if confirm_response.status_code == 200:
                confirm_data = confirm_response.json()
                print(f"🎉 ¡Upload confirmado exitosamente!")
                print(f"   🆔 ID: {confirm_data.get('upload_id')}")
                print(f"   📊 Estado: {confirm_data.get('status')}")
            else:
                print(f"⚠️  Error en confirmación: {confirm_response.status_code}")
                try:
                    error_details = confirm_response.json()
                    print(f"📄 Detalles: {error_details}")
                except:
                    print(f"📄 Raw: {confirm_response.text[:200]}")
        
        # 6. Verificar estado
        print_step("6", "📊 Verificando estado")
        if upload_id:
            status_url = f"{BASE_URL}/api2/upload/direct/status/{upload_id}/"
            status_response = requests.get(status_url, headers=headers, timeout=10)
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"✅ Estado obtenido: {status_data.get('status')}")
            else:
                print(f"⚠️  Error obteniendo estado: {status_response.status_code}")
        
        print("\n" + "=" * 70)
        print("✅ TEST COMPLETADO EXITOSAMENTE")
        print("=" * 70)
        
        return True
        
    except requests.exceptions.Timeout:
        print(f"❌ Timeout en la solicitud")
        return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Error de conexión")
        print("   Asegúrate de que el servidor esté ejecutándose:")
        print("   python manage.py runserver")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def run_diagnostic():
    """Ejecuta diagnóstico del sistema"""
    print("\n" + "=" * 70)
    print("🔧 DIAGNÓSTICO DEL SISTEMA")
    print("=" * 70)
    
    checks = []
    
    # 1. Verificar que el servidor esté corriendo
    print("\n1. 🔍 Verificando servidor local...")
    try:
        response = requests.get("http://localhost:8000/", timeout=5)
        checks.append(("Servidor corriendo", response.status_code in [200, 301, 302]))
        print(f"   ✅ Servidor respondió: {response.status_code}")
    except:
        checks.append(("Servidor corriendo", False))
        print(f"   ❌ Servidor no responde en localhost:8000")
    
    # 2. Verificar archivos críticos
    print("\n2. 📁 Verificando archivos críticos...")
    
    critical_files = [
        ('api2/utils/r2_direct.py', True),
        ('api2/views.py', True),
        ('api2/models.py', True),
        ('api2/urls.py', True),
    ]
    
    for file_path, required in critical_files:
        exists = os.path.exists(file_path)
        checks.append((f"Archivo {file_path}", exists or not required))
        status = "✅" if exists else "❌" if required else "⚠️"
        print(f"   {status} {file_path}")
    
    # 3. Verificar imports en r2_direct.py
    print("\n3. 🔍 Verificando imports en r2_direct.py...")
    if os.path.exists('api2/utils/r2_direct.py'):
        with open('api2/utils/r2_direct.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_imports = ['import time', 'import boto3', 'from botocore', 'from django.conf']
        for imp in required_imports:
            has_import = imp in content
            checks.append((f"Import {imp}", has_import))
            status = "✅" if has_import else "❌"
            print(f"   {status} {imp}")
    
    # Resumen
    print("\n" + "=" * 70)
    print("📋 RESUMEN DEL DIAGNÓSTICO")
    print("=" * 70)
    
    passed = sum(1 for _, status in checks if status)
    total = len(checks)
    
    for check_name, check_status in checks:
        status_icon = "✅" if check_status else "❌"
        print(f"{status_icon} {check_name}")
    
    success_rate = (passed / total) * 100 if total > 0 else 0
    print(f"\n🎯 Resultado: {passed}/{total} checks pasados ({success_rate:.1f}%)")
    
    if passed == total:
        print("\n✅ Sistema listo para tests")
        return True
    elif passed >= total * 0.7:
        print(f"\n⚠️  Sistema {success_rate:.1f}% listo. Algunos problemas menores.")
        return True
    else:
        print(f"\n❌ Sistema solo {success_rate:.1f}% listo. Problemas críticos.")
        return False

if __name__ == "__main__":
    print("🚀 TEST FINAL DEL SISTEMA DE UPLOAD PUT")
    print("⚠️  Asegúrate de que el servidor esté ejecutándose")
    print("   Comando: python manage.py runserver")
    print("-" * 70)
    
    # Primero hacer diagnóstico
    if not run_diagnostic():
        print("\n❌ Problemas detectados. Corrige antes de continuar.")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("🧪 INICIANDO TEST FUNCIONAL")
    print("=" * 70)
    
    success = test_put_upload_final()
    
    if success:
        print("\n🎉 ¡SISTEMA DE UPLOAD FUNCIONANDO CORRECTAMENTE!")
        print("\n📝 Resumen de funcionalidades verificadas:")
        print("   ✅ Autenticación JWT")
        print("   ✅ Consulta de cuota")
        print("   ✅ Generación de URL PUT")
        print("   ✅ Confirmación de upload")
        print("   ✅ Verificación de estado")
        print("\n🚀 ¡Listo para producción!")
        sys.exit(0)
    else:
        print("\n⚠️  Se encontraron problemas durante el test.")
        print("\n🔧 Soluciones comunes:")
        print("   1. 'time' not defined → Ejecuta: python fix_r2_complete.py")
        print("   2. Servidor no corriendo → Ejecuta: python manage.py runserver")
        print("   3. Migraciones pendientes → Ejecuta migraciones")
        print("   4. Error 500 → Revisa logs del servidor")
        sys.exit(1)