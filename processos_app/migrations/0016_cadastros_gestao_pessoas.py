"""Bloco C — cadastros parametrizáveis e Gestão de Pessoas CGM (itens 19 a 24).

Nada é removido. Os campos texto `secretaria`, `destino`, `especie`,
`genero` e `prioridade` continuam existindo e sendo gravados; as FKs novas
nascem preenchidas a partir do que já está no banco (item 20: migração
gradual e segura).

A conversão não inventa dado:
  - Unidades: as 23 Secretarias que estavam fixas no formulário, mais cada
    texto distinto de `secretaria` já gravado. Destinos NÃO geram cadastro
    (são texto livre); `destino_fk` só é ligado quando o texto coincide com
    uma unidade existente.
  - Espécies: a lista oficial que estava fixa no JavaScript, com a
    periodicidade de monitoramento que o BACKEND aplicava (views.py), que
    é o comportamento real do sistema. Espécies digitadas livremente no
    passado ("Outros") entram INATIVAS, para revisão da Gestão.
  - Prioridades: os prazos que já vigoravam (1, 2 e 7 dias).
  - O que não casar fica com a FK nula e aparece no comando
    `python manage.py sanear_dados`.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


# ---------------------------------------------------------------------------
# Sementes — reproduzem exatamente o comportamento anterior
# ---------------------------------------------------------------------------

PRIORIDADES = [
    # codigo, nome, prazo_dias, ordem
    ('URGENTE', 'Urgente', 1, 10),
    ('PRIORITARIO', 'Prioritário', 2, 20),
    ('NORMAL', 'Normal', 7, 30),
]

TIPOS_INDISPONIBILIDADE = [
    ('Férias formais', 10),
    ('Férias efetivamente usufruídas', 20),
    ('Curso/capacitação', 30),
    ('Ausência/falta', 40),
    ('Outra indisponibilidade', 50),
]

# Lista que estava fixa em templates/Formulario.html (value das options).
SECRETARIAS = [
    'Administração, Receita e Tributação',
    'Agricultura, Abastecimento e Pesca',
    'Comunicação Social',
    'Procuradoria Geral do Município',
    'Desenvolvimento Social',
    'Direitos dos Animais',
    'Educação, Cultura, Inclusão, Ciência e Tecnologia',
    'Esporte, Lazer e Turismo',
    'Finanças',
    'Gabinete',
    'Gestão, Inovação e Tecnologia',
    'Governança e Sustentabilidade',
    'Municipal de Infraestrutura',
    'Meio Ambiente',
    'Mulher',
    'Transporte e Serviços Públicos',
    'Obras Públicas',
    'Planejamento',
    'Relações Institucionais',
    'Saúde',
    'Segurança e Ordem Pública',
    'Transparência e Integridade',
    'Urbanismo',
]

# Lista que estava fixa no JavaScript de Formulario.html.
ESPECIES = {
    'LIQUIDACOES': [
        'Pagamento Geral', 'Concessão Aux. Bolsa Atleta', 'P.C. Bolsa Atleta',
        'Concessão Aux. Aluguel Social', 'Concessão Adiantamento',
        'P.C. Adiantamento', 'Subvenção Social - Concessão',
        'Subvenção Social - Pagamento',
        'Subvenção Social - Prestação de Contas',
        'Subvenção Social - P.C. Anual', 'Subvenção Social - Renovação',
        'Subvenção Bloco Carnaval', 'P.C. Subvenção Bloco Carnaval',
        'Concessão Diária', 'P.C. Patrocínio', 'Reanálise',
    ],
    'LICITACOES_E_CONTRATOS': [
        'Análise Fase Inicial', 'Análise Fase Externa',
        'Dispensa - Análise Fase Externa', 'Inexigibilidade', 'Adesão de Ata',
        'Concessão Patrocínio', 'Análise Aditivo', 'Reanálise',
    ],
}

# Periodicidade aplicada pelo backend (views.salvar_processo e
# views.atualizar_processo). Onde o JavaScript divergia, vale o backend.
MONITORAMENTO_POR_NOME = {
    'P.C. Bolsa Atleta': 'SEMESTRAL',
    'P.C. Adiantamento': 'TRIMESTRAL',
    'Subvenção Social - Prestação de Contas': 'QUADRIMESTRAL',
    'Subvenção Social - P.C. Anual': 'ANUAL',
    'P.C. Subvenção Bloco Carnaval': 'TRIMESTRAL',
    'P.C. Patrocínio': 'TRIMESTRAL',
    'Concessão Aux. Bolsa Atleta': 'TRIMESTRAL',
    'Concessão Aux. Aluguel Social': 'TRIMESTRAL',
    'Concessão Adiantamento': 'TRIMESTRAL',
    'Subvenção Social - Concessão': 'TRIMESTRAL',
    'Concessão Diária': 'TRIMESTRAL',
    'Concessão Patrocínio': 'TRIMESTRAL',
}

# Lista `especies_para_finalizar_automaticamente` de views.salvar_processo:
# a entrada de uma destas encerra o monitoramento pendente das passagens
# anteriores do mesmo número de processo.
ENCERRAM_ANTERIOR = {
    'P.C. Bolsa Atleta', 'Subvenção Social - Prestação de Contas',
    'Subvenção Social - P.C. Anual', 'Concessão Patrocínio',
    'P.C. Adiantamento', 'P.C. Patrocínio', 'P.C. Subvenção Bloco Carnaval',
    'Concessão Aux. Bolsa Atleta', 'Concessão Aux. Aluguel Social',
    'Concessão Adiantamento', 'Subvenção Social - Concessão',
    'Concessão Diária',
}

GRUPOS = ('LICITACOES_E_CONTRATOS', 'LIQUIDACOES')
LEGADO_PRIORIDADE = {'SIM': 'PRIORITARIO', 'NAO': 'NORMAL', 'NÃO': 'NORMAL'}


def _chave(texto):
    return (texto or '').strip().casefold()


def semear(apps, schema_editor):
    Prioridade = apps.get_model('processos_app', 'Prioridade')
    for codigo, nome, prazo, ordem in PRIORIDADES:
        Prioridade.objects.get_or_create(
            codigo=codigo,
            defaults={'nome': nome, 'prazo_dias': prazo, 'ordem': ordem})

    Tipo = apps.get_model('processos_app', 'TipoIndisponibilidade')
    for nome, ordem in TIPOS_INDISPONIBILIDADE:
        Tipo.objects.get_or_create(nome=nome, defaults={'ordem': ordem})

    Unidade = apps.get_model('processos_app', 'UnidadeAdministrativa')
    for ordem, nome in enumerate(SECRETARIAS, start=1):
        Unidade.objects.get_or_create(nome=nome, defaults={'ordem': ordem * 10})

    Especie = apps.get_model('processos_app', 'EspecieProcesso')
    for grupo, nomes in ESPECIES.items():
        for ordem, nome in enumerate(nomes, start=1):
            Especie.objects.get_or_create(
                nome=nome, grupo=grupo,
                defaults={
                    'ordem': ordem * 10,
                    'tipo_monitoramento': MONITORAMENTO_POR_NOME.get(nome, 'NENHUM'),
                    'encerra_monitoramento_anterior': nome in ENCERRAM_ANTERIOR,
                    # O relatório numerado sempre foi gerado para todo
                    # processo de Liquidações ao ser assumido.
                    'gera_relatorio': grupo == 'LIQUIDACOES',
                })


def converter_textos(apps, schema_editor):
    Processo = apps.get_model('processos_app', 'Processo')
    Unidade = apps.get_model('processos_app', 'UnidadeAdministrativa')
    Especie = apps.get_model('processos_app', 'EspecieProcesso')
    Prioridade = apps.get_model('processos_app', 'Prioridade')

    # Unidades: acrescenta cada texto distinto de Secretaria já gravado.
    unidades = {_chave(u.nome): u for u in Unidade.objects.all()}
    proxima_ordem = 1000
    for texto in (Processo.objects.exclude(secretaria__isnull=True)
                  .values_list('secretaria', flat=True).distinct()):
        chave = _chave(texto)
        if chave and chave not in unidades:
            unidades[chave] = Unidade.objects.create(
                nome=texto.strip(), ordem=proxima_ordem)
            proxima_ordem += 10

    # Espécies: pares (grupo, espécie) já gravados e fora da lista oficial
    # entram INATIVOS — foram digitados livremente e precisam de revisão.
    especies = {(e.grupo, _chave(e.nome)): e for e in Especie.objects.all()}
    for grupo, texto in (Processo.objects.filter(genero__in=GRUPOS)
                         .values_list('genero', 'especie').distinct()):
        chave = (grupo, _chave(texto))
        if chave[1] and chave not in especies:
            especies[chave] = Especie.objects.create(
                nome=texto.strip(), grupo=grupo, ativo=False, ordem=1000,
                tipo_monitoramento=MONITORAMENTO_POR_NOME.get(texto.strip(), 'NENHUM'),
                encerra_monitoramento_anterior=texto.strip() in ENCERRAM_ANTERIOR,
                gera_relatorio=grupo == 'LIQUIDACOES')

    prioridades = {p.codigo: p for p in Prioridade.objects.all()}

    lote = []
    campos = ['secretaria_fk', 'destino_fk', 'especie_fk', 'prioridade_fk']
    for processo in Processo.objects.all().iterator(chunk_size=500):
        processo.secretaria_fk = unidades.get(_chave(processo.secretaria))
        processo.destino_fk = unidades.get(_chave(processo.destino))
        processo.especie_fk = especies.get((processo.genero, _chave(processo.especie)))
        codigo = LEGADO_PRIORIDADE.get(processo.prioridade, processo.prioridade)
        processo.prioridade_fk = prioridades.get(codigo)
        lote.append(processo)
        if len(lote) >= 500:
            Processo.objects.bulk_update(lote, campos)
            lote = []
    if lote:
        Processo.objects.bulk_update(lote, campos)


def desfazer_conversao(apps, schema_editor):
    Processo = apps.get_model('processos_app', 'Processo')
    Processo.objects.update(secretaria_fk=None, destino_fk=None,
                            especie_fk=None, prioridade_fk=None)


def nada(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('processos_app', '0015_papeis_eventos_tramitacao'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UnidadeAdministrativa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=255, unique=True,
                                          verbose_name='Nome')),
                ('sigla', models.CharField(blank=True, max_length=30,
                                           verbose_name='Sigla')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('ordem', models.PositiveIntegerField(default=100,
                                                      verbose_name='Ordem')),
            ],
            options={
                'verbose_name': 'Unidade Administrativa',
                'verbose_name_plural': 'Unidades Administrativas',
                'db_table': 'unidades_administrativas',
                'ordering': ['ordem', 'nome'],
            },
        ),
        migrations.CreateModel(
            name='EspecieProcesso',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=255, verbose_name='Nome')),
                ('grupo', models.CharField(
                    choices=[('LICITACOES_E_CONTRATOS', 'Licitações e Contratos'),
                             ('LIQUIDACOES', 'Liquidações')],
                    db_index=True, max_length=30, verbose_name='Grupo')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('ordem', models.PositiveIntegerField(default=100,
                                                      verbose_name='Ordem')),
                ('exige_contratada', models.BooleanField(
                    default=False, verbose_name='Exige contratada/favorecido')),
                ('exige_valor', models.BooleanField(
                    default=False, verbose_name='Exige valor')),
                ('gera_relatorio', models.BooleanField(
                    default=False, verbose_name='Gera número de relatório')),
                ('tipo_monitoramento', models.CharField(
                    choices=[('NENHUM', 'Não gera monitoramento'),
                                                  ('TRIMESTRAL', 'Trimestral'),
                             ('QUADRIMESTRAL', 'Quadrimestral'),
                             ('SEMESTRAL', 'Semestral'),
                             ('ANUAL', 'Anual')],
                    default='NENHUM', max_length=20, verbose_name='Monitoramento')),
                ('encerra_monitoramento_anterior', models.BooleanField(
                    default=False, verbose_name='Encerra monitoramento anterior')),
            ],
            options={
                'verbose_name': 'Espécie de Processo',
                'verbose_name_plural': 'Espécies de Processo',
                'db_table': 'especies_processo',
                'ordering': ['grupo', 'ordem', 'nome'],
                'unique_together': {('nome', 'grupo')},
            },
        ),
        migrations.CreateModel(
            name='Prioridade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=30, unique=True,
                                            verbose_name='Código')),
                ('nome', models.CharField(max_length=100, verbose_name='Nome')),
                ('prazo_dias', models.PositiveIntegerField(verbose_name='Prazo (dias)')),
                ('ordem', models.PositiveIntegerField(default=100,
                                                      verbose_name='Ordem')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
            ],
            options={
                'verbose_name': 'Prioridade',
                'verbose_name_plural': 'Prioridades',
                'db_table': 'prioridades',
                'ordering': ['ordem', 'codigo'],
            },
        ),
        migrations.CreateModel(
            name='TipoIndisponibilidade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, unique=True,
                                          verbose_name='Nome')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('ordem', models.PositiveIntegerField(default=100,
                                                      verbose_name='Ordem')),
            ],
            options={
                'verbose_name': 'Tipo de Indisponibilidade',
                'verbose_name_plural': 'Tipos de Indisponibilidade',
                'db_table': 'tipos_indisponibilidade',
                'ordering': ['ordem', 'nome'],
            },
        ),
        migrations.CreateModel(
            name='Indisponibilidade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('data_inicio', models.DateField(blank=True, null=True,
                                                 verbose_name='Início')),
                ('data_fim', models.DateField(blank=True, null=True,
                                              verbose_name='Fim')),
                ('recorrente', models.BooleanField(default=False,
                                                   verbose_name='Recorrente')),
                ('dia_semana', models.IntegerField(
                    blank=True, null=True,
                    choices=[(0, 'Segunda-feira'), (1, 'Terça-feira'),
                             (2, 'Quarta-feira'), (3, 'Quinta-feira'),
                             (4, 'Sexta-feira'), (5, 'Sábado'), (6, 'Domingo')],
                    verbose_name='Dia da semana')),
                ('vigencia_inicio', models.DateField(
                    blank=True, null=True, verbose_name='Vigência — início')),
                ('vigencia_fim', models.DateField(
                    blank=True, null=True, verbose_name='Vigência — fim')),
                ('observacao', models.TextField(blank=True,
                                                verbose_name='Observação')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('criado_em', models.DateTimeField(
                    default=django.utils.timezone.now,
                    verbose_name='Registrado em')),
                ('criado_por', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='indisponibilidades_registradas',
                    to=settings.AUTH_USER_MODEL, verbose_name='Registrado por')),
                ('tipo', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='registros',
                    to='processos_app.tipoindisponibilidade',
                    verbose_name='Tipo')),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='indisponibilidades',
                    to=settings.AUTH_USER_MODEL, verbose_name='Servidor')),
            ],
            options={
                'verbose_name': 'Indisponibilidade',
                'verbose_name_plural': 'Indisponibilidades',
                'db_table': 'indisponibilidades',
                'ordering': ['-data_inicio', '-criado_em'],
            },
        ),

        # ----------------------------------------------------- FKs no Processo
        migrations.AddField(
            model_name='processo',
            name='secretaria_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='processos_origem',
                to='processos_app.unidadeadministrativa',
                verbose_name='Secretaria de origem'),
        ),
        migrations.AddField(
            model_name='processo',
            name='destino_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='processos_destino',
                to='processos_app.unidadeadministrativa',
                verbose_name='Unidade de destino'),
        ),
        migrations.AddField(
            model_name='processo',
            name='especie_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='processos',
                to='processos_app.especieprocesso',
                verbose_name='Espécie (cadastro)'),
        ),
        migrations.AddField(
            model_name='processo',
            name='prioridade_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='processos',
                to='processos_app.prioridade',
                verbose_name='Prioridade (cadastro)'),
        ),

        migrations.RunPython(semear, nada),
        migrations.RunPython(converter_textos, desfazer_conversao),
    ]
