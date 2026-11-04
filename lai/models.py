import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .storage import private_storage

USER = settings.AUTH_USER_MODEL

class Importacao(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(USER, on_delete=models.PROTECT)
    arquivo = models.FileField(upload_to='lai/importacoes/', storage=private_storage)
    nome = models.CharField(max_length=240)
    dados = models.JSONField(default=dict)
    criado_em = models.DateTimeField(auto_now_add=True)
    utilizada = models.BooleanField(default=False)

class Secretaria(models.Model):
    nome = models.CharField(max_length=180)
    sigla = models.CharField(max_length=25)
    email = models.EmailField()
    responsavel = models.CharField(max_length=180, blank=True)
    substituto = models.CharField(max_length=180, blank=True)
    ativa = models.BooleanField(default=True)
    referencia_externa = models.CharField(max_length=100, blank=True)
    def __str__(self): return self.nome
    class Meta: ordering = ['nome']

class Operador(models.Model):
    usuario = models.OneToOneField(USER, on_delete=models.PROTECT)
    nome = models.CharField(max_length=180)
    cargo = models.CharField(max_length=180)
    matricula = models.CharField(max_length=50, blank=True)
    unidade = models.CharField(max_length=180, default='Controladoria-Geral do Município')
    email = models.EmailField()
    ativo = models.BooleanField(default=True)
    secretarias = models.ManyToManyField(Secretaria, blank=True)
    acesso_global = models.BooleanField(default=False)
    autoridade_recursal = models.BooleanField(default=False)
    def __str__(self): return self.nome

class PoliticaPrazo(models.Model):
    versao = models.CharField(max_length=80, unique=True)
    dias_uteis = models.BooleanField(default=False)
    ajustar_vencimento = models.BooleanField(default=False)
    feriados = models.JSONField(default=list, help_text='Lista ISO: ["2026-12-25"]')
    homologada = models.BooleanField(default=False)
    fundamento = models.TextField(blank=True)
    alerta_inicial = models.PositiveSmallIntegerField(default=10)
    alerta_urgente = models.PositiveSmallIntegerField(default=19)
    alerta_prorrogacao = models.PositiveSmallIntegerField(default=8)
    def __str__(self): return self.versao
    def clean(self):
        from datetime import date
        try:
            if not isinstance(self.feriados, list): raise ValueError()
            for d in self.feriados: date.fromisoformat(d)
        except (ValueError, TypeError): raise ValidationError('Feriados devem ser uma lista de datas ISO.')
    def save(self, *args, **kwargs):
        if self.pk and self.demandas.exists():
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(old, f.name) != getattr(self, f.name) for f in self._meta.fields if f.name != 'id'):
                raise ValidationError('Política em uso é imutável. Crie uma nova versão.')
        super().save(*args, **kwargs)

