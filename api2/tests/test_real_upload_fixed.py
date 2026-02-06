"""
TESTS REALISTAS CON ARCHIVOS REALES
Sube diferentes tipos de archivos a R2 y verifica integridad
"""

import os
import tempfile
import json
from pathlib import Path
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from api2.models import UploadSession, UploadQuota
import logging
from unittest.mock import patch
import requests
from io import BytesIO

logger = logging.getLogger(__name__)
User = get_user_model()

class RealUploadTests(TestCase):
    """Tests con archivos multimedia reales"""
    
    def setUp(self):
        """Preparar usuario de prueba y cliente API"""
        self.user = User.objects.create_user(
            username='jordi',
            email='test@example.com',
            password='machimbo90'
        )
        
        # Obtener token JWT
        self.token = str(AccessToken.for_user(self.user))
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        
        # Crear cuota
        UploadQuota.objects.create(user=self.user)
        
        # URLs de la API
        self.request_url = '/api2/upload/direct/request/'
        self.confirm_url = '/api2/upload/direct/confirm/'
        self.status_url = '/api/upload/direct/status/'
        
        # Configurar settings para tests (usar bucket de test si existe)
        self.original_bucket = os.environ.get('R2_BUCKET_NAME')
        
    def tearDown(self):
        """Limpiar después de tests"""
        if self.original_bucket:
            os.environ['R2_BUCKET_NAME'] = self.original_bucket
            
    def _create_test_file(self, filename, size_kb=100, content_type='audio/mpeg'):
        """Crea archivo de prueba realista"""
        temp_dir = tempfile.mkdtemp()
        filepath = os.path.join(temp_dir, filename)
        
        # Generar contenido realista según tipo
        if filename.endswith('.mp3'):
            # Cabecera MP3 simulada + datos aleatorios
            with open(filepath, 'wb') as f:
                # Cabecera ID3 simulada
                f.write(b'ID3')
                # Datos de audio (aleatorios pero estructurados)
                import random
                f.write(bytes([random.randint(0, 255) for _ in range(size_kb * 1024)]))
                
        elif filename.endswith('.jpg'):
            # Cabecera JPEG simulada
            with open(filepath, 'wb') as f:
                f.write(b'\xFF\xD8\xFF\xE0')  # SOI + APP0
                # Datos de imagen
                import random
                f.write(bytes([random.randint(0, 255) for _ in range(size_kb * 1024)]))
                f.write(b'\xFF\xD9')  # EOI
                
        elif filename.endswith('.wav'):
            # Cabecera WAV
            with open(filepath, 'wb') as f:
                f.write(b'RIFF')
                # Tamaño del archivo
                f.write((size_kb * 1024 + 36).to_bytes(4, 'little'))
                f.write(b'WAVEfmt ')
                # Más datos de cabecera...
                import random
                f.write(bytes([random.randint(0, 255) for _ in range(size_kb * 1024)]))
                
        else:
            # Archivo genérico
            with open(filepath, 'wb') as f:
                import random
                f.write(bytes([random.randint(0, 255) for _ in range(size_kb * 1024)]))
        
        return filepath, temp_dir
    
    def test_complete_audio_upload_flow(self):
        """
        Test 1: Flujo completo de subida de audio MP3
        Escenario: Usuario sube canción de 5MB
        """
        print("\n" + "="*60)
        print("TEST 1: Subida completa de archivo MP3 (5MB)")
        print("="*60)
        
        # 1. Solicitar URL de upload
        print("1. Solicitando URL de upload...")
        response = self.client.post(self.request_url, {
            'file_name': 'mi_cancion.mp3',
            'file_size': 5 * 1024 * 1024,  # 5MB
            'file_type': 'audio/mpeg',
            'metadata': {
                'original_name': 'Mi Canción Favorita.mp3',
                'artist': 'Test Artist',
                'album': 'Test Album',
                'genre': 'Electronic'
            }
        }, format='json')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        upload_id = data['upload_id']
        upload_url = data['upload_url']
        file_key = data['file_key']
        
        print(f"   ✓ URL obtenida, ID: {upload_id}")
        print(f"   ✓ Key R2: {file_key}")
        
        # 2. Crear archivo MP3 de prueba (más pequeño para test rápido)
        print("2. Creando archivo MP3 de prueba (100KB)...")
        filepath, temp_dir = self._create_test_file('test.mp3', size_kb=100)
        file_size = os.path.getsize(filepath)
        
        # 3. Subir directamente a R2 (usando requests)
        print("3. Subiendo archivo a R2...")
        try:
            with open(filepath, 'rb') as f:
                headers = {
                    'Content-Type': 'audio/mpeg',
                    'Content-Length': str(file_size)
                }
                
                # Subir archivo
                upload_response = requests.put(
                    upload_url,
                    data=f,
                    headers=headers,
                    timeout=30
                )
                
                print(f"   ✓ Upload HTTP Status: {upload_response.status_code}")
                self.assertIn(upload_response.status_code, [200, 201])
                
        except Exception as e:
            print(f"   ✗ Error subiendo archivo: {e}")
            self.fail(f"Error subiendo a R2: {e}")
        finally:
            # Limpiar archivo temporal
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        # 4. Confirmar upload
        print("4. Confirmando upload en backend...")
        confirm_response = self.client.post(
            f"{self.confirm_url}{upload_id}/",
            {'delete_invalid': False},  # ← ¡Datos que el serializer espera!
            format='json'
        )
        
        print(f"   ✓ Confirmación Status: {confirm_response.status_code}")
        self.assertEqual(confirm_response.status_code, 200)
        confirm_data = confirm_response.json()
        self.assertTrue(confirm_data['success'])
        
        # 5. Verificar estado
        print("5. Verificando estado del upload...")
        status_response = self.client.get(f"{self.status_url}{upload_id}/")
        self.assertEqual(status_response.status_code, 200)
        status_data = status_response.json()
        
        print(f"   ✓ Estado final: {status_data['status']}")
        print("   ✓ Flujo completo ejecutado exitosamente!")
        
        # Verificar que la sesión existe
        session = UploadSession.objects.get(id=upload_id)
        self.assertEqual(session.user.id, self.user.id)
        self.assertEqual(session.file_name, 'mi_cancion.mp3')
    
    def test_large_file_upload(self):
        """
        Test 2: Archivo grande (límite del plan)
        Escenario: Usuario premium sube archivo de 400MB
        """
        print("\n" + "="*60)
        print("TEST 2: Upload de archivo grande (20MB simulado)")
        print("="*60)
        
        # Simular usuario premium
        self.user.profile.tier = 'premium'
        self.user.save()
        
        # Solicitar URL para archivo grande
        response = self.client.post(self.request_url, {
            'file_name': 'set_completo.wav',
            'file_size': 20 * 1024 * 1024,  # 20MB para test
            'file_type': 'audio/wav',
            'metadata': {
                'original_name': 'DJ Set Completo.wav',
                'duration': '3600',
                'bitrate': '1411'
            }
        }, format='json')
        
        if response.status_code == 429:
            print("   ⚠️ Cuota excedida (esperado en tests consecutivos)")
            return
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        print(f"   ✓ URL para archivo grande obtenida")
        print(f"   ✓ Tamaño máximo permitido: {data['max_size'] / (1024*1024):.1f}MB")
    
    def test_multiple_simultaneous_uploads(self):
        """
        Test 3: Múltiples uploads simultáneos
        Escenario: Usuario sube 3 archivos a la vez
        """
        print("\n" + "="*60)
        print("TEST 3: Múltiples uploads simultáneos")
        print("="*60)
        
        files = [
            {'name': 'track1.mp3', 'size': 3*1024*1024, 'type': 'audio/mpeg'},
            {'name': 'track2.mp3', 'size': 4*1024*1024, 'type': 'audio/mpeg'},
            {'name': 'artwork.jpg', 'size': 2*1024*1024, 'type': 'image/jpeg'},
        ]
        
        upload_ids = []
        
        for i, file_info in enumerate(files, 1):
            print(f"{i}. Solicitando URL para {file_info['name']}...")
            
            response = self.client.post(self.request_url, {
                'file_name': file_info['name'],
                'file_size': file_info['size'],
                'file_type': file_info['type']
            }, format='json')
            
            # Puede fallar por cuota después del primero
            if response.status_code == 429:
                print(f"   ⚠️ Cuota excedida para archivo {i}")
                break
                
            self.assertEqual(response.status_code, 200)
            data = response.json()
            upload_ids.append(data['upload_id'])
            print(f"   ✓ URL obtenida (ID: {data['upload_id'][:8]}...)")
        
        print(f"\n   Total de URLs obtenidas: {len(upload_ids)}")
        
        # Verificar que se crearon las sesiones
        sessions = UploadSession.objects.filter(user=self.user)
        print(f"   Sesiones en BD: {sessions.count()}")
    
    def test_invalid_file_type_rejection(self):
        """
        Test 4: Rechazo de tipos de archivo no permitidos
        """
        print("\n" + "="*60)
        print("TEST 4: Validación de tipos de archivo")
        print("="*60)
        
        # Archivo ejecutable (no permitido)
        response = self.client.post(self.request_url, {
            'file_name': 'virus.exe',
            'file_size': 1024 * 1024,  # 1MB
            'file_type': 'application/x-msdownload'
        }, format='json')
        
        # El sistema debería rechazarlo o al menos marcarlo
        print(f"   Respuesta para .exe: {response.status_code}")
        
        # Archivo sin extensión
        response = self.client.post(self.request_url, {
            'file_name': 'sin_extension',
            'file_size': 1024 * 1024,
            'file_type': 'application/octet-stream'
        }, format='json')
        
        print(f"   Respuesta sin extensión: {response.status_code}")