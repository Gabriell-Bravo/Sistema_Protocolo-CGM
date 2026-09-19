# processos_app/models.py
from django.db import models
from datetime import datetime, date, timedelta
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User


class Processo(models.Model):
    PRIORIDADE_CHOICES = [
        ('NORMAL', 'Normal'),
        ('PRIORITARIO', 'Prioritário'),
        ('URGENTE', 'Urgente'),
    ]

    # Nomes antigos (DISPONIVEL / AGUARDANDO_ASSINATURA) permanecem no banco.
    # A tela mostra o texto novo. Os três estados que não existiam entram
    # com o nome do Bloco A e só nascem de ação nova.
    SITUACAO_TRAMITE_CHOICES = [
        ('DISPONIVEL', 'Disponível para análise'),
        ('EM_ANALISE', 'Em análise'),
        ('ASSINATURA_DIRECIONADA', 'Direcionado para assinatura'),
        ('AGUARDANDO_ASSINATURA', 'Liberado para assinatura'),
        ('DISPONIVEL_RETIRADA', 'Disponível para retirada'),
        ('SAIDA_CONCLUIDA', 'Saída concluída'),
    ]

    # Estados em que o processo ainda está fisicamente na CGM (item 58).
    SITUACOES_ATIVAS = (
        'DISPONIVEL',
        'EM_ANALISE',
        'ASSINATURA_DIRECIONADA',
        'AGUARDANDO_ASSINATURA',
        'DISPONIVEL_RETIRADA',
    )

    PENDENCIA_CHOICES = [
        ('SIM', 'SIM'),
        ('NAO', 'NÃO'),
    ]

    MONITORAMENTO_CHOICES = [
        ('SEMESTRAL', 'Semestral'),
        ('QUADRIMESTRAL', 'Quadrimestral'),
        ('ANUAL', 'Anual'),
        ('TRIMESTRAL', 'Trimestral'),
        # Para processos que não requerem monitoramento
        ('NAO_APLICAVEL', 'Não Aplicável'),
    ]

    STATUS_MONITORAMENTO_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('CONCLUIDO', 'Concluído'),
        ('ATRASADO', 'Atrasado'),
        ('NAO_APLICAVEL', 'Não Aplicável'),
    ]

    # NEW STATUS_ANALISE_CHOICES
    STATUS_ANALISE_CHOICES = [
        ('PROSSEGUIMENTO_SEM_RESSALVA', 'Prosseguimento sem ressalva'),
        ('PROSSEGUIMENTO_COM_RESSALVA', 'Prosseguimento com ressalva'),
        ('NAO_PROSSEGUIMENTO', 'Não Prosseguimento'),
        ('DEVOLUCAO_PARA_SANEAMENTO', 'Devolução para saneamento'),
        ('NAO_APLICAVEL', 'Não Aplicável'),
    ]

    numero_processo = models.CharField(
        max_length=255, verbose_name="Número de Processo")
    volume = models.CharField(
        max_length=255, verbose_name="Volume")
    secretaria = models.CharField(max_length=255, verbose_name="Secretaria")
    data_entrada = models.DateField(verbose_name="Data de Entrada")
    hora_entrada = models.TimeField(verbose_name="Hora de Entrada")
    data_saida = models.DateField(
        null=True, blank=True, verbose_name="Data de Saída")
    hora_saida = models.TimeField(
        null=True, blank=True, verbose_name="Hora de Saída")
    destino = models.CharField(
        max_length=255, null=True, blank=True, verbose_name="Destino")

    genero = models.CharField(max_length=255, verbose_name="Gênero")
    especie = models.CharField(max_length=255, verbose_name="Espécie")

    objeto = models.TextField(verbose_name="Objeto")
    contratada = models.CharField(
        max_length=255, null=True, blank=True, verbose_name="Contratada/Interessada")
    # item 54: valor interno SIM/NAO, sem acento; rótulo Sim/Não. Antes o
    # valor padrão era 'NÃO' (com acento) e o formulário gravava 'NAO' — os
    # dois conviviam no banco. A migration 0017 normaliza o histórico.
    recorrente = models.CharField(
        max_length=3,
        default='NAO',
        choices=[('SIM', 'Sim'), ('NAO', 'Não')],
        verbose_name="Recorrente"
    )
    prioridade = models.CharField(
        max_length=50,
        choices=PRIORIDADE_CHOICES,
        default='NORMAL',
        verbose_name="Prioridade"
    )
    situacao_tramite = models.CharField(
        max_length=30,
        choices=SITUACAO_TRAMITE_CHOICES,
        default='DISPONIVEL',
        db_index=True,
        verbose_name="Situação da tramitação"
    )
    analista_responsavel = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processos_em_analise',
        verbose_name="Analista responsável"
    )
    data_hora_assumido = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Data/hora em que foi assumido"
    )
    numero_relatorio = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Número do relatório"
    )

    # --- Assinatura (itens 7, 8, 10 e 11) --------------------------------
    # analista_responsavel continua representando QUEM ANALISOU. Nunca é
    # sobrescrito por assinatura substitutiva.
    assinatura_direcionada_para = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assinaturas_recebidas',
        verbose_name="Assinatura direcionada para"
    )
    assinatura_direcionada_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Assinatura direcionada em")
    liberado_assinatura_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assinaturas_liberadas',
        verbose_name="Liberado para assinatura por"
    )
    liberado_assinatura_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Liberado para assinatura em")

    # --- Protocolo: retorno físico e saída (itens 13 e 15) ---------------
    disponivel_retirada_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Disponível para retirada em")
    disponivel_retirada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processos_disponibilizados',
        verbose_name="Disponibilizado por"
    )
    saida_concluida_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Saída concluída em")
    saida_concluida_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saidas_registradas',
        verbose_name="Saída registrada por"
    )

    # --- Cadastros parametrizáveis (itens 19 a 22) -----------------------
    # Convivem com os campos texto legados (secretaria, destino, especie,
    # genero, prioridade), que continuam sendo gravados em paralelo até a
    # remoção posterior (item 60). PROTECT: cadastro usado não se apaga,
    # inativa-se (item 19).
    secretaria_fk = models.ForeignKey(
        'UnidadeAdministrativa', on_delete=models.PROTECT, null=True,
        blank=True, related_name='processos_origem',
        verbose_name="Secretaria de origem")
    destino_fk = models.ForeignKey(
        'UnidadeAdministrativa', on_delete=models.PROTECT, null=True,
        blank=True, related_name='processos_destino',
        verbose_name="Unidade de destino")
    especie_fk = models.ForeignKey(
        'EspecieProcesso', on_delete=models.PROTECT, null=True, blank=True,
        related_name='processos', verbose_name="Espécie (cadastro)")
    prioridade_fk = models.ForeignKey(
        'Prioridade', on_delete=models.PROTECT, null=True, blank=True,
        related_name='processos', verbose_name="Prioridade (cadastro)")

    # --- Cancelamento lógico (item 35) -----------------------------------
    cancelado_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Cancelado em")
    cancelado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processos_cancelados',
        verbose_name="Cancelado por"
    )
    motivo_cancelamento = models.TextField(
        null=True, blank=True, verbose_name="Motivo do cancelamento")
    prazo_dias = models.IntegerField(
        null=True, blank=True, verbose_name="Prazo em Dias")

    tecnico = models.CharField(
        null=True, blank=True, max_length=255, verbose_name="Técnico Responsável Análise")
    data_analise = models.DateField(
        null=True, blank=True, verbose_name="Data da Análise")
    numero_despacho = models.CharField(
        null=True, blank=True, max_length=255, verbose_name="Controle do N° de Despacho")
    observacao = models.TextField(
        null=True, blank=True, verbose_name="Observação")
    aviso_enviado = models.IntegerField(
        default=0, verbose_name="Aviso Enviado")

    # NOVOS CAMPOS PARA MONITORAMENTO
    prazo_monitoramento = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=MONITORAMENTO_CHOICES,
        verbose_name="Prazo de Monitoramento"
    )
    proxima_data_monitoramento = models.DateField(
        null=True,
        blank=True,
        verbose_name="Próxima Data de Monitoramento"
    )
    status_monitoramento = models.CharField(
        max_length=20,
        default='NAO_APLICAVEL',
        choices=STATUS_MONITORAMENTO_CHOICES,
        verbose_name="Status de Monitoramento"
    )

    # NEW FIELDS: Valor, Periodo, Status
    valor = models.CharField(max_length=255, null=True,
                             blank=True, verbose_name="Valor")
    periodo = models.CharField(
        max_length=255, null=True, blank=True, verbose_name="Período")
    status_analise = models.CharField(
        max_length=50,
        choices=STATUS_ANALISE_CHOICES,
        default='NAO_APLICAVEL',
        verbose_name="Status da Análise"
    )

    tem_pendencia = models.CharField(
        max_length=3,
        default='NAO',
        choices=PENDENCIA_CHOICES,
        verbose_name="Tem Pendência"
    )

    GENERO_LABELS = {
        'LICITACOES_E_CONTRATOS': 'Licitações e Contratos',
        'LIQUIDACOES': 'Liquidações',
        'OUTROS_GENERO': 'Outros',
    }

    def __str__(self):
        return self.numero_processo

    @property
    def genero_display(self):
        return self.GENERO_LABELS.get(self.genero, self.genero)

    @property
    def prioridade_display(self):
        labels = {
            'NORMAL': 'Normal',
            'PRIORITARIO': 'Prioritário',
            'URGENTE': 'Urgente',
            'SIM': 'Prioritário',
            'NAO': 'Normal',
        }
        if self.prioridade in labels:
            return labels[self.prioridade]
        # item 22: código criado no cadastro de Prioridades
        if self.prioridade_fk_id:
            return self.prioridade_fk.nome
        return self.get_prioridade_display()

    @property
    def prioridade_badge_class(self):
        if self.prioridade == 'URGENTE':
            return 'badge--danger'
        if self.prioridade in ('PRIORITARIO', 'SIM'):
            return 'badge--warning'
        return ''

    @property
    def grupo(self):
        """item 21: o grupo vem da espécie cadastrada. O texto `genero` é o
        valor legado, usado enquanto a espécie não estiver vinculada."""
        if self.especie_fk_id and self.especie_fk.grupo:
            return self.especie_fk.grupo
        return self.genero

    @property
    def esta_cancelado(self):
        return self.cancelado_em is not None

    @property
    def esta_ativo(self):
        """item 58: ativo é o que não saiu e não foi cancelado.

        `data_saida` entra só como compatibilidade: registros anteriores à
        nova tramitação têm a saída gravada ali, sem SAIDA_CONCLUIDA.
        """
        return (not self.esta_cancelado
                and self.situacao_tramite in self.SITUACOES_ATIVAS
                and self.data_saida is None)

    @property
    def tem_pendencia_aberta(self):
        """item 31: calculado a partir dos registros reais, não alimentado."""
        return self.pendencias.filter(
            status__in=Pendencia.STATUS_ABERTOS).exists()

    @property
    def nome_assinatura_direcionada(self):
        if self.assinatura_direcionada_para:
            return (self.assinatura_direcionada_para.get_full_name()
                    or self.assinatura_direcionada_para.username)
        return ''

    @property
    def nome_analista(self):
        if self.analista_responsavel:
            return (
                self.analista_responsavel.get_full_name()
                or self.analista_responsavel.username
            )
        return self.tecnico or ''

    class Meta:
        db_table = 'processos'
        verbose_name_plural = "Processos"
        indexes = [
            models.Index(fields=['situacao_tramite', 'genero'],
                         name='idx_proc_situacao_genero'),
            models.Index(fields=['numero_processo'],
                         name='idx_proc_numero'),
            models.Index(fields=['analista_responsavel'],
                         name='idx_proc_analista'),
            models.Index(fields=['data_entrada'],
                         name='idx_proc_data_entrada'),
            # item 57 (migration 0017)
            models.Index(fields=['data_saida'], name='idx_proc_data_saida'),
            models.Index(fields=['saida_concluida_em'], name='idx_proc_saida_concluida'),
            models.Index(fields=['liberado_assinatura_em'], name='idx_proc_liberado_em'),
            models.Index(fields=['cancelado_em'], name='idx_proc_cancelado_em'),
        ]


