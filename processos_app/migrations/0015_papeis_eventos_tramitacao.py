"""Bloco A — papéis, eventos de negócio e máquina de estados completa.

Nada é removido aqui. Os campos legados (`tecnico`, `data_saida`,
`hora_saida`, `genero`, `tem_pendencia`, `level`) continuam existindo e
sendo alimentados, para que as telas atuais não quebrem. A remoção fica
para uma migration posterior, depois da conferência dos dados.

`situacao_tramite` dos registros atuais NÃO é reescrita: DISPONIVEL,
EM_ANALISE e AGUARDANDO_ASSINATURA permanecem. Só entram os três
estados novos (ASSINATURA_DIRECIONADA, DISPONIVEL_RETIRADA,
SAIDA_CONCLUIDA), preenchidos daqui pra frente pelas telas novas.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


# ---------------------------------------------------------------------------
# Conversões de dados
# ---------------------------------------------------------------------------

MAPA_NIVEL_PAPEL = {
    '0': 'PROTOCOLO',
    '1': 'ANALISTA_LICITACOES',
    '2': 'ANALISTA_LIQUIDACOES',
    # "Usuário Geral (Todos)" vira Gestão: visão global SEM atos técnicos.
    # Quem de fato analisa deve ser reclassificado nominalmente pela
    # administração, em /manage_users.
    '3': 'GESTAO',
}


def converter_papeis(apps, schema_editor):
    Profile = apps.get_model('processos_app', 'Profile')
    for nivel, papel in MAPA_NIVEL_PAPEL.items():
        Profile.objects.filter(level=nivel).update(papel=papel)


def reverter_papeis(apps, schema_editor):
    pass  # `level` nunca deixou de existir


def preencher_responsavel_tecnico(apps, schema_editor):
    """item 27: o responsável técnico é, normalmente, quem criou a
    pendência. Para os registros já existentes, é a única informação
    verdadeira disponível."""
    Pendencia = apps.get_model('processos_app', 'Pendencia')
    for pendencia in Pendencia.objects.filter(
            responsavel_tecnico__isnull=True).iterator():
        if pendencia.criada_por_id:
            pendencia.responsavel_tecnico_id = pendencia.criada_por_id
            pendencia.save(update_fields=['responsavel_tecnico'])


def nada(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0014_fila_analise_gestao'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # -------------------------------------------------- papel do usuário
        migrations.AddField(
            model_name='profile',
            name='papel',
            field=models.CharField(
                choices=[
                    ('PROTOCOLO', 'Protocolo'),
                    ('ANALISTA_LICITACOES', 'Analista – Licitações e Contratos'),
                    ('ANALISTA_LIQUIDACOES', 'Analista – Liquidações'),
                    ('GESTAO', 'Gestão'),
                ],
                db_index=True,
                default='GESTAO',
                max_length=30,
                verbose_name='Papel operacional',
            ),
        ),
        migrations.RunPython(converter_papeis, reverter_papeis),

        # ------------------------------------------- assinatura e autoria
        migrations.AddField(
            model_name='processo',
            name='assinatura_direcionada_para',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assinaturas_recebidas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Assinatura direcionada para'),
        ),
        migrations.AddField(
            model_name='processo',
            name='assinatura_direcionada_em',
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name='Assinatura direcionada em'),
        ),
        migrations.AddField(
            model_name='processo',
            name='liberado_assinatura_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assinaturas_liberadas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Liberado para assinatura por'),
        ),
        migrations.AddField(
            model_name='processo',
            name='liberado_assinatura_em',
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name='Liberado para assinatura em'),
        ),

        # --------------------------------------- protocolo: retirada e saída
        migrations.AddField(
            model_name='processo',
            name='disponivel_retirada_em',
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name='Disponível para retirada em'),
        ),
        migrations.AddField(
            model_name='processo',
            name='disponivel_retirada_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='processos_disponibilizados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Disponibilizado por'),
        ),
        migrations.AddField(
            model_name='processo',
            name='saida_concluida_em',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Saída concluída em'),
        ),
        migrations.AddField(
            model_name='processo',
            name='saida_concluida_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='saidas_registradas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Saída registrada por'),
        ),

        # ------------------------------------------- cancelamento lógico
        migrations.AddField(
            model_name='processo',
            name='cancelado_em',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Cancelado em'),
        ),
        migrations.AddField(
            model_name='processo',
            name='cancelado_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='processos_cancelados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Cancelado por'),
        ),
        migrations.AddField(
            model_name='processo',
            name='motivo_cancelamento',
            field=models.TextField(
                blank=True, null=True, verbose_name='Motivo do cancelamento'),
        ),

        # ------------------------------------------------ máquina de estados
        # Os valores já gravados (DISPONIVEL, EM_ANALISE, AGUARDANDO_ASSINATURA)
        # não são reescritos. Só se acrescentam os três estados novos.
        migrations.AlterField(
            model_name='processo',
            name='situacao_tramite',
            field=models.CharField(
                choices=[
                    ('DISPONIVEL', 'Disponível para análise'),
                    ('EM_ANALISE', 'Em análise'),
                    ('ASSINATURA_DIRECIONADA', 'Direcionado para assinatura'),
                    ('AGUARDANDO_ASSINATURA', 'Liberado para assinatura'),
                    ('DISPONIVEL_RETIRADA', 'Disponível para retirada'),
                    ('SAIDA_CONCLUIDA', 'Saída concluída'),
                ],
                db_index=True,
                default='DISPONIVEL',
                max_length=30,
                verbose_name='Situação da tramitação',
            ),
        ),

        # ------------------------------------------------------- pendências
        migrations.AddField(
            model_name='pendencia',
            name='status',
            field=models.CharField(
                choices=[
                    ('AGUARDANDO_ATENDIMENTO', 'Aguardando atendimento'),
                    ('ATENDIMENTO_INDICADO', 'Atendimento indicado'),
                    ('RESOLVIDA', 'Resolvida'),
                    ('CANCELADA', 'Cancelada'),
                ],
                db_index=True,
                default='AGUARDANDO_ATENDIMENTO',
                max_length=30,
                verbose_name='Status'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='responsavel_tecnico',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pendencias_sob_responsabilidade',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Responsável técnico'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='atendimento_indicado_em',
            field=models.DateTimeField(
                blank=True, null=True,
                verbose_name='Atendimento indicado em'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='atendimento_indicado_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='atendimentos_indicados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Atendimento indicado por'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='resolvida_em',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Resolvida em'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='resolvida_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pendencias_resolvidas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Resolvida por'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='cancelada_em',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Cancelada em'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='cancelada_por',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pendencias_canceladas',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Cancelada por'),
        ),
        migrations.AddField(
            model_name='pendencia',
            name='motivo_cancelamento',
            field=models.TextField(
                blank=True, null=True, verbose_name='Motivo do cancelamento'),
        ),
        migrations.RunPython(preencher_responsavel_tecnico, nada),

        # ------------------------------------------- eventos de negócio
        migrations.CreateModel(
            name='EventoProcesso',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID')),
                ('tipo', models.CharField(
                    choices=[
                        ('PROCESSO_CADASTRADO', 'Processo cadastrado'),
                        ('PROCESSO_ASSUMIDO', 'Processo assumido'),
                        ('ASSINATURA_DIRECIONADA', 'Assinatura direcionada'),
                        ('ASSINATURA_REDIRECIONADA', 'Assinatura redirecionada'),
                        ('LIBERADO_ASSINATURA', 'Liberado para assinatura'),
                        ('DISPONIVEL_RETIRADA', 'Disponibilizado para retirada'),
                        ('DESTINO_ALTERADO', 'Destino alterado'),
                        ('SAIDA_CONCLUIDA', 'Saída concluída'),
                        ('PRIORIDADE_ALTERADA', 'Prioridade alterada'),
                        ('PROCESSO_CANCELADO', 'Processo cancelado'),
                    ],
                    db_index=True, max_length=40, verbose_name='Evento')),
                ('criado_em', models.DateTimeField(
                    db_index=True, default=django.utils.timezone.now,
                    verbose_name='Data/Hora')),
                ('descricao', models.TextField(
                    blank=True, verbose_name='Descrição')),
                ('dados', models.JSONField(
                    blank=True, default=dict, verbose_name='Dados do evento')),
                ('processo', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='eventos', to='processos_app.processo',
                    verbose_name='Processo')),
                ('usuario', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL, verbose_name='Usuário')),
            ],
            options={
                'verbose_name': 'Evento do Processo',
                'verbose_name_plural': 'Eventos dos Processos',
                'db_table': 'eventos_processo',
                'ordering': ['-criado_em', '-id'],
            },
        ),
        migrations.CreateModel(
            name='EventoPendencia',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID')),
                ('tipo', models.CharField(
                    choices=[
                        ('CRIADA', 'Criada'),
                        ('ATENDIMENTO_INDICADO', 'Atendimento indicado'),
                        ('ATENDIMENTO_INSUFICIENTE', 'Atendimento insuficiente'),
                        ('RESOLVIDA', 'Resolvida'),
                        ('CANCELADA', 'Cancelada'),
                    ],
                    max_length=30, verbose_name='Evento')),
                ('criado_em', models.DateTimeField(
                    default=django.utils.timezone.now,
                    verbose_name='Data/Hora')),
                ('descricao', models.TextField(
                    blank=True, verbose_name='Descrição')),
                ('pendencia', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='eventos', to='processos_app.pendencia',
                    verbose_name='Pendência')),
                ('usuario', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL, verbose_name='Usuário')),
            ],
            options={
                'verbose_name': 'Evento da Pendência',
                'verbose_name_plural': 'Eventos das Pendências',
                'db_table': 'eventos_pendencia',
                'ordering': ['-criado_em', '-id'],
            },
        ),

        # ------------------------------------------------------- índices
        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['situacao_tramite', 'genero'],
                               name='idx_proc_situacao_genero'),
        ),
        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['numero_processo'],
                               name='idx_proc_numero'),
        ),
        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['analista_responsavel'],
                               name='idx_proc_analista'),
        ),
        migrations.AddIndex(
            model_name='processo',
            index=models.Index(fields=['data_entrada'],
                               name='idx_proc_data_entrada'),
        ),
    ]
