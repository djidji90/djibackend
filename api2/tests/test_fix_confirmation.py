

def test_complete_audio_upload_flow(self):
    """
    Test 1: Flujo completo de subida de audio MP3
    Escenario: Usuario sube canción de 5MB
    """
    print("\n" + "="*60)
    print("TEST 1: Subida completa de archivo MP3 (5MB) - CON DEBUG")
    print("="*60)
    
    # Debug: Verificar usuario autenticado
    print(f"🔍 DEBUG: Usuario autenticado: {self.user.id} - {self.user.username}")
    
    # 1. Solicitar URL de upload
    print("1. Solicitando URL de upload...")
    
    # Debug: Verificar headers de autenticación
    print(f"🔍 DEBUG: Headers auth: {self.client._credentials}")
    
    response = self.client.post(self.request_url, {
        'file_name': 'mi_cancion.mp3',
        'file_size': 5 * 1024 * 1024,  # 5MB
        'file_type': 'audio/mpeg',
        'metadata': {
            'original_name': 'Mi Canción Favorita.mp3',
            'artist': 'Test Artist',
            'album': 'Test Album',
            'genre': 'Electronic',
            'test': True  # Para identificación
        }
    }, format='json')
    
    print(f"🔍 DEBUG: Status solicitud URL: {response.status_code}")
    print(f"🔍 DEBUG: Respuesta: {response.json()}")
    
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertTrue(data['success'])
    
    upload_id = data['upload_id']
    upload_url = data['upload_url']
    file_key = data['file_key']
    
    print(f"   ✓ URL obtenida, ID: {upload_id}")
    print(f"   ✓ Key R2: {file_key}")
    print(f"🔍 DEBUG: confirmation_url en respuesta: {data.get('confirmation_url', 'NO ENCONTRADA')}")
    
    # 2. Crear archivo MP3 de prueba (más pequeño para test rápido)
    print("\n2. Creando archivo MP3 de prueba (100KB)...")
    filepath, temp_dir = self._create_test_file('test.mp3', size_kb=100)
    file_size = os.path.getsize(filepath)
    print(f"🔍 DEBUG: Archivo creado: {filepath}, tamaño: {file_size} bytes")
    
    # 3. Subir directamente a R2 (usando requests)
    print("\n3. Subiendo archivo a R2...")
    try:
        with open(filepath, 'rb') as f:
            headers = {
                'Content-Type': 'audio/mpeg',
                'Content-Length': str(file_size)
            }
            
            print(f"🔍 DEBUG: Subiendo a URL: {upload_url[:100]}...")
            print(f"🔍 DEBUG: Headers: {headers}")
            
            # Subir archivo
            upload_response = requests.put(
                upload_url,
                data=f,
                headers=headers,
                timeout=30
            )
            
            print(f"🔍 DEBUG: Status upload R2: {upload_response.status_code}")
            print(f"🔍 DEBUG: Headers respuesta R2: {dict(upload_response.headers)}")
            
            print(f"   ✓ Upload HTTP Status: {upload_response.status_code}")
            self.assertIn(upload_response.status_code, [200, 201, 204])
            
    except Exception as e:
        print(f"   ✗ Error subiendo archivo: {e}")
        import traceback
        traceback.print_exc()
        self.fail(f"Error subiendo a R2: {e}")
    finally:
        # Limpiar archivo temporal
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("🔍 DEBUG: Archivo temporal eliminado")
    
    # 4. Confirmar upload - CON DEBUG DETALLADO
    print("\n4. Confirmando upload en backend...")
    
    # Construir URL de confirmación
    confirmation_url = f"{self.confirm_url}{upload_id}/"
    print(f"🔍 DEBUG: URL de confirmación: {confirmation_url}")
    print(f"🔍 DEBUG: upload_id: {upload_id}")
    
    # Verificar que upload_id es un UUID válido
    import uuid
    try:
        uuid_obj = uuid.UUID(upload_id)
        print(f"🔍 DEBUG: UUID válido: {uuid_obj}")
    except ValueError:
        print(f"❌ ERROR: upload_id NO es un UUID válido: {upload_id}")
        print(f"❌ upload_id debe ser algo como: 12345678-1234-1234-1234-123456789abc")
    
    # Debug: Verificar que la sesión existe en BD antes de confirmar
    try:
        from musica.models import UploadSession
        session = UploadSession.objects.get(id=upload_id)
        print(f"🔍 DEBUG: Sesión encontrada en BD:")
        print(f"  - ID: {session.id}")
        print(f"  - Estado: {session.status}")
        print(f"  - File Key: {session.file_key}")
        print(f"  - can_confirm: {session.can_confirm}")
        print(f"  - is_expired: {session.is_expired}")
    except UploadSession.DoesNotExist:
        print("❌ ERROR: Sesión NO encontrada en BD")
        print("❌ Esto explica el 404 - la sesión no existe")
    
    # Intentar confirmar
    print(f"🔍 DEBUG: Enviando POST a: {confirmation_url}")
    print(f"🔍 DEBUG: Datos enviados: {{'delete_invalid': False}}")
    
    confirm_response = self.client.post(
        confirmation_url,
        {'delete_invalid': False},
        format='json'
    )
    
    print(f"🔍 DEBUG: Status confirmación: {confirm_response.status_code}")
    print(f"🔍 DEBUG: Headers respuesta: {dict(confirm_response.headers)}")
    
    if confirm_response.status_code != 200:
        print(f"🔍 DEBUG: Respuesta completa (error):")
        try:
            error_data = confirm_response.json()
            print(f"  Error: {error_data.get('error', 'No error field')}")
            print(f"  Message: {error_data.get('message', 'No message')}")
            print(f"  Details: {error_data}")
        except:
            print(f"  Raw response: {confirm_response.content}")
    
    print(f"   ✓ Confirmación Status: {confirm_response.status_code}")
    
    # Si es 404, debug adicional de routing
    if confirm_response.status_code == 404:
        print("\n🔍 DEBUG ADICIONAL PARA 404:")
        print("1. Verificando routing...")
        
        # Usar reverse para ver si la URL existe
        try:
            from django.urls import reverse, NoReverseMatch
            reverse_url = reverse('direct-upload-confirm', args=[upload_id])
            print(f"   ✅ reverse funciona: {reverse_url}")
            
            # Verificar que coincida con nuestra URL
            expected_url = f"/api2/upload/direct/confirm/{upload_id}/"
            if reverse_url == expected_url:
                print(f"   ✅ URLs coinciden")
            else:
                print(f"   ❌ URLs NO coinciden:")
                print(f"     reverse: {reverse_url}")
                print(f"     nuestra: {expected_url}")
        except NoReverseMatch:
            print(f"   ❌ reverse NO encuentra la URL")
            print(f"   ❌ El nombre 'direct-upload-confirm' no está registrado")
        except Exception as e:
            print(f"   ⚠️ Error usando reverse: {e}")
    
    self.assertEqual(confirm_response.status_code, 200)
    confirm_data = confirm_response.json()
    self.assertTrue(confirm_data['success'])
    
    # 5. Verificar estado
    print("\n5. Verificando estado del upload...")
    
    # Pequeña pausa para procesamiento
    import time
    time.sleep(2)
    
    status_response = self.client.get(f"{self.status_url}{upload_id}/")
    print(f"🔍 DEBUG: Status check: {status_response.status_code}")
    
    if status_response.status_code == 200:
        status_data = status_response.json()
        print(f"🔍 DEBUG: Estado actual: {status_data.get('status')}")
        print(f"🔍 DEBUG: can_confirm: {status_data.get('can_confirm')}")
        print(f"🔍 DEBUG: file_in_r2: {status_data.get('file_in_r2')}")
    
    self.assertEqual(status_response.status_code, 200)
    status_data = status_response.json()
    
    print(f"   ✓ Estado final: {status_data['status']}")
    print("   ✓ Flujo completo ejecutado exitosamente!")
    
    # Verificar que la sesión existe
    session = UploadSession.objects.get(id=upload_id)
    self.assertEqual(session.user.id, self.user.id)
    self.assertEqual(session.file_name, 'mi_cancion.mp3')
    
    print("\n" + "="*60)
    print("✅ TEST COMPLETADO CON DEBUG")
    print("="*60)