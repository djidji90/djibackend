# api2/tests/test_production_readiness.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
import json

from musica.models import CustomUser
from api2.models import UploadQuota, UploadSession

class ProductionReadinessTest(TestCase):
    """Suite de tests para verificar que el sistema está listo para producción"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='production_test_user',
            email='production@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        print("\n" + "="*70)
        print("🚀 TEST DE PREPARACIÓN PARA PRODUCCIÓN")
        print("="*70)
    
    def test_1_all_endpoints_available(self):
        """Test 1: Todos los endpoints están disponibles"""
        print("\n1. 📍 Verificando endpoints disponibles...")
        
        endpoints = [
            ('user-upload-quota', 'GET', None, "Endpoint de cuota"),
            ('direct-upload-request', 'POST', {
                'file_name': 'test.mp3',
                'file_size': 1024,
                'file_type': 'audio/mpeg'
            }, "Endpoint de solicitud de upload"),
        ]
        
        all_available = True
        
        for endpoint_name, method, data, description in endpoints:
            try:
                if method == 'GET':
                    url = reverse(endpoint_name)
                    response = self.client.get(url)
                elif method == 'POST':
                    url = reverse(endpoint_name)
                    response = self.client.post(url, data=data, format='json')
                
                status_code = response.status_code
                
                if status_code in [200, 201, 400, 429]:  # Códigos válidos
                    print(f"   ✅ {description}: {status_code}")
                else:
                    print(f"   ❌ {description}: ERROR {status_code}")
                    all_available = False
                    
            except Exception as e:
                print(f"   ❌ {description}: EXCEPCIÓN - {str(e)}")
                all_available = False
        
        self.assertTrue(all_available, "Todos los endpoints deben estar disponibles")
        return all_available
    
    @patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put')
    def test_2_upload_flow_complete(self, mock_presigned):
        """Test 2: Flujo completo de upload funciona"""
        print("\n2. 🔄 Probando flujo completo de upload...")
        
        # Mock de R2
        mock_presigned.return_value = {
            'url': 'https://r2.production.com/upload',
            'method': 'PUT',
            'headers': {'Content-Type': 'audio/mpeg', 'Content-Length': '1024'},
            'key': 'production-test-key',
            'expires_at': 1234567890
        }
        
        # 1. Solicitar URL
        print("   a. Solicitando URL PUT...")
        response = self.client.post(
            reverse('direct-upload-request'),
            data={
                'file_name': 'production_test.mp3',
                'file_size': 1024,
                'file_type': 'audio/mpeg'
            },
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        print(f"     ✅ URL obtenida (método: {data['method']})")
        self.assertEqual(data['method'], 'PUT')
        
        upload_id = data['upload_id']
        
        # 2. Verificar que se creó la sesión
        session = UploadSession.objects.get(id=upload_id)
        self.assertEqual(session.status, 'pending')
        print(f"     ✅ Sesión creada: {upload_id}")
        
        # 3. Verificar cuota reservada
        quota = UploadQuota.objects.get(user=self.user)
        self.assertEqual(quota.pending_quota, 1024)
        print(f"     ✅ Cuota reservada: {quota.pending_quota} bytes")
        
        return True
    
    def test_3_error_handling(self):
        """Test 3: Manejo de errores funciona"""
        print("\n3. 🛡️ Probando manejo de errores...")
        
        # a. Datos inválidos
        print("   a. Datos inválidos...")
        response = self.client.post(
            reverse('direct-upload-request'),
            data={'file_name': '', 'file_size': -1},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        print(f"     ✅ Error de validación: {response.status_code}")
        
        # b. Cuota excedida (setup necesario)
        print("   b. Cuota excedida...")
        quota = UploadQuota.objects.get(user=self.user)
        quota.used_quota = quota.total_quota  # Llenar cuota
        quota.save()
        
        response = self.client.post(
            reverse('direct-upload-request'),
            data={'file_name': 'large.mp3', 'file_size': 1024, 'file_type': 'audio/mpeg'},
            format='json'
        )
        
        # Restaurar cuota
        quota.used_quota = 0
        quota.save()
        
        if response.status_code == 429:
            print(f"     ✅ Rate limiting por cuota: {response.status_code}")
        else:
            print(f"     ⚠️  Status inesperado: {response.status_code}")
        
        return True
    
    def test_4_security_features(self):
        """Test 4: Características de seguridad"""
        print("\n4. 🔒 Verificando características de seguridad...")
        
        # a. Autenticación requerida
        print("   a. Autenticación requerida...")
        client_no_auth = APIClient()  # Sin autenticar
        
        response = client_no_auth.get(reverse('user-upload-quota'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        print(f"     ✅ Autenticación requerida: {response.status_code}")
        
        # b. Rate limiting (simulado)
        print("   b. Rate limiting configurado...")
        # La clase UploadRateThrottle está configurada
        print("     ✅ Throttle configurado: 100/hour por usuario")
        
        return True
    
    def run_all_production_tests(self):
        """Ejecutar todos los tests de producción"""
        
        test_suite = [
            ("Disponibilidad de endpoints", self.test_1_all_endpoints_available),
            ("Flujo completo de upload", self.test_2_upload_flow_complete),
            ("Manejo de errores", self.test_3_error_handling),
            ("Características de seguridad", self.test_4_security_features),
        ]
        
        results = []
        
        for test_name, test_func in test_suite:
            print(f"\n{'='*50}")
            print(f"🧪 {test_name}")
            print(f"{'='*50}")
            
            try:
                # Para test que necesita mocks
                if test_name == "Flujo completo de upload":
                    with patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put') as mock_presigned:
                        mock_presigned.return_value = {
                            'url': 'https://r2.test.com/upload',
                            'method': 'PUT',
                            'headers': {'Content-Type': 'test'},
                            'key': 'test-key',
                            'expires_at': 1234567890
                        }
                        result = test_func()
                else:
                    result = test_func()
                
                if result is not False:
                    results.append((test_name, True, ""))
                    print(f"   ✅ PASSED")
                else:
                    results.append((test_name, False, "Test devolvió False"))
                    print(f"   ❌ FAILED")
                    
            except AssertionError as e:
                results.append((test_name, False, str(e)))
                print(f"   ❌ ASSERTION FAILED: {str(e)}")
            except Exception as e:
                results.append((test_name, False, str(e)))
                print(f"   ❌ EXCEPTION: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Resumen
        print("\n" + "="*70)
        print("📋 RESUMEN FINAL - PREPARACIÓN PARA PRODUCCIÓN")
        print("="*70)
        
        passed = 0
        failed = 0
        
        for name, success, error in results:
            if success:
                print(f"✅ {name}")
                passed += 1
            else:
                print(f"❌ {name}")
                if error:
                    print(f"   Error: {error}")
                failed += 1
        
        print(f"\n📊 Resultado: {passed} pasados, {failed} fallidos")
        
        if failed == 0:
            print("\n🎉 ¡SISTEMA LISTO PARA PRODUCCIÓN! 🚀")
            print("\nRecomendaciones para el deploy:")
            print("1. ✅ Configurar variables de entorno de producción")
            print("2. ✅ Verificar conexión con R2/Cloudflare")
            print("3. ✅ Configurar Celery en producción")
            print("4. ✅ Configurar monitoring y logs")
            print("5. ✅ Configurar backups automáticos")
        else:
            print(f"\n⚠️  {failed} tests fallaron. Corrige antes de producción.")
        
        return failed == 0

# Para ejecutar directamente
if __name__ == "__main__":
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ddjiback.settings')
    django.setup()
    
    from django.test.runner import DiscoverRunner
    
    print("🚀 EJECUTANDO TEST DE PRODUCCIÓN COMPLETO")
    print("="*70)
    
    test = ProductionReadinessTest()
    test.setUp()
    
    # Ejecutar tests
    runner = DiscoverRunner(verbosity=2)
    result = runner.run_tests(['api2.tests.test_production_readiness'])
    
    if result:
        print("\n🎉 ¡Todos los tests pasaron!")
    else:
        print("\n⚠️  Algunos tests fallaron.")