class ProcessHistory(models.Model):
    process = models.ForeignKey(
        Processo, on_delete=models.CASCADE, verbose_name="Processo")
    field_name = models.CharField(max_length=255, verbose_name="Campo")
    old_value = models.TextField(
        null=True, blank=True, verbose_name="Valor Antigo")
    new_value = models.TextField(
        null=True, blank=True, verbose_name="Novo Valor")
    changed_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Data/Hora da Mudança")
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Alterado Por")

    def __str__(self):
        return f"Histórico de {self.process.numero_processo} - {self.field_name}"

    @property
    def changed_at_formatted(self):
        return self.changed_at.strftime("%d/%m/%Y %H:%M:%S")

    class Meta:
        db_table = 'process_history'
        verbose_name = "Histórico do Processo"
        verbose_name_plural = "Histórico dos Processos"


class MonitoramentoRecord(models.Model):
    processo = models.ForeignKey(Processo, on_delete=models.CASCADE,
                                 related_name='monitoramento_registros', verbose_name="Processo")
    data_registro = models.DateField(
        auto_now_add=True, verbose_name="Data do Registro")
    observacao = models.TextField(
        blank=True, null=True, verbose_name="Observação")
    registrado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Registrado Por")

    def __str__(self):
        return f"Monitoramento de {self.processo.numero_processo} em {self.data_registro.strftime('%d/%m/%Y')}"

    class Meta:
        db_table = 'monitoramento_registros'
        verbose_name = "Registro de Monitoramento"
        verbose_name_plural = "Registros de Monitoramento"

