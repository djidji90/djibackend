# test_r2_upload.py
import os
import django
import sys

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tu_proyecto.settings')
django.setup()

from api2.r2_utils import upload_file_to_r2, check_file_exists, delete_file_from_r2
from api2.r2_client import r2_client, R2_BUCKET_NAME
import logging

# Configurar logging para ver detalles
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_r2_connection():
    """Prueba básica de conexión a R2"""
    print("🔍 Probando conexión a R2...")
    
    if not r2_client:
        print("❌ Cliente R2 no inicializado")
        return False
    
    try:
        # Listar buckets (esto prueba la conexión)
        response = r2_client.list_buckets()
        buckets = [b['Name'] for b in response.get('Buckets', [])]
        print(f"✅ Conexión exitosa. Buckets disponibles: {buckets}")
        
        # Verificar que nuestro bucket existe
        if R2_BUCKET_NAME in buckets:
            print(f"✅ Bucket '{R2_BUCKET_NAME}' encontrado")
        else:
            print(f"⚠️ Bucket '{R2_BUCKET_NAME}' NO encontrado")
            print("   Creando bucket...")
            try:
                r2_client.create_bucket(Bucket=R2_BUCKET_NAME)
                print(f"✅ Bucket '{R2_BUCKET_NAME}' creado")
            except Exception as e:
                print(f"❌ Error creando bucket: {e}")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error de conexión R2: {e}")
        print("   Verifica:")
        print("   1. Variables de entorno (R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)")
        print("   2. R2_ACCOUNT_ID correcto")
        print("   3. Internet funcionando")
        return False

def upload_test_files():
    """Sube archivos de prueba reales a R2"""
    print("\n📤 Subiendo archivos de prueba...")
    
    # Ruta a tus archivos REALES - ¡CAMBIAR ESTAS RUTAS!
    audio_path = "/ruta/a/tu/archivo/audio.mp3"  # ¡CAMBIAR!
    image_path = "/ruta/a/tu/archivo/imagen.jpg"  # ¡CAMBIAR!
    
    # Verificar que los archivos existen
    if not os.path.exists(audio_path):
        print(f"❌ Archivo de audio no encontrado: {audio_path}")
        print("   Por favor, especifica la ruta correcta")
        return False
    
    if not os.path.exists(image_path):
        print(f"❌ Archivo de imagen no encontrado: {image_path}")
        print("   Por favor, especifica la ruta correcta")
        return False
    
    # Keys para R2
    audio_key = "test/audio_real.mp3"
    image_key = "test/imagen_real.jpg"
    
    # Subir audio
    print(f"🎵 Subiendo audio: {os.path.basename(audio_path)} → {audio_key}")
    try:
        with open(audio_path, 'rb') as audio_file:
            success = upload_file_to_r2(
                file_obj=audio_file,
                key=audio_key,
                content_type='audio/mpeg'
            )
            
            if success:
                print(f"✅ Audio subido exitosamente")
                
                # Verificar que existe
                exists = check_file_exists(audio_key)
                print(f"   Verificación: {'✅ Existe' if exists else '❌ No encontrado'}")
            else:
                print(f"❌ Falló subida de audio")
                return False
    except Exception as e:
        print(f"💥 Error subiendo audio: {e}")
        return False
    
    # Subir imagen
    print(f"🖼️ Subiendo imagen: {os.path.basename(image_path)} → {image_key}")
    try:
        with open(image_path, 'rb') as image_file:
            success = upload_file_to_r2(
                file_obj=image_file,
                key=image_key,
                content_type='image/jpeg'
            )
            
            if success:
                print(f"✅ Imagen subida exitosamente")
                
                # Verificar que existe
                exists = check_file_exists(image_key)
                print(f"   Verificación: {'✅ Existe' if exists else '❌ No encontrado'}")
            else:
                print(f"❌ Falló subida de imagen")
                return False
    except Exception as e:
        print(f"💥 Error subiendo imagen: {e}")
        return False
    
    print("\n🎉 ¡Archivos subidos exitosamente!")
    print(f"🔗 Puedes verlos en: https://dash.cloudflare.com/")
    print(f"   Navega a: R2 → {R2_BUCKET_NAME} → test/")
    
    return True

def clean_test_files():
    """Limpia los archivos de prueba"""
    print("\n🧹 Limpiando archivos de prueba...")
    
    test_keys = ["test/audio_real.mp3", "test/imagen_real.jpg"]
    
    for key in test_keys:
        try:
            if check_file_exists(key):
                delete_file_from_r2(key)
                print(f"🗑️ Eliminado: {key}")
            else:
                print(f"📭 No existe: {key}")
        except Exception as e:
            print(f"⚠️ Error limpiando {key}: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("TEST DE SUBIDA REAL A R2 CLOUDFLARE")
    print("=" * 60)
    
    # 1. Probar conexión
    if not test_r2_connection():
        print("\n❌ Prueba fallida. No se puede conectar a R2.")
        sys.exit(1)
    
    # 2. Subir archivos
    success = upload_test_files()
    
    if success:
        # 3. Preguntar si limpiar
        print("\n" + "=" * 60)
        respuesta = input("¿Deseas eliminar los archivos de prueba? (s/n): ")
        if respuesta.lower() == 's':
            clean_test_files()
    
    print("\n✨ Prueba completada")