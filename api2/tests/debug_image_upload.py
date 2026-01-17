# debug_image_upload.py
import os
import django
import sys


# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()

# Crear usuario
user = User.objects.create_user(
    username='debug_user',
    password='debug_pass',
    email='debug@test.com'
)

client = APIClient()
client.force_authenticate(user=user)

print("🎵 DEBUG: Upload con imagen")

# Intentar upload con imagen
response = client.post(
    '/api2/songs/upload/',
    {
        'audio_file': SimpleUploadedFile('test.mp3', b'MP3DATA', 'audio/mpeg'),
        'image': SimpleUploadedFile('cover.jpg', b'\xff\xd8JPEG', 'image/jpeg'),
        'title': 'Test Song',
        'artist': 'Test Artist',
        'is_public': 'true',
    },
    format='multipart'
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json() if response.content else 'No content'}")