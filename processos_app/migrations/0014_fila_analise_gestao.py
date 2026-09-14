from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrar_prioridade(apps, schema_editor):
    Processo = apps.get_model('processos_app', 'Processo')
    Processo.objects.filter(prioridade='SIM').update(prioridade='PRIORITARIO')
    Processo.objects.filter(prioridade='NAO').update(prioridade='NORMAL')


def reverter_prioridade(apps, schema_editor):
    Processo = apps.get_model('processos_app', 'Processo')
    Processo.objects.filter(prioridade='PRIORITARIO').update(prioridade='SIM')
    Processo.objects.filter(prioridade__in=['NORMAL', 'URGENTE']).update(prioridade='NAO')


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0013_processo_tem_pendencia_pendencia'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='processo',
            name='situacao_tramite',
            field=models.CharField(
                choices=[
                    ('DISPONIVEL', 'Disponível para análise'),
                    ('EM_ANALISE', 'Em análise'),
                    ('AGUARDANDO_ASSINATURA', 'Aguardando assinatura'),
                ],
                default='DISPONIVEL',
                max_length=30,
                verbose_name='Situação da análise',
            ),
        ),
        migrations.AddField(
            model_name='processo',
            name='analista_responsavel',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='processos_em_analise',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Analista responsável',
            ),
        ),
        migrations.AddField(
            model_name='processo',
            name='data_hora_assumido',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Data/hora em que foi assumido',
            ),
        ),
        migrations.AddField(
            model_name='processo',
            name='numero_relatorio',
            field=models.CharField(
                blank=True,
                max_length=50,
                null=True,
                verbose_name='Número do relatório',
            ),
        ),
        migrations.RunPython(migrar_prioridade, reverter_prioridade),
        migrations.AlterField(
            model_name='processo',
            name='prioridade',
            field=models.CharField(
                choices=[
                    ('NORMAL', 'Normal'),
                    ('PRIORITARIO', 'Prioritário'),
                    ('URGENTE', 'Urgente'),
                ],
                default='NORMAL',
                max_length=50,
                verbose_name='Prioridade',
            ),
        ),
        migrations.CreateModel(
            name='SequenciaRelatorio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grupo', models.CharField(max_length=50, unique=True, verbose_name='Grupo')),
                ('proximo_numero', models.PositiveIntegerField(default=1540, verbose_name='Próximo número')),
            ],
            options={
                'verbose_name': 'Sequência de Relatório',
                'verbose_name_plural': 'Sequências de Relatório',
                'db_table': 'sequencia_relatorio',
            },
        ),
    ]
