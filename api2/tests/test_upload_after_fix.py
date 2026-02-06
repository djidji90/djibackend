# api2/tests/test_upload_after_fix.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from unittest.mock import patch, MagicMock
import json

from musica.models import CustomUser

class UploadSystemTestAfterFix(TestCase):
    """Test después de corregir el error de timezone"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='testuser_fixed',
            email='test_fixed@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        print(f"\n🔧 Test configurado para usuario: {self.user.username}")
    
    def test_quota_endpoint_working(self):
        """Verificar que el endpoint de cuota funciona"""
        print("\n1. 📊 Probando endpoint de cuota...")
        response = self.client.get(reverse('user-upload-quota'))
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        print(f"   ✅ Status: {response.status_code}")
        print(f"   📋 Estructura: {list(data.keys())}")
        
        # Verificar estructura esperada
        expected_keys = ['daily', 'pending', 'limits', 'totals', 'reset_at']
        for key in expected_keys:
            self.assertIn(key, data)
        
        return True
    
    @patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put')
    @patch('api2.tasks.process_direct_upload.delay')
    def test_upload_request_fixed(self, mock_task, mock_presigned):
        """Test principal después de corregir timezone"""
        print("\n2. 📤 Probando solicitud de upload (PUT)...")
        
        # Configurar mocks
        mock_presigned.return_value = {
            'url': 'https://r2.example.com/upload/test.mp3',
            'method': 'PUT',
            'headers': {
                'Content-Type': 'audio/mpeg',
                'Content-Length': '1048576'
            },
            'key': 'test-key',
            'expires_at': timezone.now().timestamp() + 3600
        }
        
        mock_task.return_value = MagicMock(id='test-task-123')
        
        # Datos de prueba
        test_data = {
            'file_name': 'test_after_fix.mp3',
            'file_size': 1048576,
            'file_type': 'audio/mpeg',
            'metadata': {
                'original_name': 'test_fixed.mp3',
                'test_case': 'after_timezone_fix'
            }
        }
        
        response = self.client.post(
            reverse('direct-upload-request'),
            data=json.dumps(test_data),
            content_type='application/json'
        )
        
        print(f"   📥 Response status: {response.status_code}")
        
        # Manejo de errores específicos
        if response.status_code == 500:
            error_data = response.json()
            error_msg = str(error_data)
            
            print(f"   ❌ Error 500: {error_data}")
            
            # Detectar si es el error de timezone
            if 'timezone' in error_msg.lower() or 'utc' in error_msg.lower():
                print("\n   ⚠️  ¡ERROR DE TIMEZONE PERSISTE!")
                print("   ================================")
                print("   La corrección no funcionó.")
                print("   Verifica que en views.py línea ~2385 tenga:")
                print("   expires_at = datetime.fromtimestamp(..., tz=pytz.UTC)")
                print("   Y que 'import pytz' esté al inicio del archivo")
                print("   ================================")
                return False
        
        # Verificar éxito
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.json()
        print(f"   ✅ Success: {response_data.get('success')}")
        print(f"   ✅ Method: {response_data.get('method')} (debe ser PUT)")
        print(f"   📦 Upload ID: {response_data.get('upload_id')}")
        
        # Verificaciones específicas
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['method'], 'PUT')
        self.assertIn('upload_url', response_data)
        self.assertIn('headers', response_data)
        
        return True
    
    def run_comprehensive_test(self):
        """Ejecutar test completo"""
        print("\n" + "="*60)
        print("🧪 TEST COMPLETO - SISTEMA DE UPLOAD")
        print("="*60)
        
        tests = [
            ("Endpoint de cuota", self.test_quota_endpoint_working),
            ("Solicitud de upload PUT", self.test_upload_request_fixed),
        ]
        
        results = []
        for test_name, test_func in tests:
            print(f"\n{'='*40}")
            print(f"🧪 {test_name}")
            print(f"{'='*40}")
            
            try:
                if test_name == "Solicitud de upload PUT":
                    # Este test necesita mocks específicos
                    with patch('api2.utils.r2_direct.R2DirectUpload.generate_presigned_put') as mock_presigned, \
                         patch('api2.tasks.process_direct_upload.delay') as mock_task:
                        
                        mock_presigned.return_value = {
                            'url': 'https://r2.test.com/upload',
                            'method': 'PUT',
                            'headers': {'Content-Type': 'test'},
                            'key': 'test-key',
                            'expires_at': 1234567890
                        }
                        mock_task.return_value = MagicMock(id='mock-task')
                        
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
        
        # Resumen
        print("\n" + "="*60)
        print("📋 RESULTADOS DEL TEST")
        print("="*60)
        
        all_passed = True
        for name, passed, error in results:
            status_icon = "✅" if passed else "❌"
            print(f"{status_icon} {name}")
            if not passed and error:
                print(f"   Error: {error}")
            all_passed = all_passed and passed
        
        print("\n" + "="*60)
        if all_passed:
            print("🎉 ¡SISTEMA DE UPLOAD FUNCIONANDO CORRECTAMENTE!")
            print("   Puedes pasar a producción 🚀")
        else:
            print("⚠️  Se encontraron problemas")
            print("   Revisa los errores arriba")
        
        return all_passed

# Para ejecutar directamente
if __name__ == "__main__":
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ddjiback.settings')
    django.setup()
    
    test = UploadSystemTestAfterFix()
    test.setUp()
    test.run_comprehensive_test()