class Pendencia(models.Model):
    STATUS_CHOICES = [
        ('AGUARDANDO_ATENDIMENTO', 'Aguardando atendimento'),
        ('ATENDIMENTO_INDICADO', 'Atendimento indicado'),
        ('RESOLVIDA', 'Resolvida'),
        ('CANCELADA', 'Cancelada'),
    ]

    STATUS_ABERTOS = ('AGUARDANDO_ATENDIMENTO', 'ATENDIMENTO_INDICADO')

    processo = models.ForeignKey(
        Processo, on_delete=models.CASCADE, related_name='pendencias', verbose_name="Processo")
    descricao = models.TextField(verbose_name="Descrição da Pendência")
    criada_em = models.DateTimeField(
        auto_now_add=True, verbose_name="Criada em")
    criada_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Criada Por")

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='AGUARDANDO_ATENDIMENTO',
        db_index=True,
        verbose_name="Status"
    )
    # item 27: permanece mesmo que o processo mude de estado ou já tenha
    # saído fisicamente da CGM.
    responsavel_tecnico = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pendencias_sob_responsabilidade',
        verbose_name="Responsável técnico"
    )
    atendimento_indicado_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Atendimento indicado em")
    atendimento_indicado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='atendimentos_indicados',
        verbose_name="Atendimento indicado por"
    )
    resolvida_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Resolvida em")
    resolvida_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pendencias_resolvidas',
        verbose_name="Resolvida por"
    )
    cancelada_em = models.DateTimeField(
        null=True, blank=True, verbose_name="Cancelada em")
    cancelada_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pendencias_canceladas',
        verbose_name="Cancelada por"
    )
    motivo_cancelamento = models.TextField(
        null=True, blank=True, verbose_name="Motivo do cancelamento")

    def __str__(self):
        return f"Pendência de {self.processo.numero_processo}"

    @property
    def esta_aberta(self):
        return self.status in self.STATUS_ABERTOS

    @property
    def dias_decorridos(self):
        """item 28: tempo decorrido, calculado, não alimentado."""
        return (timezone.now() - self.criada_em).days

    @property
    def criada_em_formatted(self):
        return self.criada_em.strftime("%d/%m/%Y %H:%M")

    class Meta:
        db_table = 'pendencias'
        ordering = ['criada_em']
        verbose_name = "Pendência"
        verbose_name_plural = "Pendências"
        indexes = [
            # item 57: fila de Diligências e "Atendimentos indicados"
            models.Index(fields=['status', 'responsavel_tecnico'],
                         name='idx_pend_status_resp'),
        ]


