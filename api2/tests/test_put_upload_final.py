# test_put_upload_final.py
import requests
import json

def test_put_upload_final():
    """Test final del sistema PUT"""
    
    print("=" * 60)
    print("🧪 TEST FINAL - UPLOAD VIA PUT")
    print("=" * 60)
    
    # 1. Autenticar
    print("\n1. 🔑 Autenticando...")
    auth = requests.post(
        'http://localhost:8000/musica/api/token/',
        json={'username': 'jordi', 'password': 'machimbo90'}
    )
    
    if auth.status_code != 200:
        print(f"❌ Error de autenticación: {auth.status_code}")
        return
    
    token = auth.json()['access']
    headers = {'Authorization': f'Bearer {token}'}
    print("   ✅ Autenticado")
    
    # 2. Solicitar URL PUT
    print("\n2. 📋 Solicitando URL PUT...")
    response = requests.post(
        'http://localhost:8000/api2/upload/direct/request/',
        json={
            'file_name': 'test_final_put.mp3',
            'file_size': 1024,
            'file_type': 'audio/mpeg'
        },
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ Error del backend: {response.status_code}")
        print(response.text[:500])
        return
    
    data = response.json()
    print(f"   ✅ URL obtenida")
    print(f"   📦 Upload ID: {data.get('upload_id')}")
    print(f"   🔗 Método: {data.get('method', 'POST')}")
    print(f"   📋 Headers: {data.get('headers', {})}")
    
    # Verificar que sea PUT
    if data.get('method') != 'PUT':
        print("❌ ERROR: El método debería ser PUT, no POST")
        print("   Actualiza tu vista DirectUploadRequestView")
        return
    
    # 3. Crear contenido de prueba
    print("\n3. 📄 Creando contenido de prueba...")
    test_content = b'Test audio content for PUT upload' * 30  # ~1KB
    
    # 4. Subir usando PUT
    print("\n4. 🚀 Subiendo con PUT...")
    put_headers = {
        'Content-Type': data['headers']['Content-Type'],
        'Content-Length': data['headers']['Content-Length'],
    }
    
    put_response = requests.put(
        data['upload_url'],
        data=test_content,
        headers=put_headers,
        timeout=30
    )
    
    print(f"   📥 PUT Response: {put_response.status_code}")
    
    if put_response.status_code == 200:
        print("   ✅ ¡PUT exitoso!")
        
        # 5. Confirmar
        print("\n5. ✅ Confirmando upload...")
        confirm_response = requests.post(
            data['confirmation_url'],
            json={'delete_invalid': False},
            headers=headers
        )
        
        print(f"   📋 Confirmación: {confirm_response.status_code}")
        
        if confirm_response.status_code == 200:
            confirm_data = confirm_response.json()
            print(f"   🎉 ¡Upload confirmado!")
            print(f"   🆔 ID: {confirm_data.get('upload_id')}")
            print(f"   🔗 URL estado: {confirm_data.get('check_status_url', 'N/A')}")
        else:
            print(f"   ❌ Error confirmando: {confirm_response.text[:200]}")
    else:
        print(f"   ❌ Error PUT: {put_response.status_code}")
        print(f"   Detalle: {put_response.text[:200]}")
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETADO")
    print("=" * 60)

if __name__ == "__main__":
    test_put_upload_final()