class Demanda(models.Model):
    STATUS = [('CONFERENCIA', 'Aguardando conferência'), ('CADASTRADA', 'Cadastrada'),
        ('AGUARDANDO', 'Aguardando secretaria'), ('COMPLEMENTACAO', 'Em complementação'),
        ('RESPOSTA_INTERNA', 'Aguardando registro no Fala.BR'), ('RESPONDIDA', 'Respondida no Fala.BR'), ('ARQUIVADA', 'Arquivada')]
    nup = models.CharField(max_length=40)
    nup_normalizada = models.CharField(max_length=30, unique=True, editable=False)
    tipo = models.CharField(max_length=180)
    cadastro_falabr = models.DateField()
    marco_inicial = models.DateField()
    vencimento_original = models.DateField()
    prazo_interno = models.DateField()
    teor = models.TextField()
    resumo = models.TextField()
    secretaria = models.ForeignKey(Secretaria, on_delete=models.PROTECT)
    operador = models.ForeignKey(Operador, on_delete=models.PROTECT)
    politica = models.ForeignKey(PoliticaPrazo, on_delete=models.PROTECT, related_name='demandas')
    status = models.CharField(max_length=24, choices=STATUS, default='CONFERENCIA')
    pessoal = models.BooleanField(default=True)
    grau_sigilo = models.CharField(max_length=50, blank=True)
    anexos_esperados = models.JSONField(default=list, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    conferido_em = models.DateTimeField(null=True, blank=True)
    motivo_conferencia = models.TextField(blank=True)
    ciclo = models.PositiveIntegerField(default=1)
    auto_cobranca = models.BooleanField(default=False)
    autorizacao_automacao = models.TextField(blank=True)
    respondida_em = models.DateField(null=True, blank=True)
    class Meta:
        ordering = ['vencimento_original', '-id']
        permissions = [('operar', 'Cadastrar e tratar demandas LAI'), ('expedir', 'Expedir memorandos LAI'),
            ('prorrogar', 'Formalizar prorrogação LAI'), ('recorrer', 'Registrar recursos LAI'),
            ('decidir', 'Registrar decisões recursais LAI'), ('gestao', 'Acompanhar gestão LAI'),
            ('cadastrar', 'Gerenciar cadastros LAI')]
    def save(self, *args, **kwargs):
        import re
        self.nup_normalizada = re.sub(r'\D', '', self.nup)
        super().save(*args, **kwargs)
    @property
    def vencimento(self):
        prorrogacao = self.prorrogacoes.order_by('-id').first()
        return prorrogacao.novo_prazo if prorrogacao else self.vencimento_original
    @property
    def encerrada(self): return self.status in ('RESPONDIDA', 'ARQUIVADA')
    @property
    def precisa_resposta_interna(self): return self.status in ('CADASTRADA', 'AGUARDANDO', 'COMPLEMENTACAO')
    @property
    def dias_restantes(self): return (self.vencimento - timezone.localdate()).days
    def __str__(self): return self.nup

class Documento(models.Model):
    CATEGORIAS = [('NUP', 'PDF da NUP'), ('ANEXO', 'Anexo do cidadão'), ('RESPOSTA', 'Resposta'),
        ('COMPROVANTE', 'Comprovante'), ('ASSINADO', 'Memorando assinado'), ('RECURSO', 'Recurso / decisão')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    demanda = models.ForeignKey(Demanda, on_delete=models.PROTECT, related_name='documentos')
    categoria = models.CharField(max_length=20, choices=CATEGORIAS)
    nome = models.CharField(max_length=240)
    arquivo = models.FileField(upload_to='lai/%Y/%m/', storage=private_storage)
    sha256 = models.CharField(max_length=64)
    tamanho = models.PositiveIntegerField()
    usuario = models.ForeignKey(USER, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)
    metadados = models.JSONField(default=dict, blank=True)
    def __str__(self): return self.nome

class Evento(models.Model):
    demanda = models.ForeignKey(Demanda, on_delete=models.PROTECT, related_name='eventos')
    usuario = models.ForeignKey(USER, null=True, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=60)
    dados = models.JSONField(default=dict)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-id']

class Sequencia(models.Model):
    ano = models.PositiveIntegerField(primary_key=True)
    valor = models.PositiveIntegerField(default=0)

class ModeloMemorando(models.Model):
    versao = models.CharField(max_length=80, unique=True)
    texto = models.TextField(default='Encaminhamos o pedido de acesso à informação registrado sob a NUP {nup}.\n\nObjeto: {resumo}\n\nSolicitamos resposta até {prazo_interno}, considerando o prazo externo de {prazo_externo}. A resposta deverá atender aos pontos solicitados e indicar eventual fundamento de restrição de acesso.')
    ativo = models.BooleanField(default=True)
    def __str__(self): return self.versao

class Memorando(models.Model):
    demanda = models.ForeignKey(Demanda, on_delete=models.PROTECT, related_name='memorandos')
    numero = models.PositiveIntegerField()
    ano = models.PositiveIntegerField()
    texto = models.TextField()
    destinatario = models.CharField(max_length=180)
    email = models.EmailField()
    signatario = models.TextField()
    modelo_versao = models.CharField(max_length=80)
    anterior = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    emitido_por = models.ForeignKey(USER, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)
    cancelado = models.BooleanField(default=False)
    motivo_cancelamento = models.TextField(blank=True)
    documento_assinado = models.ForeignKey(Documento, null=True, blank=True, on_delete=models.PROTECT)
    metodo_assinatura = models.CharField(max_length=180, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['ano', 'numero'], name='lai_numero_anual_unico')]
        ordering = ['-id']
    def __str__(self): return f'{self.numero:04d}/{self.ano}/LAI/CGM'

class Comunicacao(models.Model):
    STATUS = [('PENDENTE','Pendente'), ('PROCESSANDO','Processando'), ('SIMULADO','Simulado'),
        ('ACEITO','Aceito pelo SMTP'), ('INCERTO','Envio incerto'), ('FALHA','Falha'), ('MANUAL','Envio manual comprovado'), ('CANCELADO','Cancelado')]
    memorando = models.ForeignKey(Memorando, on_delete=models.PROTECT, related_name='comunicacoes')
    chave = models.CharField(max_length=160, unique=True)
    message_id = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=STATUS, default='PENDENTE')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    cobranca = models.BooleanField(default=False)
    comprovante = models.ForeignKey(Documento, null=True, blank=True, on_delete=models.PROTECT)