class EventoProcesso(models.Model):
    """Histórico de atos administrativos do processo (item 45).

    Não substitui ProcessHistory, que registra o diff campo a campo.
    Aqui fica o ATO: quem fez, o que fez, quando.
    """

    TIPO_CHOICES = [
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
    ]

    processo = models.ForeignKey(
        Processo, on_delete=models.CASCADE, related_name='eventos',
        verbose_name="Processo")
    tipo = models.CharField(
        max_length=40, choices=TIPO_CHOICES, db_index=True,
        verbose_name="Evento")
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Usuário")
    criado_em = models.DateTimeField(
        default=timezone.now, db_index=True, verbose_name="Data/Hora")
    descricao = models.TextField(blank=True, verbose_name="Descrição")
    dados = models.JSONField(
        default=dict, blank=True, verbose_name="Dados do evento")

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.processo.numero_processo}"

    @property
    def criado_em_formatted(self):
        return timezone.localtime(self.criado_em).strftime("%d/%m/%Y %H:%M")

    class Meta:
        db_table = 'eventos_processo'
        ordering = ['-criado_em', '-id']
        verbose_name = "Evento do Processo"
        verbose_name_plural = "Eventos dos Processos"


class EventoPendencia(models.Model):
    """item 46: apenas os atos formais. Telefonema, e-mail e cobrança
    intermediária não são registrados."""

    TIPO_CHOICES = [
        ('CRIADA', 'Criada'),
        ('ATENDIMENTO_INDICADO', 'Atendimento indicado'),
        ('ATENDIMENTO_INSUFICIENTE', 'Atendimento insuficiente'),
        ('RESOLVIDA', 'Resolvida'),
        ('CANCELADA', 'Cancelada'),
    ]

    pendencia = models.ForeignKey(
        Pendencia, on_delete=models.CASCADE, related_name='eventos',
        verbose_name="Pendência")
    tipo = models.CharField(
        max_length=30, choices=TIPO_CHOICES, verbose_name="Evento")
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Usuário")
    criado_em = models.DateTimeField(
        default=timezone.now, verbose_name="Data/Hora")
    descricao = models.TextField(blank=True, verbose_name="Descrição")

    def __str__(self):
        return f"{self.get_tipo_display()} — pendência {self.pendencia_id}"

    class Meta:
        db_table = 'eventos_pendencia'
        ordering = ['-criado_em', '-id']
        verbose_name = "Evento da Pendência"
        verbose_name_plural = "Eventos das Pendências"


