# Crear un script para ejecutar todas las pruebas
# run_all_tests.py
import sys
import subprocess

def run_tests():
    """Ejecutar todas las suites de prueba"""
    test_suites = [
        'api2.tests.test_upload_system',
        'api2.tests.test_file_checking',
        'api2.tests.test_streaming',
        'api2.tests.test_rate_limiting',
        'api2.tests.test_download_models',  # Tus tests existentes
    ]
    
    all_passed = True
    
    for suite in test_suites:
        print(f"\n{'='*70}")
        print(f"🚀 EJECUTANDO: {suite}")
        print('='*70)
        
        result = subprocess.run(
            ['python', 'manage.py', 'test', suite, '--verbosity=2'],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode != 0:
            all_passed = False
            print(f"❌ {suite} FALLÓ")
        else:
            print(f"✅ {suite} PASÓ")
    
    print(f"\n{'='*70}")
    if all_passed:
        print("🎉 ¡TODAS LAS PRUEBAS PASARON!")
    else:
        print("⚠️  ALGUNAS PRUEBAS FALLARON")
    print('='*70)
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(run_tests())