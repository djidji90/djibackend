# musica/migrations/0007_fix_slug_unique.py
from django.db import migrations, models
from django.utils.text import slugify


def generate_unique_slugs(apps, schema_editor):
    CustomUser = apps.get_model('musica', 'CustomUser')
    
    total = CustomUser.objects.count()
    print(f"\n🚀 Corrigiendo slugs para {total} usuarios...")
    
    # 1. Asignar slugs vacíos
    empty_fixed = 0
    for user in CustomUser.objects.filter(slug=''):
        # Usar first_name + last_name o username (campos reales)
        if user.first_name and user.last_name:
            base = f"{user.first_name} {user.last_name}"
        elif user.first_name:
            base = user.first_name
        elif user.last_name:
            base = user.last_name
        else:
            base = user.username or f"user-{user.id}"
        
        user.slug = slugify(base)
        user.save(update_fields=['slug'])
        empty_fixed += 1
    
    if empty_fixed > 0:
        print(f"   📝 {empty_fixed} slugs vacíos corregidos")
    
    # 2. Resolver duplicados
    seen = set()
    duplicates_fixed = 0
    
    for user in CustomUser.objects.all().order_by('date_joined'):
        if not user.slug:
            continue
            
        original_slug = user.slug
        counter = 1
        
        while user.slug in seen:
            user.slug = f"{original_slug}-{counter}"
            counter += 1
            duplicates_fixed += 1
        
        seen.add(user.slug)
        
        if user.slug != original_slug:
            user.save(update_fields=['slug'])
    
    if duplicates_fixed > 0:
        print(f"   🔄 {duplicates_fixed} slugs duplicados resueltos")
    
    print("✅ Slugs corregidos correctamente.")


def reverse_slugs(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('musica', '0006_add_seo_fields'),
    ]
    operations = [
        migrations.RunPython(generate_unique_slugs, reverse_code=reverse_slugs),
        migrations.AlterField(
            model_name='customuser',
            name='slug',
            field=models.SlugField(
                blank=True,
                max_length=255,
                unique=True,
                db_index=True,
                help_text='Identificador unico para la URL del perfil',
            ),
        ),
        migrations.AddIndex(
            model_name='customuser',
            index=models.Index(fields=['slug'], name='musica_slug_idx'),
        ),
    ]