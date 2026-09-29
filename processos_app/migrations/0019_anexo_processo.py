"""Arquivos anexados ao processo de Licitações e Contratos."""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import processos_app.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('processos_app', '0018_analise_declinada'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnexoProcesso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('arquivo', models.FileField(upload_to=processos_app.models._caminho_anexo, verbose_name='Arquivo')),
                ('nome_original', models.CharField(max_length=255, verbose_name='Nome original')),
                ('tamanho', models.PositiveIntegerField(default=0, verbose_name='Tamanho (bytes)')),
                ('enviado_em', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Enviado em')),
                ('enviado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='anexos_enviados', to=settings.AUTH_USER_MODEL, verbose_name='Enviado por')),
                ('processo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='anexos', to='processos_app.processo', verbose_name='Processo')),
            ],
            options={
                'verbose_name': 'Anexo do Processo',
                'verbose_name_plural': 'Anexos do Processo',
                'db_table': 'anexos_processo',
                'ordering': ['-enviado_em', '-id'],
            },
        ),
        migrations.AlterField(
            model_name='eventoprocesso',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('PROCESSO_CADASTRADO', 'Processo cadastrado'),
                    ('PROCESSO_ASSUMIDO', 'Processo assumido'),
                    ('ANALISE_DECLINADA', 'Análise declinada'),
                    ('ASSINATURA_DIRECIONADA', 'Assinatura direcionada'),
                    ('ASSINATURA_REDIRECIONADA', 'Assinatura redirecionada'),
                    ('LIBERADO_ASSINATURA', 'Liberado para assinatura'),
                    ('DISPONIVEL_RETIRADA', 'Disponibilizado para retirada'),
                    ('DESTINO_ALTERADO', 'Destino alterado'),
                    ('SAIDA_CONCLUIDA', 'Saída concluída'),
                    ('PRIORIDADE_ALTERADA', 'Prioridade alterada'),
                    ('PROCESSO_CANCELADO', 'Processo cancelado'),
                    ('ARQUIVO_ANEXADO', 'Arquivo anexado'),
                    ('ARQUIVO_REMOVIDO', 'Arquivo removido'),
                ],
                db_index=True, max_length=40, verbose_name='Evento'),
        ),
    ]