class SequenciaRelatorio(models.Model):
    grupo = models.CharField(max_length=50, unique=True, verbose_name="Grupo")
    proximo_numero = models.PositiveIntegerField(
        default=1540, verbose_name="Próximo número")

    def __str__(self):
        return f"{self.grupo} → {self.proximo_numero}"

    class Meta:
        db_table = 'sequencia_relatorio'
        verbose_name = "Sequência de Relatório"
        verbose_name_plural = "Sequências de Relatório"


# ---------------------------------------------------------------------------
# Cadastros parametrizáveis (itens 19 a 22)
# ---------------------------------------------------------------------------
# Tiram as listas fixas do HTML, do JavaScript e do Python. Cadastro usado
# historicamente não é excluído: é inativado (campo `ativo`).


class UnidadeAdministrativa(models.Model):
    """item 20: a mesma entidade serve à Secretaria de origem e ao destino."""

    nome = models.CharField(max_length=255, unique=True, verbose_name="Nome")
    sigla = models.CharField(max_length=30, blank=True, verbose_name="Sigla")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    ordem = models.PositiveIntegerField(default=100, verbose_name="Ordem")

    def __str__(self):
        return self.nome

    class Meta:
        db_table = 'unidades_administrativas'
        ordering = ['ordem', 'nome']
        verbose_name = "Unidade Administrativa"
        verbose_name_plural = "Unidades Administrativas"


