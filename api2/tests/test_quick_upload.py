# api2/tests/test_quick_upload.py
import os
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()

class TestQuickUpload(TestCase):
    """Test RÁPIDO para debug"""
    
    def setUp(self):
        # Usuario simple
        self.user = User.objects.create_user(
            username='quicktest',
            password='quickpass',
            email='quick@test.com'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    def test_quick_upload_no_image(self):
        """Test rápido sin imagen"""
        print("\n🚀 Test rápido de upload")
        
        # Archivo mínimo
        audio = SimpleUploadedFile(
            'test.mp3',
            b'FAKE MP3' * 10,
            'audio/mpeg'
        )
        
        response = self.client.post(
            '/api2/songs/upload/',
            {
                'audio_file': audio,
                'title': 'Quick Test',
                'artist': 'Quick Artist',
                'is_public': 'true'
            },
            format='multipart'
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 201:
            print(f"✅ Success! Song ID: {response.json().get('song_id')}")
        elif response.status_code == 400:
            print(f"❌ Validation error: {response.json()}")
        elif response.status_code == 500:
            print(f"💥 Server error: {response.json()}")
        
        # Solo verificar que no sea 500
        self.assertNotEqual(response.status_code, 500)