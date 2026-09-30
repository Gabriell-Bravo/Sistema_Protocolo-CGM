"""Inclui o evento TRAMITE_DESFEITO no histórico do processo."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0021_controle_relatorio'),
    ]

    operations = [
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
                    ('TRAMITE_DESFEITO', 'Tramitação desfeita'),
                    ('ARQUIVO_ANEXADO', 'Arquivo anexado'),
                    ('ARQUIVO_REMOVIDO', 'Arquivo removido'),
                ],
                db_index=True, max_length=40, verbose_name='Evento'),
        ),
    ]
