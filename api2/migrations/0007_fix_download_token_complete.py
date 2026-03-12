from django.db import migrations, models
import secrets

def assign_unique_tokens(apps, schema_editor):
    """Asigna tokens únicos a todas las descargas existentes"""
    Download = apps.get_model('api2', 'Download')
    
    total = Download.objects.count()
    if total > 0:
        print(f"Asignando tokens únicos a {total} descargas...")
        
        for download in Download.objects.all():
            download.download_token = secrets.token_urlsafe(32)
            download.save(update_fields=['download_token'])
        
        print("✅ Tokens asignados correctamente")

class Migration(migrations.Migration):
    dependencies = [
        ('api2', '0006_download_download_token_download_is_confirmed_and_more'),
    ]

    operations = [
        migrations.RunPython(assign_unique_tokens),
        migrations.AlterField(
            model_name='download',
            name='download_token',
            field=models.CharField(max_length=64, unique=True),
        ),
    ]