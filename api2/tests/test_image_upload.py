# api2/tests/test_image_upload.py
"""
Tests para diagnosticar problemas de subida de imágenes a R2
Versión corregida para usar CustomUser
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
import io
import time
from PIL import Image
import requests

# Obtener el modelo de usuario personalizado
User = get_user_model()

class ImageUploadDiagnosticTest(TestCase):
    """Diagnóstico completo de subida de imágenes"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Crear usuario usando el modelo personalizado
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.force_authenticate(user=self.user)
        print(f"\n✅ Usuario de prueba creado: {self.user.username} (ID: {self.user.id})")
    
    def test_1_request_upload_url_for_image(self):
        """Test 1: Solicitar URL de upload para imagen"""
        print("\n" + "="*60)
        print("TEST 1: Solicitar URL de upload para imagen")
        print("="*60)
        
        # Crear imagen de prueba
        img = Image.new('RGB', (100, 100), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_size = len(img_byte_arr.getvalue())
        
        response = self.client.post('/api2/upload/direct/request/', {
            'file_name': 'test_image.jpg',
            'file_size': img_size,
            'file_type': 'image/jpeg',
            'metadata': {
                'title': 'Test Image',
                'type': 'cover_art'
            }
        })
        
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Éxito!")
            print(f"   Upload ID: {data.get('upload_id')}")
            print(f"   File key: {data.get('file_key')}")
            print(f"   Method: {data.get('method')}")
            print(f"   Upload URL: {data.get('upload_url', '')[:80]}...")
            self.assertIsNotNone(data.get('upload_url'))
        else:
            print(f"❌ Falló: {response.json()}")
            self.fail(f"Request failed with status {response.status_code}")
    
    def test_2_full_image_upload_flow(self):
        """Test 2: Flujo completo - solicitar, subir y confirmar imagen"""
        print("\n" + "="*60)
        print("TEST 2: Flujo completo de subida de imagen")
        print("="*60)
        
        # 1. Crear imagen de prueba
        print("\n📸 Creando imagen de prueba...")
        img = Image.new('RGB', (200, 200), color='blue')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_data = img_byte_arr.getvalue()
        print(f"   Tamaño: {len(img_data)} bytes")
        
        # 2. Solicitar URL de upload
        print("\n📤 Solicitando URL de upload...")
        request_response = self.client.post('/api2/upload/direct/request/', {
            'file_name': 'full_test_image.jpg',
            'file_size': len(img_data),
            'file_type': 'image/jpeg',
            'metadata': {
                'title': 'Full Test Image',
                'artist': 'Test Artist',
                'type': 'cover_art'
            }
        })
        
        if request_response.status_code != 200:
            print(f"❌ Falló solicitud: {request_response.json()}")
            self.fail("Failed to get upload URL")
        
        upload_data = request_response.json()
        upload_id = upload_data['upload_id']
        upload_url = upload_data['upload_url']
        file_key = upload_data['file_key']
        
        print(f"✅ Upload ID: {upload_id}")
        print(f"✅ File Key: {file_key}")
        
        # 3. Subir imagen a R2
        print("\n☁️ Subiendo imagen a R2...")
        try:
            put_response = requests.put(
                upload_url,
                data=img_data,
                headers={'Content-Type': 'image/jpeg'},
                timeout=30
            )
            
            print(f"   PUT Response: {put_response.status_code}")
            
            if put_response.status_code not in [200, 204]:
                print(f"❌ PUT falló: {put_response.text}")
                self.fail(f"PUT to R2 failed with status {put_response.status_code}")
            
            print("✅ Imagen subida exitosamente a R2")
            
        except Exception as e:
            print(f"❌ Error en PUT: {str(e)}")
            self.fail(f"PUT error: {str(e)}")
        
        # 4. Confirmar upload
        print("\n✅ Confirmando upload...")
        confirm_response = self.client.post(
            f'/api2/upload/direct/confirm/{upload_id}/',
            {'delete_invalid': True}
        )
        
        print(f"   Confirm Status: {confirm_response.status_code}")
        confirm_data = confirm_response.json()
        print(f"   Confirm Response: {confirm_data}")
        
        if confirm_response.status_code == 200:
            print("✅ Upload confirmado exitosamente")
            print(f"   Status: {confirm_data.get('status')}")
        else:
            print("❌ Confirmación falló")
            # No fallamos el test aquí para poder ver el error completo
    
    def test_3_compare_audio_vs_image_upload(self):
        """Test 3: Comparar comportamiento entre audio e imagen"""
        print("\n" + "="*60)
        print("TEST 3: Comparando audio vs imagen")
        print("="*60)
        
        # Crear imagen
        img = Image.new('RGB', (100, 100), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        img_data = img_byte_arr.getvalue()
        
        # 1. Solicitar upload para imagen
        print("\n📸 Solicitando para IMAGEN...")
        img_response = self.client.post('/api2/upload/direct/request/', {
            'file_name': 'compare_image.jpg',
            'file_size': len(img_data),
            'file_type': 'image/jpeg',
            'metadata': {'type': 'image'}
        })
        
        print(f"   Status: {img_response.status_code}")
        if img_response.status_code == 200:
            img_data_resp = img_response.json()
            print(f"   Upload ID: {img_data_resp.get('upload_id')}")
            print(f"   File key: {img_data_resp.get('file_key')}")
            print(f"   Method: {img_data_resp.get('method')}")
            img_key = img_data_resp.get('file_key', '')
        else:
            print(f"   Error: {img_response.json()}")
            img_key = ""
        
        # 2. Solicitar upload para audio (simulado)
        print("\n🎵 Solicitando para AUDIO...")
        audio_response = self.client.post('/api2/upload/direct/request/', {
            'file_name': 'compare_audio.mp3',
            'file_size': 1024 * 1024,  # 1MB
            'file_type': 'audio/mpeg',
            'metadata': {'type': 'audio'}
        })
        
        print(f"   Status: {audio_response.status_code}")
        if audio_response.status_code == 200:
            audio_data_resp = audio_response.json()
            print(f"   Upload ID: {audio_data_resp.get('upload_id')}")
            print(f"   File key: {audio_data_resp.get('file_key')}")
            print(f"   Method: {audio_data_resp.get('method')}")
            audio_key = audio_data_resp.get('file_key', '')
        else:
            print(f"   Error: {audio_response.json()}")
            audio_key = ""
        
        # Comparar
        if img_response.status_code == 200 and audio_response.status_code == 200:
            print("\n✅ Ambos tipos de archivo reciben respuesta 200")
            
            # Comparar estructura de file_key
            print(f"\n   Imagen key: {img_key}")
            print(f"   Audio key: {audio_key}")
            
            if 'images' in img_key:
                print("   ✅ Imagen usa directorio 'images'")
            else:
                print("   ⚠️ Imagen NO usa directorio 'images' - ESTO PODRÍA SER EL PROBLEMA")
            
            if 'audio' in audio_key or 'songs' in audio_key:
                print("   ✅ Audio usa directorio correcto")
        else:
            print("\n❌ Diferencia en comportamiento")
            if img_response.status_code != 200:
                print(f"   Imagen falló con status {img_response.status_code}")
                print(f"   Error: {img_response.json()}")
            if audio_response.status_code != 200:
                print(f"   Audio falló con status {audio_response.status_code}")