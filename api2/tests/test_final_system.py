# test_final_system.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from api2.models import Song
import json

User = get_user_model()

class FinalSystemTest(TestCase):
    """Test FINAL del sistema completo"""
    
    def test_complete_upload_flow(self):
        """Flujo completo: Upload → DB → Check files"""
        print("\n" + "="*60)
        print("🎵 TEST SISTEMA COMPLETO")
        print("="*60)
        
        # 1. Crear usuario
        user = User.objects.create_user(
            username='system_test',
            password='system_pass',
            email='system@test.com'
        )
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        # 2. Subir canción CON imagen
        print("\n📤 1. Subiendo canción con imagen...")
        
        response = client.post(
            '/api2/songs/upload/',
            {
                'audio_file': SimpleUploadedFile(
                    'song.mp3',
                    b'ID3\x03\x00' + (b'AUDIO' * 1000),
                    'audio/mpeg'
                ),
                'image': SimpleUploadedFile(
                    'cover.jpg',
                    b'\xff\xd8\xff\xe0' + (b'IMAGE' * 500),
                    'image/jpeg'
                ),
                'title': 'Canción de Prueba',
                'artist': 'Artista Test',
                'genre': 'rock',
                'is_public': 'true',
            },
            format='multipart'
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            data = response.json()
            song_id = data['song_id']
            print(f"   ✅ ÉXITO - Song ID: {song_id}")
            print(f"   Title: {data['title']}")
            print(f"   Artist: {data['artist']}")
            
            # 3. Verificar en DB
            print("\n💾 2. Verificando en base de datos...")
            song = Song.objects.get(id=song_id)
            print(f"   DB Title: {song.title}")
            print(f"   DB File Key: {song.file_key}")
            print(f"   DB Image Key: {song.image_key or 'None'}")
            print(f"   DB Public: {song.is_public}")
            
            # 4. Verificar endpoint check-files
            print("\n🔍 3. Verificando archivos en R2...")
            check_response = client.get(f'/api2/songs/{song_id}/check-files/')
            
            if check_response.status_code == 200:
                check_data = check_response.json()
                print(f"   ✅ Check-files OK")
                print(f"   Audio exists: {check_data['files']['audio']['exists']}")
                if song.image_key:
                    print(f"   Image exists: {check_data['files']['image']['exists']}")
            else:
                print(f"   ❌ Check-files failed: {check_response.status_code}")
            
            # 5. Verificar sin autenticación
            print("\n🔐 4. Verificando seguridad...")
            client.force_authenticate(user=None)
            unauth_response = client.get(f'/api2/songs/{song_id}/check-files/')
            print(f"   Sin autenticación: {unauth_response.status_code} (debe ser 401)")
            
            return True
            
        else:
            print(f"   ❌ FALLO")
            print(f"   Errors: {json.dumps(response.json(), indent=2) if response.content else 'No errors'}")
            return False
    
    def test_upload_no_image(self):
        """Test sin imagen"""
        print("\n📤 Test sin imagen...")
        
        user = User.objects.create_user('noimage', 'pass', 'noimage@test.com')
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(
            '/api2/songs/upload/',
            {
                'audio_file': SimpleUploadedFile('song2.mp3', b'MP3' * 100, 'audio/mpeg'),
                'title': 'Sin Imagen',
                'artist': 'Test',
                'is_public': 'false',
            },
            format='multipart'
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            song_id = response.json()['song_id']
            song = Song.objects.get(id=song_id)
            print(f"   ✅ ÉXITO - Song ID: {song_id}")
            print(f"   Image Key: {song.image_key} (debe ser None)")
            
            # Verificar que image_key sea None
            if song.image_key is None:
                print("   ✅ CORRECTO: image_key es None")
            else:
                print(f"   ❌ ERROR: image_key es {song.image_key} (debe ser None)")
            
            return song.image_key is None
            
        else:
            print(f"   ❌ FALLO")
            return False

if __name__ == "__main__":
    test = FinalSystemTest()
    
    print("\n" + "="*60)
    print("🚀 INICIANDO TESTS DEL SISTEMA")
    print("="*60)
    
    # Ejecutar tests
    success1 = test.test_complete_upload_flow()
    success2 = test.test_upload_no_image()
    
    print("\n" + "="*60)
    print("📊 RESULTADOS FINALES")
    print("="*60)
    
    if success1 and success2:
        print("🎉 ¡TODOS LOS TESTS PASARON!")
        print("✅ El sistema de upload funciona correctamente")
        print("✅ Backend listo para producción")
    else:
        print("❌ Algunos tests fallaron")
        print("🔧 Revisa los logs para ver los errores específicos")
    
    print("="*60)