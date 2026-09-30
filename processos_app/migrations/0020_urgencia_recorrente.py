"""Número de processo cuja próxima entrada já nasce urgente."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('processos_app', '0019_anexo_processo'),
    ]

    operations = [
        migrations.CreateModel(
            name='UrgenciaRecorrente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_processo', models.CharField(max_length=255, unique=True, verbose_name='Número do processo')),
                ('definido_em', models.DateTimeField(auto_now=True, verbose_name='Definido em')),
                ('definido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='urgencias_recorrentes', to=settings.AUTH_USER_MODEL, verbose_name='Definido por')),
            ],
            options={
                'verbose_name': 'Urgência recorrente',
                'verbose_name_plural': 'Urgências recorrentes',
                'db_table': 'urgencias_recorrentes',
            },
        ),
    ]