class EspecieProcesso(models.Model):
    """item 21: a espécie determina o grupo e a regra de monitoramento."""

    GRUPO_CHOICES = [
        ('LICITACOES_E_CONTRATOS', 'Licitações e Contratos'),
        ('LIQUIDACOES', 'Liquidações'),
    ]

    TIPO_MONITORAMENTO_CHOICES = [
        ('NENHUM', 'Não gera monitoramento'),
        ('TRIMESTRAL', 'Trimestral'),
        ('QUADRIMESTRAL', 'Quadrimestral'),
        ('SEMESTRAL', 'Semestral'),
        ('ANUAL', 'Anual'),
    ]

    # Meses de calendário de cada periodicidade (item 41: relativedelta,
    # nunca múltiplos de 30 dias).
    MESES_POR_TIPO = {
        'TRIMESTRAL': 3,
        'QUADRIMESTRAL': 4,
        'SEMESTRAL': 6,
        'ANUAL': 12,
    }

    nome = models.CharField(max_length=255, verbose_name="Nome")
    grupo = models.CharField(
        max_length=30, choices=GRUPO_CHOICES, db_index=True,
        verbose_name="Grupo")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    ordem = models.PositiveIntegerField(default=100, verbose_name="Ordem")
    exige_contratada = models.BooleanField(
        default=False, verbose_name="Exige contratada/favorecido")
    exige_valor = models.BooleanField(
        default=False, verbose_name="Exige valor")
    gera_relatorio = models.BooleanField(
        default=False, verbose_name="Gera número de relatório")
    tipo_monitoramento = models.CharField(
        max_length=20, choices=TIPO_MONITORAMENTO_CHOICES, default='NENHUM',
        verbose_name="Monitoramento")
    encerra_monitoramento_anterior = models.BooleanField(
        default=False, verbose_name="Encerra monitoramento anterior")

    def __str__(self):
        return self.nome

    @property
    def meses_monitoramento(self):
        return self.MESES_POR_TIPO.get(self.tipo_monitoramento)

    class Meta:
        db_table = 'especies_processo'
        ordering = ['grupo', 'ordem', 'nome']
        unique_together = [('nome', 'grupo')]
        verbose_name = "Espécie de Processo"
        verbose_name_plural = "Espécies de Processo"


class Prioridade(models.Model):
    """item 22: prazo por prioridade sai do código e vira cadastro.

    A política de contagem (dias corridos x úteis, recontagem) continua
    pendente de definição administrativa (item 66). Aqui fica só o número
    de dias de cada prioridade.
    """

    codigo = models.CharField(max_length=30, unique=True, verbose_name="Código")
    nome = models.CharField(max_length=100, verbose_name="Nome")
    prazo_dias = models.PositiveIntegerField(verbose_name="Prazo (dias)")
    ordem = models.PositiveIntegerField(default=100, verbose_name="Ordem")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    def __str__(self):
        return self.nome

    class Meta:
        db_table = 'prioridades'
        ordering = ['ordem', 'codigo']
        verbose_name = "Prioridade"
        verbose_name_plural = "Prioridades"


class TipoIndisponibilidade(models.Model):
    """itens 19 e 23: tipos usados pelo módulo Gestão de Pessoas CGM."""

    nome = models.CharField(max_length=100, unique=True, verbose_name="Nome")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    ordem = models.PositiveIntegerField(default=100, verbose_name="Ordem")

    def __str__(self):
        return self.nome

    class Meta:
        db_table = 'tipos_indisponibilidade'
        ordering = ['ordem', 'nome']
        verbose_name = "Tipo de Indisponibilidade"
        verbose_name_plural = "Tipos de Indisponibilidade"