class TentativaEnvio(models.Model):
    comunicacao = models.ForeignKey(Comunicacao, on_delete=models.PROTECT, related_name='tentativas')
    resultado = models.CharField(max_length=40)
    detalhe = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

class Prorrogacao(models.Model):
    demanda = models.ForeignKey(Demanda, on_delete=models.PROTECT, related_name='prorrogacoes')
    novo_prazo = models.DateField()
    justificativa = models.TextField()
    ciencia_em = models.DateField()
    registro_falabr = models.CharField(max_length=240)
    comprovante = models.ForeignKey(Documento, on_delete=models.PROTECT)
    usuario = models.ForeignKey(USER, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)

class Resposta(models.Model):
    demanda = models.ForeignKey(Demanda, on_delete=models.PROTECT, related_name='respostas')
    tipo = models.CharField(max_length=20, choices=[('INTERNA','Resposta interna suficiente'), ('PARCIAL','Resposta incompleta'), ('FINAL','Registrada no Fala.BR')])
    texto = models.TextField()
    data = models.DateField()
    referencia = models.CharField(max_length=240, blank=True)
    comprovante = models.ForeignKey(Documento, on_delete=models.PROTECT)
    usuario = models.ForeignKey(USER, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)

class Recurso(models.Model):
    demanda = models.ForeignKey(Demanda, on_delete=models.PROTECT, related_name='recursos')
    tipo = models.CharField(max_length=30, choices=[('NEGATIVA','Negativa de acesso'),('DESCUMPRIMENTO','Descumprimento'),('DESCLASSIFICACAO','Desclassificação')])
    decisao_recorrida = models.TextField()
    ciencia = models.DateField()
    protocolo_em = models.DateField()
    protocolo = models.CharField(max_length=180)
    fundamentos = models.TextField()
    documento = models.ForeignKey(Documento, on_delete=models.PROTECT)
    criado_por = models.ForeignKey(USER, on_delete=models.PROTECT)
    encerrado = models.BooleanField(default=False)
    @property
    def limite_interposicao(self):
        from .prazos import somar
        return somar(self.ciencia, 10, self.demanda.politica)
    def __str__(self): return f'{self.demanda.nup} / {self.protocolo}'

class EtapaRecurso(models.Model):
    INSTANCIAS = [('SECRETARIA','Secretário / superior'),('CGM','Controladoria-Geral'),('COMISSAO','Comissão de Reavaliação'),
        ('PROCURADORIA','Consulta à Procuradoria'),('CUMPRIMENTO','Cumprimento da decisão')]
    recurso = models.ForeignKey(Recurso, on_delete=models.PROTECT, related_name='etapas')
    instancia = models.CharField(max_length=20, choices=INSTANCIAS)
    autoridade = models.CharField(max_length=180)
    recebida_em = models.DateField()
    vencimento = models.DateField(null=True, blank=True)
    fundamento = models.TextField()
    decisao = models.TextField(blank=True)
    resultado = models.CharField(max_length=20, blank=True, choices=[('PROVIDO','Provido'),('NEGADO','Negado'),('PARCIAL','Parcialmente provido'),('CUMPRIDO','Cumprido'),('PARECER','Parecer emitido')])
    decidida_em = models.DateField(null=True, blank=True)
    comunicada_em = models.DateField(null=True, blank=True)
    documento_decisao = models.ForeignKey(Documento, null=True, blank=True, on_delete=models.PROTECT)
    prorrogada = models.BooleanField(default=False)
    suspensa_em = models.DateField(null=True, blank=True)
    saldo_suspenso = models.PositiveIntegerField(null=True, blank=True)
    class Meta: ordering = ['id']

