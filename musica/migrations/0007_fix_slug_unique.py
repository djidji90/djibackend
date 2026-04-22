from django.db import migrations, models
from django.utils.text import slugify

def generate_unique_slugs(apps, schema_editor):
    CustomUser = apps.get_model('musica', 'CustomUser')
    for user in CustomUser.objects.filter(slug=''):
        base = user.full_name or user.username or f"user-{user.id}"
        user.slug = slugify(base)
        user.save(update_fields=['slug'])
    seen = set()
    for user in CustomUser.objects.all().order_by('date_joined'):
        if not user.slug: continue
        original = user.slug
        counter = 1
        while user.slug in seen:
            user.slug = f"{original}-{counter}"
            counter += 1
        seen.add(user.slug)
        if user.slug != original:
            user.save(update_fields=['slug'])

class Migration(migrations.Migration):
    dependencies = [('musica', '0006_add_seo_fields')]
    operations = [
        migrations.RunPython(generate_unique_slugs, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(model_name='customuser', name='slug', field=models.SlugField(blank=True, max_length=255, unique=True, db_index=True)),
        migrations.AddIndex(model_name='customuser', index=models.Index(fields=['slug'], name='slug_idx')),
    ]