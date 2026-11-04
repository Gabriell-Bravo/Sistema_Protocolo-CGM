import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def continuar_do_historico(apps, schema_editor):
    """Quem já gerou memorandos continua do número seguinte ao maior de cada ano."""
    Memorando = apps.get_model('lai', 'MemorandoFalabr')
    Numeracao = apps.get_model('lai', 'NumeracaoMemorando')
    for ano in Memorando.objects.values_list('ano', flat=True).distinct():
        maior = Memorando.objects.filter(ano=ano).order_by('-numero').values_list('numero', flat=True).first()
        Numeracao.objects.get_or_create(ano=ano, defaults={'proximo': (maior or 0) + 1})


class Migration(migrations.Migration):

    dependencies = [
        ('lai', '0005_memorando_falabr'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NumeracaoMemorando',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ano', models.PositiveIntegerField(unique=True)),
                ('proximo', models.PositiveIntegerField(default=1)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('atualizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(continuar_do_historico, migrations.RunPython.noop),
    ]