class Indisponibilidade(models.Model):
    """item 23: Gestão de Pessoas CGM.

    Finalidade estritamente operacional: a disponibilidade real da equipe.
    Não é sistema de RH, folha ou gestão funcional.

    Cobre os quatro casos do documento:
      - dia único                -> data_inicio (data_fim igual ou vazia)
      - período                  -> data_inicio .. data_fim
      - recorrente               -> recorrente=True + dia_semana
      - recorrente com vigência  -> + vigencia_inicio / vigencia_fim
    """

    DIAS_SEMANA = [
        (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
        (3, 'Quinta-feira'), (4, 'Sexta-feira'), (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    usuario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='indisponibilidades',
        verbose_name="Servidor")
    tipo = models.ForeignKey(
        TipoIndisponibilidade, on_delete=models.PROTECT,
        related_name='registros', verbose_name="Tipo")
    data_inicio = models.DateField(null=True, blank=True, verbose_name="Início")
    data_fim = models.DateField(null=True, blank=True, verbose_name="Fim")
    recorrente = models.BooleanField(default=False, verbose_name="Recorrente")
    dia_semana = models.IntegerField(
        choices=DIAS_SEMANA, null=True, blank=True,
        verbose_name="Dia da semana")
    vigencia_inicio = models.DateField(
        null=True, blank=True, verbose_name="Vigência — início")
    vigencia_fim = models.DateField(
        null=True, blank=True, verbose_name="Vigência — fim")
    observacao = models.TextField(blank=True, verbose_name="Observação")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    criado_em = models.DateTimeField(
        default=timezone.now, verbose_name="Registrado em")
    criado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='indisponibilidades_registradas',
        verbose_name="Registrado por")

    def __str__(self):
        return f'{self.usuario} — {self.tipo}'

    def vale_em(self, dia):
        """A indisponibilidade se aplica nesta data?"""
        if not self.ativo:
            return False
        if self.recorrente:
            if self.dia_semana is None or dia.weekday() != self.dia_semana:
                return False
            if self.vigencia_inicio and dia < self.vigencia_inicio:
                return False
            if self.vigencia_fim and dia > self.vigencia_fim:
                return False
            return True
        if not self.data_inicio:
            return False
        fim = self.data_fim or self.data_inicio
        return self.data_inicio <= dia <= fim

    def descricao_para(self, dia):
        """Rótulo curto, como no documento: 'Curso hoje', 'Férias até 30/09'."""
        if self.recorrente:
            return f'{self.tipo} (toda {self.get_dia_semana_display().lower()})'
        fim = self.data_fim or self.data_inicio
        if fim and fim > dia:
            return f'{self.tipo} até {fim.strftime("%d/%m")}'
        return f'{self.tipo} hoje'

    class Meta:
        db_table = 'indisponibilidades'
        ordering = ['-data_inicio', '-criado_em']
        verbose_name = "Indisponibilidade"
        verbose_name_plural = "Indisponibilidades"


# NEW PROFILE MODEL


class Profile(models.Model):
    # Códigos numéricos legados. Mantidos apenas durante a transição:
    # o campo `papel` é a fonte de verdade a partir da migration 0015.
    USER_LEVEL_CHOICES = [
        ('0', 'Protocolo'),
        ('1', 'Analista 1 (Licitações e Contratos)'),
        ('2', 'Analista 2 (Liquidações)'),
        ('3', 'Usuário Geral (Todos)'),
    ]

    PAPEL_CHOICES = [
        ('PROTOCOLO', 'Protocolo'),
        ('ANALISTA_LICITACOES', 'Analista – Licitações e Contratos'),
        ('ANALISTA_LIQUIDACOES', 'Analista – Liquidações'),
        ('GESTAO', 'Gestão'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    level = models.CharField(
        max_length=1, choices=USER_LEVEL_CHOICES, default='3')
    papel = models.CharField(
        max_length=30,
        choices=PAPEL_CHOICES,
        default='GESTAO',
        db_index=True,
        verbose_name="Papel operacional"
    )

    def __str__(self):
        return f'{self.user.username} — {self.get_papel_display()}'

# Signal to create or update user profile when a User is created/updated


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Garante Profile para todo User, inclusive os criados fora do fluxo
    normal (createsuperuser, shell, fixtures)."""
    Profile.objects.get_or_create(user=instance)
