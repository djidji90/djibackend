# api2/tests/test_debug_upload.py
import os
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
import json

User = get_user_model()

class TestDebugUpload(TestCase):
    """Test para debuggear problemas específicos"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='debuguser',
            password='debugpass',
            email='debug@test.com'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    def test_debug_mp3_with_jpg(self):
        """Debug: Por qué falla MP3+JPG?"""
        print("\n🔍 DEBUG: MP3 + JPG")
        
        # Crear archivos realistas
        mp3_content = b'ID3\x03\x00' + (b'A' * 1000)
        jpg_content = b'\xff\xd8\xff\xe0' + (b'B' * 500)
        
        audio_file = SimpleUploadedFile(
            'test_song.mp3',
            mp3_content,
            'audio/mpeg'
        )
        
        image_file = SimpleUploadedFile(
            'test_cover.jpg',
            jpg_content,
            'image/jpeg'
        )
        
        # Hacer request
        response = self.client.post(
            '/api2/songs/upload/',
            {
                'audio_file': audio_file,
                'image': image_file,
                'title': 'Debug Song',
                'artist': 'Debug Artist',
                'is_public': 'true'
            },
            format='multipart'
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 400:
            print(f"ERRORES: {json.dumps(response.json(), indent=2)}")
        
        # Pausar para leer
        input("Presiona Enter para continuar...")
    
    def test_debug_wav_only(self):
        """Debug: Solo WAV"""
        print("\n🔍 DEBUG: Solo WAV")
        
        wav_content = b'RIFF' + (b'WAVDATA' * 500)
        
        audio_file = SimpleUploadedFile(
            'test_song.wav',
            wav_content,
            'audio/wav'
        )
        
        response = self.client.post(
            '/api2/songs/upload/',
            {
                'audio_file': audio_file,
                'title': 'WAV Only',
                'artist': 'Test Artist',
                'is_public': 'true'
            },
            format='multipart'
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 400:
            print(f"ERRORES: {json.dumps(response.json(), indent=2)}")
        
        input("Presiona Enter para continuar...")