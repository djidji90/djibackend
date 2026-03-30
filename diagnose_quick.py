# C:\Users\HP\Desktop\ddjiback\diagnose_quick.py - Versión con imagen más grande
"""
Script de diagnóstico rápido - Subida de imágenes
Versión con imagen de tamaño suficiente
"""

import os
import sys

# Agregar directorio actual al path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

try:
    import django
    django.setup()
    print("✅ Django configurado correctamente")
except Exception as e:
    print(f"❌ Error configurando Django: {e}")
    sys.exit(1)

# Ahora importar lo necesario
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from io import BytesIO
from PIL import Image
import requests
import json
import time

User = get_user_model()

def quick_diagnose():
    print("\n" + "="*60)
    print("DIAGNÓSTICO RÁPIDO - SUBIDA DE IMÁGENES A R2")
    print("="*60)
    
    # Verificar modelo de usuario
    print(f"\n📋 Modelo de usuario: {User.__module__}.{User.__name__}")
    
    # Crear usuario de prueba
    print("\n👤 Creando usuario de prueba...")
    try:
        user, created = User.objects.get_or_create(
            username='quick_diagnostic',
            defaults={
                'email': 'quick@test.com'
            }
        )
        user.set_password('testpass123')
        user.save()
        print(f"✅ Usuario: {user.username} (ID: {user.id})")
    except Exception as e:
        print(f"❌ Error creando usuario: {e}")
        return
    
    # Crear cliente autenticado
    client = APIClient()
    client.force_authenticate(user=user)
    
    # Crear imagen de prueba - MÁS GRANDE (mínimo 1024 bytes)
    print("\n📸 Creando imagen de prueba...")
    # Usar una imagen más grande (200x200 en lugar de 100x100)
    img = Image.new('RGB', (200, 200), color='red')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG', quality=95)  # Calidad alta
    img_data = img_bytes.getvalue()
    print(f"   Tamaño: {len(img_data)} bytes")
    print(f"   Tipo: image/jpeg")
    
    # Verificar que cumple el mínimo
    if len(img_data) < 1024:
        # Si aún es pequeña, hacerla más grande
        img = Image.new('RGB', (300, 300), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG', quality=95)
        img_data = img_bytes.getvalue()
        print(f"   Nuevo tamaño (300x300): {len(img_data)} bytes")
    
    # Solicitar URL de upload
    print("\n📤 Solicitando URL de upload...")
    request_data = {
        'file_name': 'diagnostic_image.jpg',
        'file_size': len(img_data),
        'file_type': 'image/jpeg',
        'metadata': {
            'test': True,
            'timestamp': str(time.time()),
            'title': 'Diagnostic Image',
            'type': 'cover_art'
        }
    }
    
    print(f"   Tamaño enviado: {len(img_data)} bytes")
    
    try:
        response = client.post(
            '/api2/upload/direct/request/', 
            request_data,
            format='json',
            HTTP_HOST='localhost'
        )
        print(f"\n   Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ RESPUESTA EXITOSA!")
            print(json.dumps(data, indent=2, default=str))
            
            # Verificar si la key incluye 'images'
            file_key = data.get('file_key', '')
            if 'images' in file_key:
                print("\n   ✅ CORRECTO: El file_key incluye 'images'")
            else:
                print(f"\n   ⚠️ ATENCIÓN: El file_key NO incluye 'images': {file_key}")
            
            # Intentar subir a R2
            print("\n☁️ Subiendo imagen a R2...")
            try:
                put_response = requests.put(
                    data['upload_url'],
                    data=img_data,
                    headers={
                        'Content-Type': 'image/jpeg',
                        'Content-Length': str(len(img_data))
                    },
                    timeout=30
                )
                print(f"   PUT Status: {put_response.status_code}")
                
                if put_response.status_code in [200, 204]:
                    print("   ✅ Imagen subida exitosamente a R2")
                    
                    # Confirmar upload
                    print("\n✅ Confirmando upload...")
                    confirm_response = client.post(
                        f"/api2/upload/direct/confirm/{data['upload_id']}/",
                        {'delete_invalid': True},
                        format='json',
                        HTTP_HOST='localhost'
                    )
                    print(f"   Confirm Status: {confirm_response.status_code}")
                    
                    try:
                        confirm_data = confirm_response.json()
                        print(f"   Confirm Response: {json.dumps(confirm_data, indent=2)}")
                        
                        if confirm_response.status_code == 200:
                            # Verificar estado
                            print("\n📊 Verificando estado final...")
                            for i in range(5):
                                time.sleep(1)
                                status_response = client.get(
                                    f"/api2/upload/direct/status/{data['upload_id']}/",
                                    HTTP_HOST='localhost'
                                )
                                status_data = status_response.json()
                                print(f"   Estado ({i+1}s): {status_data.get('status')}")
                                
                                if status_data.get('status') == 'ready':
                                    print("   ✅ Procesamiento completado!")
                                    if 'song' in status_data:
                                        print(f"   📝 Canción creada: {status_data['song']['title']}")
                                    break
                                elif status_data.get('status') == 'failed':
                                    print(f"   ❌ Procesamiento falló: {status_data.get('status_message')}")
                                    break
                                elif status_data.get('status') == 'processing':
                                    print("   ⏳ Procesando...")
                    except Exception as e:
                        print(f"   Error: {e}")
                else:
                    print(f"   ❌ PUT falló: {put_response.text}")
                    
            except Exception as e:
                print(f"   ❌ Error en PUT: {str(e)}")
                
        else:
            print(f"\n❌ ERROR EN RESPUESTA (Status {response.status_code}):")
            print(json.dumps(response.json(), indent=2))
            
    except Exception as e:
        print(f"❌ Error en solicitud: {str(e)}")
    
    print("\n" + "="*60)
    print("DIAGNÓSTICO COMPLETADO")
    print("="*60)

if __name__ == "__main__":
    quick_diagnose()