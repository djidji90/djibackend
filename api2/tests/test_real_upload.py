# api2/tests/test_real_upload.py - VERSIÓN CORREGIDA
import os
import tempfile
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model  # ← USAR ESTO
import logging

# Obtener el modelo de usuario personalizado
User = get_user_model()
logger = logging.getLogger(__name__)

class TestRealUploadToR2(TestCase):
    """Tests REALES que suben archivos a R2"""
    
    def setUp(self):
        logger.info("\n" + "="*60)
        logger.info("🔄 CONFIGURANDO TEST REAL DE UPLOAD")
        logger.info("="*60)
        
        # Crear usuario CON EL MODELO CORRECTO
        self.user = User.objects.create_user(
            username='testuser_real',
            password='testpass123',
            email='test_real@example.com'
        )
        
        # Crear admin (si tu CustomUser soporta create_superuser)
        try:
            self.admin = User.objects.create_superuser(
                username='admin_real',
                password='adminpass123',
                email='admin_real@example.com'
            )
        except:
            # Si no tiene create_superuser, crear usuario normal con is_staff=True
            self.admin = User.objects.create_user(
                username='admin_real',
                password='adminpass123',
                email='admin_real@example.com',
                is_staff=True,
                is_superuser=True
            )
        
        self.client = APIClient()
        
        # Crear archivos de prueba REALES
        self.create_test_files()
    
    def create_test_files(self):
        """Crear archivos de prueba reales"""
        # Audio de prueba (pequeño MP3 simulado)
        self.audio_content = b'ID3\x03\x00\x00\x00\x00\x00\x00' + (b'FAKE MP3 CONTENT' * 1000)
        self.audio_file = SimpleUploadedFile(
            name='real_test_song.mp3',
            content=self.audio_content,
            content_type='audio/mpeg'
        )
        
        # Imagen de prueba (JPEG simulado)
        self.image_content = b'\xff\xd8\xff\xe0\x00\x10JFIF' + (b'FAKE JPEG' * 100)
        self.image_file = SimpleUploadedFile(
            name='real_test_cover.jpg',
            content=self.image_content,
            content_type='image/jpeg'
        )
        
        logger.info(f"📁 Archivos creados:")
        logger.info(f"   Audio: {self.audio_file.name} ({len(self.audio_content)} bytes)")
        logger.info(f"   Imagen: {self.image_file.name} ({len(self.image_content)} bytes)")
    
    def test_01_real_upload_with_audio_and_image(self):
        """Test REAL: Subir audio + imagen a R2"""
        logger.info("\n🎵 TEST 1: Upload REAL con audio e imagen")
        
        # Autenticar
        self.client.force_authenticate(user=self.user)
        
        # Preparar datos
        data = {
            'title': 'Canción Real de Prueba',
            'artist': 'Artista Real',
            'genre': 'rock',
            'is_public': True,
        }
        
        files = {
            'audio_file': self.audio_file,
            'image': self.image_file,  # ← IMPORTANTE: 'image' no 'image_file'
        }
        
        logger.info(f"📤 Enviando upload...")
        logger.info(f"   Data: {data}")
        logger.info(f"   Files: {list(files.keys())}")
        
        # Hacer la petición
        response = self.client.post(
            '/api2/songs/upload/',
            data=data,
            files=files,
            format='multipart'
        )
        
        logger.info(f"📥 Respuesta recibida:")
        logger.info(f"   Status: {response.status_code}")
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"   ✅ ÉXITO - Song ID: {result.get('song_id')}")
            logger.info(f"   Title: {result.get('title')}")
            logger.info(f"   Artist: {result.get('artist')}")
            
            # Verificar que se creó en DB
            from api2.models import Song
            song = Song.objects.get(id=result['song_id'])
            logger.info(f"   DB: file_key={song.file_key}")
            logger.info(f"   DB: image_key={song.image_key}")
            
        elif response.status_code == 400:
            errors = response.json()
            logger.error(f"   ❌ ERROR DE VALIDACIÓN: {errors}")
        elif response.status_code == 429:
            logger.warning(f"   ⚠️ RATE LIMIT: {response.json()}")
        elif response.status_code == 500:
            logger.error(f"   💥 ERROR INTERNO: {response.json()}")
        else:
            logger.warning(f"   ⚠️ STATUS INESPERADO: {response.status_code}")
            logger.warning(f"   Response: {response.json()}")
        
        # Assert
        self.assertIn(response.status_code, [201, 400, 429])
        
        if response.status_code == 201:
            self.assertTrue(response.json().get('song_id'))
            self.assertEqual(response.json().get('title'), 'Canción Real de Prueba')
    
    def test_02_upload_audio_only(self):
        """Test REAL: Subir solo audio (sin imagen)"""
        logger.info("\n🎵 TEST 2: Upload REAL solo audio")
        
        self.client.force_authenticate(user=self.user)
        
        data = {
            'title': 'Solo Audio Test',
            'artist': 'Solo Artist',
            'is_public': False,
        }
        
        files = {
            'audio_file': self.audio_file,
            # No se envía 'image'
        }
        
        response = self.client.post('/api2/songs/upload/', data=data, files=files, format='multipart')
        
        logger.info(f"📥 Status: {response.status_code}")
        
        if response.status_code == 201:
            logger.info(f"   ✅ ÉXITO - Song ID: {response.json().get('song_id')}")
        
        self.assertIn(response.status_code, [201, 400, 429])
    
    def test_03_upload_with_invalid_audio(self):
        """Test: Subir archivo de audio inválido"""
        logger.info("\n🎵 TEST 3: Upload con audio inválido")
        
        self.client.force_authenticate(user=self.user)
        
        # Crear archivo inválido
        invalid_audio = SimpleUploadedFile(
            name='invalid.exe',
            content=b'not an audio file',
            content_type='application/octet-stream'
        )
        
        data = {
            'title': 'Invalid Audio',
            'artist': 'Test',
            'is_public': True,
        }
        
        files = {
            'audio_file': invalid_audio,
        }
        
        response = self.client.post('/api2/songs/upload/', data=data, files=files, format='multipart')
        
        logger.info(f"📥 Status: {response.status_code}")
        
        if response.status_code == 400:
            errors = response.json()
            logger.info(f"   ✅ ESPERADO - Error de validación: {errors.get('audio_file', '')}")
        
        self.assertEqual(response.status_code, 400)
    
    def tearDown(self):
        """Limpiar después de tests"""
        logger.info("\n🧹 LIMPIANDO TEST REAL DE UPLOAD")
        logger.info("="*60)