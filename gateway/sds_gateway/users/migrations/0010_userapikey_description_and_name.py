from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_alter_user_is_approved'),
    ]

    operations = [
        migrations.AddField(
            model_name='userapikey',
            name='description',
            field=models.TextField(blank=True, default='', help_text='Optional description for this API key.'),
        ),
        migrations.AlterField(
            model_name='userapikey',
            name='name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
