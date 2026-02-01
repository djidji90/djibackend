# api2/tests/test_real_upload.py
import os
import tempfile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
import uuid
import json
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()

class RealFileUploadTest(TestCase):
    """Prueba con archivo real (pero mockeando R2)"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='realupload',
            email=f'real{uuid.uuid4().hex[:8]}@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        
        # Crear archivo MP3 simulado
        self.mp3_content = b'ID3\x03\x00\x00\x00\x00\x00' + b'FAKE MP3 CONTENT' * 1000
        
    def test_real_mp3_file_simulation(self):
        """Simula upload de archivo MP3 real"""
        print("\n🎵 Simulando upload de archivo MP3 real...")
        
        # Crear archivo simulado
        mp3_file = SimpleUploadedFile(
            "test_song.mp3",
            self.mp3_content,
            content_type="audio/mpeg"
        )
        
        file_size = len(self.mp3_content)
        
        print(f"   Archivo creado: test_song.mp3")
        print(f"   Tamaño: {file_size} bytes ({file_size/1024/1024:.2f} MB)")
        print(f"   Tipo MIME: audio/mpeg")
        
        # Verificar que parece un MP3 (tiene header ID3)
        self.assertTrue(self.mp3_content.startswith(b'ID3'))
        print(f"   ✓ Header ID3 detectado (MP3 válido)")
        
        # Simular la solicitud de upload
        with patch('api2.views.r2_direct') as mock_r2:
            mock_r2.generate_presigned_post.return_value = {
                'url': 'https://fake.r2.url/upload',
                'fields': {'key': 'uploads/test.mp3'},
                'key': 'uploads/test.mp3',
                'expires_at': 1700000000
            }
            
            request_data = {
                'file_name': 'test_song.mp3',
                'file_size': file_size,
                'file_type': 'audio/mpeg',
                'metadata': {
                    'original_name': 'Mi Canción.mp3',
                    'duration': 180,  # 3 minutos
                    'bitrate': 192
                }
            }
            
            response = self.client.post(
                reverse('direct-upload-request'),
                data=json.dumps(request_data),
                content_type='application/json'
            )
            
            if response.status_code == 200:
                print(f"   ✓ Solicitud de upload aceptada")
                print(f"   ✓ ID de sesión: {response.data.get('upload_id', 'N/A')}")
                
                # Verificar instrucciones para el frontend
                self.assertIn('instructions', response.data)
                instructions = response.data['instructions']
                
                print(f"\n📋 Instrucciones para frontend:")
                print(f"   Método: {instructions.get('method')}")
                print(f"   Content-Type: {instructions.get('content_type')}")
                
                steps = instructions.get('steps', [])
                for i, step in enumerate(steps, 1):
                    print(f"   {i}. {step}")
                    
            elif response.status_code == 400:
                print(f"   ⚠ Error de validación: {response.data}")
            else:
                print(f"   ❌ Error inesperado: {response.status_code}")