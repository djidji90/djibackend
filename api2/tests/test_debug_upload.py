# debug_upload.py
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from api2.models import Song
from api2.r2_utils import upload_file_to_r2, check_file_exists

User = get_user_model()

def debug_r2_connection():
    """Verificar conexión a R2"""
    print("🔍 Debug R2 Connection")
    
    # Test simple de R2
    test_key = "test_connection.txt"
    test_content = b"Hello R2"
    
    print(f"1. Intentando subir archivo de prueba a R2: {test_key}")
    
    # Crear archivo temporal
    import tempfile
    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
        f.write(test_content)
        temp_path = f.name
    
    try:
        # Intentar subir
        success = upload_file_to_r2(temp_path, test_key)
        print(f"   ✅ Upload success: {success}")
        
        # Verificar que existe
        exists = check_file_exists(test_key)
        print(f"   ✅ File exists in R2: {exists}")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    finally:
        # Limpiar
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def debug_serializer():
    """Debug del serializer"""
    print("\n🔍 Debug Serializer")
    
    from api2.serializers import SongUploadSerializer
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    # Crear datos de prueba
    audio_file = SimpleUploadedFile(
        'debug.mp3',
        b'debug audio content',
        'audio/mpeg'
    )
    
    data = {
        'title': 'Debug Song',
        'artist': 'Debug Artist',
        'audio_file': audio_file,
    }
    
    print(f"1. Creando serializer...")
    
    # Necesitamos un request mock
    from rest_framework.test import APIRequestFactory
    factory = APIRequestFactory()
    request = factory.post('/')
    
    # Crear usuario
    user = User.objects.create_user('debug_user', 'debug@test.com', 'debugpass')
    request.user = user
    
    serializer = SongUploadSerializer(data=data, context={'request': request})
    
    print(f"2. Validando...")
    is_valid = serializer.is_valid()
    print(f"   ✅ Is valid: {is_valid}")
    
    if not is_valid:
        print(f"   ❌ Errors: {serializer.errors}")
        return
    
    print(f"3. Intentando create...")
    try:
        song = serializer.save()
        print(f"   ✅ Song created: {song.id}")
        print(f"   ✅ File key: {song.file_key}")
    except Exception as e:
        print(f"   ❌ Error in create: {e}")

if __name__ == "__main__":
    print("="*60)
    print("🔧 DEBUG UPLOAD SYSTEM")
    print("="*60)
    
    debug_r2_connection()
    debug_serializer()