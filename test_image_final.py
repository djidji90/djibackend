# C:\Users\HP\Desktop\ddjiback\test_image_final.py
"""
Test final de subida de imagen - Versión definitiva
"""

import os
import sys
import django

sys.path.append('C:\\Users\\HP\\Desktop\\ddjiback')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from io import BytesIO
from PIL import Image
import requests
import time
from django.conf import settings

User = get_user_model()

def test_upload():
    print("\n" + "="*60)
    print("TEST FINAL - SUBIDA DE IMAGEN")
    print("="*60)
    
    # Verificar configuración
    print(f"\nALLOWED_HOSTS contiene 'testserver': {'testserver' in settings.ALLOWED_HOSTS}")
    
    # Crear usuario
    print("\n1. Preparando usuario...")
    user, _ = User.objects.get_or_create(
        username='final_test',
        defaults={'email': 'final@test.com'}
    )
    user.set_password('test123')
    user.save()
    print(f"   Usuario: {user.username}")
    
    # Cliente - NO forzar host, dejar que APIClient maneje
    client = APIClient()
    client.force_authenticate(user=user)
    
    # Crear imagen
    print("\n2. Creando imagen...")
    img = Image.new('RGB', (300, 300), color='blue')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG', quality=95)
    img_data = img_bytes.getvalue()
    print(f"   Tamaño: {len(img_data)} bytes")
    
    # Solicitar URL - SIN forzar host
    print("\n3. Solicitando URL de upload...")
    response = client.post(
        '/api2/upload/direct/request/', 
        {
            'file_name': 'final_test.jpg',
            'file_size': len(img_data),
            'file_type': 'image/jpeg',
            'metadata': {
                'title': 'Final Test',
                'type': 'cover_art'
            }
        },
        format='json'
        # NO incluir HTTP_HOST
    )
    
    print(f"   Status code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"   Error: {response.json() if response.content else 'No content'}")
        return
    
    data = response.json()
    print(f"   ✅ Upload ID: {data['upload_id']}")
    print(f"   File Key: {data['file_key']}")
    
    # Subir a R2
    print("\n4. Subiendo imagen a R2...")
    try:
        put_response = requests.put(
            data['upload_url'],
            data=img_data,
            headers={'Content-Type': 'image/jpeg'},
            timeout=30
        )
        print(f"   PUT Status: {put_response.status_code}")
        
        if put_response.status_code in [200, 204]:
            print("   ✅ Imagen subida exitosamente a R2!")
            
            # Confirmar
            print("\n5. Confirmando upload...")
            confirm = client.post(
                f"/api2/upload/direct/confirm/{data['upload_id']}/",
                {'delete_invalid': True},
                format='json'
            )
            print(f"   Confirm Status: {confirm.status_code}")
            
            if confirm.status_code == 200:
                confirm_data = confirm.json()
                print(f"   ✅ Confirmado: {confirm_data.get('status')}")
                
                # Verificar estado
                print("\n6. Verificando estado final...")
                for i in range(5):
                    time.sleep(1)
                    status = client.get(
                        f"/api2/upload/direct/status/{data['upload_id']}/"
                    )
                    status_data = status.json()
                    print(f"   Estado ({i+1}s): {status_data.get('status')}")
                    
                    if status_data.get('status') == 'ready':
                        print("\n   🎉 ÉXITO TOTAL! La imagen se procesó correctamente")
                        if 'song' in status_data:
                            print(f"   ID en DB: {status_data['song']['id']}")
                            print(f"   Título: {status_data['song']['title']}")
                        break
                    elif status_data.get('status') == 'failed':
                        print(f"   ❌ Falló: {status_data.get('status_message')}")
                        break
            else:
                print(f"   ❌ Error en confirmación: {confirm.json()}")
        else:
            print(f"   ❌ PUT falló: {put_response.text}")
            
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ Error de conexión a R2: {e}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    test_upload()