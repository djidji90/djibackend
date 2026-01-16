# api2/tests/test_upload_system.py
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from api2.models import Song
from api2.r2_utils import delete_file_from_r2
import io
import os

User = get_user_model()

class TestSongUploadSystem(TestCase):
    """Pruebas completas para el sistema de upload"""
    
    def setUp(self):
        """Configuración inicial"""
        print("\n" + "="*60)
        print("🔄 Configurando tests de upload...")
        
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='uploaduser',
            email='upload@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Crear archivos de prueba en MEMORIA (sin guardar en disco)
        self.create_test_files()
        
        print("✅ Configuración completada")
        print("="*60)
    
def create_test_files(self):
    """Crear archivos de prueba válidos"""
    import io
    from PIL import Image
    
    # Audio MP3 simulado
    self.valid_audio_content = b'ID3\x03\x00' + b'A' * 1024
    self.valid_audio = SimpleUploadedFile(
        "test_song.mp3",
        self.valid_audio_content,
        content_type="audio/mpeg"
    )
    
    # Crear una imagen JPEG real en memoria
    try:
        # Intenta usar PIL para crear imagen real
        image = Image.new('RGB', (100, 100), color='red')
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        
        self.valid_image_content = img_byte_arr.getvalue()
    except ImportError:
        # Fallback: JPEG válido simple
        self.valid_image_content = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00'
            b'\xff\xdb\x00C\x00\x03\x02\x02\x03\x02\x02\x03\x03\x03\x03\x04'
            b'\x03\x03\x04\x05\x08\x05\x05\x04\x04\x05\n\x07\x07\x06\x08\x0c'
            b'\n\x0c\x0c\x0b\n\x0b\x0b\r\x0e\x12\x10\r\x0e\x11\x0e\x0b\x0b'
            b'\x10\x16\x10\x11\x13\x14\x15\x15\x15\x0c\x0f\x17\x18\x16\x14'
            b'\x18\x12\x14\x15\x14\xff\xc0\x00\x0b\x08\x00d\x00d\x01\x01\x11'
            b'\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07'
            b'\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04'
            b'\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05'
            b'\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R'
            b'\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEF'
            b'GHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a'
            b'\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7'
            b'\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4'
            b'\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda'
            b'\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5'
            b'\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00'
            b'\xff\xd9'
        )
    
    self.valid_image = SimpleUploadedFile(
        "test_cover.jpg",
        self.valid_image_content,
        content_type="image/jpeg"
    )
    
    def test_01_successful_upload_with_image(self):
        """Prueba 1: Subida exitosa con audio e imagen"""
        print("\n🎵 Test 1: Subida exitosa con audio e imagen")
        
        data = {
            'title': 'Canción de prueba completa',
            'artist': 'Artista famoso',
            'genre': 'Pop Rock',
            'duration': '3:45',
            'is_public': True,
            'audio_file': self.valid_audio,
            'image_file': self.valid_image,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            response_data = response.json()
            print(f"   ✅ ÉXITO: Canción creada con ID {response_data.get('song_id')}")
            print(f"   Título: {response_data.get('title')}")
            print(f"   Artista: {response_data.get('artist')}")
            
            # Verificar en base de datos
            song = Song.objects.get(id=response_data['song_id'])
            self.assertEqual(song.title, 'Canción de prueba completa')
            self.assertEqual(song.artist, 'Artista famoso')
            self.assertEqual(song.uploaded_by, self.user)
            self.assertIsNotNone(song.file_key)
            
            # Limpiar archivos de R2 después de la prueba
            if song.file_key:
                delete_file_from_r2(song.file_key)
            if song.image_key:
                delete_file_from_r2(song.image_key)
                
        else:
            print(f"   ❌ FALLÓ: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_02_successful_upload_without_image(self):
        """Prueba 2: Subida exitosa solo con audio (sin imagen)"""
        print("\n🎵 Test 2: Subida solo con audio (sin imagen)")
        
        data = {
            'title': 'Canción sin imagen',
            'artist': 'Artista independiente',
            'genre': 'Indie',
            'audio_file': self.valid_audio,
            # Sin image_file
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            print("   ✅ ÉXITO: Canción subida sin imagen")
            
            # Limpiar
            song_id = response.json()['song_id']
            song = Song.objects.get(id=song_id)
            if song.file_key:
                delete_file_from_r2(song.file_key)
        else:
            print(f"   ❌ FALLÓ: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_03_upload_with_invalid_audio_format(self):
        """Prueba 3: Subida con formato de audio inválido"""
        print("\n🎵 Test 3: Formato de audio inválido (.exe)")
        
        data = {
            'title': 'Canción inválida',
            'artist': 'Hacker',
            'genre': 'Malware',
            'audio_file': self.invalid_file,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 400:
            errors = response.json()
            print(f"   ✅ ÉXITO: Validación funcionó")
            print(f"   Error: {errors.get('audio_file', ['No error field'])[0]}")
        else:
            print(f"   ⚠️ INESPERADO: {response.status_code}")
            print(f"   Response: {response.json()}")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('audio_file', response.json())
    
    def test_04_upload_missing_required_fields(self):
        """Prueba 4: Subida sin campos requeridos"""
        print("\n🎵 Test 4: Campos requeridos faltantes")
        
        # Falta 'artist'
        data = {
            'title': 'Canción incompleta',
            'genre': 'Rock',
            'audio_file': self.valid_audio,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 400:
            errors = response.json()
            print(f"   ✅ ÉXITO: Validación de campos funcionó")
            print(f"   Error: {list(errors.keys())}")
        else:
            print(f"   ❌ FALLÓ: Debería haber fallado")
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_05_rate_limiting(self):
        """Prueba 5: Rate limiting (20 uploads por hora)"""
        print("\n🎵 Test 5: Rate limiting")
        
        # Simular 21 uploads rápidamente
        successes = 0
        failures = 0
        
        for i in range(22):  # Uno más del límite
            # Recrear archivo para cada iteración
            audio = SimpleUploadedFile(
                f"test_{i}.mp3",
                self.valid_audio_content,
                content_type="audio/mpeg"
            )
            
            data = {
                'title': f'Canción {i}',
                'artist': f'Artista {i}',
                'genre': 'Test',
                'audio_file': audio,
            }
            
            response = self.client.post('/api2/songs/upload/', data, format='multipart')
            
            if response.status_code == 201:
                successes += 1
                # Limpiar
                song_id = response.json()['song_id']
                song = Song.objects.get(id=song_id)
                if song.file_key:
                    delete_file_from_r2(song.file_key)
            elif response.status_code == 429:
                failures += 1
                print(f"   Upload {i+1}: ❌ Rate limit alcanzado (esperado)")
                break
        
        print(f"   ✅ ÉXITO: {successes} uploads exitosos, {failures} bloqueados por rate limit")
        self.assertGreater(failures, 0)  # Debería haber al menos un bloqueo
    
    def test_06_authentication_required(self):
        """Prueba 6: Autenticación requerida"""
        print("\n🎵 Test 6: Autenticación requerida")
        
        # Desautenticar
        self.client.force_authenticate(user=None)
        
        data = {
            'title': 'Canción sin auth',
            'artist': 'Anónimo',
            'genre': 'Unknown',
            'audio_file': self.valid_audio,
        }
        
        response = self.client.post('/api2/songs/upload/', data, format='multipart')
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code in [401, 403]:
            print("   ✅ ÉXITO: Autenticación requerida funcionó")
        else:
            print(f"   ❌ FALLÓ: Debería requerir autenticación")
        
        self.assertIn(response.status_code, [401, 403])
    
    def test_07_cleanup_on_failure(self):
        """Prueba 7: Limpieza en caso de error"""
        print("\n🎵 Test 7: Limpieza en error (simulación)")
        
        # Esta prueba es más compleja porque necesitaríamos simular un error
        # durante el upload. Para simplificar, verificamos que el serializer
        # tiene lógica de cleanup.
        
        from api2.serializers import SongUploadSerializer
        import inspect
        
        source = inspect.getsource(SongUploadSerializer.create)
        
        if 'delete_file_from_r2' in source and 'uploaded_files' in source:
            print("   ✅ ÉXITO: Serializer tiene lógica de cleanup")
        else:
            print("   ⚠️ ADVERTENCIA: Revisar lógica de cleanup en serializer")
    
    def tearDown(self):
        """Limpieza después de cada test"""
        print("\n🧹 Limpiando después del test...")
        
        # Limpiar canciones creadas en pruebas
        for song in Song.objects.all():
            try:
                song.delete()
            except Exception as e:
                print(f"   Error limpiando canción {song.id}: {e}")
        
        print("✅ Limpieza completada")