class Alerta(models.Model):
    demanda = models.ForeignKey(Demanda, on_delete=models.PROTECT, related_name='alertas')
    chave = models.CharField(max_length=160, unique=True)
    nivel = models.CharField(max_length=20)
    mensagem = models.CharField(max_length=240)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

class ManifestacaoFalabr(models.Model):
    """Linha lida da lista do Fala.BR, para acompanhar o prazo antes do cadastro.

    Não guarda o e-mail nem o nome do cidadão. O que a Demanda tem de
    conferido continua na Demanda; aqui fica só o que o Fala.BR mostra.
    """
    nup = models.CharField(max_length=40)
    nup_normalizada = models.CharField(max_length=30, unique=True, editable=False)
    orgao = models.CharField(max_length=180, blank=True)
    assunto = models.CharField(max_length=400, blank=True)
    servico = models.CharField(max_length=240, blank=True)
    tipo = models.CharField(max_length=180, blank=True)
    cadastro = models.DateField(null=True, blank=True)
    prazo = models.DateField(null=True, blank=True)
    situacao = models.CharField(max_length=80, blank=True)
    responsavel = models.CharField(max_length=180, blank=True)
    link = models.URLField(max_length=300, blank=True)
    primeira_leitura = models.DateTimeField(auto_now_add=True)
    ultima_leitura = models.DateTimeField(default=timezone.now)
    prazo_anterior = models.DateField(null=True, blank=True)
    situacao_anterior = models.CharField(max_length=80, blank=True)
    alterado_em = models.DateTimeField(null=True, blank=True)
    FILAS = [('ABERTA', 'Aberta no Fala.BR'), ('ENCERRADA', 'Encerrada no Fala.BR'), ('SAIU', 'Saiu da fila aberta')]
    fila = models.CharField(max_length=10, choices=FILAS, default='ABERTA')
    # Tema que dá nome à pasta e vai para a coluna OBJETO da planilha. Vazio = usa o assunto da lista.
    tema = models.CharField(max_length=200, blank=True)
    pasta = models.CharField(max_length=300, blank=True)
    baixado_em = models.DateTimeField(null=True, blank=True)
    @property
    def tema_efetivo(self): return self.tema or self.assunto
    class Meta: ordering = ['prazo', 'nup']
    def save(self, *args, **kwargs):
        import re
        self.nup_normalizada = re.sub(r'\D', '', self.nup)
        super().save(*args, **kwargs)
    def __str__(self): return self.nup

class MemorandoFalabr(models.Model):
    """Registro de cada memorando de reiteração gerado (.docx) a partir de uma manifestação do Fala.BR.

    O arquivo em si é entregue na hora para quem gerou; aqui fica só o histórico: número, secretaria e
    prazo informados. O número segue o da Controladoria (pode ser compartilhado com outros memorandos),
    por isso não é único: gerar de novo com o mesmo número é uma correção.
    """
    manifestacao = models.ForeignKey(ManifestacaoFalabr, on_delete=models.CASCADE, related_name='memorandos')
    numero = models.PositiveIntegerField()
    ano = models.PositiveIntegerField()
    data = models.DateField()
    secretaria = models.CharField(max_length=180)
    prazo = models.DateField()
    usuario = models.ForeignKey(USER, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-ano', '-numero', '-id']
    @property
    def rotulo(self): return f'{self.numero}/{self.ano}/CGM'
    def __str__(self): return f'Memorando {self.rotulo}'

class ExecucaoMonitor(models.Model):
    inicio = models.DateTimeField(auto_now_add=True)
    fim = models.DateTimeField(null=True)
    sucesso = models.BooleanField(default=False)
    detalhe = models.CharField(max_length=240, blank=True)
