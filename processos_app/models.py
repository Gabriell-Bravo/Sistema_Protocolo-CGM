# processos_app/models.py
from django.db import models
from datetime import datetime, date, timedelta
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User


class Processo(models.Model):
    PRIORIDADE_CHOICES = [
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

    status_analise = models.CharField(
        max_length=50,
        choices=STATUS_ANALISE_CHOICES,
        default='NAO_APLICAVEL',
        verbose_name="Status da Análise"
    )

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
    recorrente = models.CharField(
        max_length=3,
        default='NÃO',
        choices=[('SIM', 'SIM'), ('NÃO', 'NÃO')],
        verbose_name="Recorrente"
    )
    prioridade = models.CharField(
        max_length=50,
        choices=PRIORIDADE_CHOICES,
        default='NAO',
        verbose_name="Prioridade"
    )
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

    def __str__(self):
        return self.numero_processo

    class Meta:
        db_table = 'processos'
        verbose_name_plural = "Processos"


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

# NEW PROFILE MODEL


class Profile(models.Model):
    USER_LEVEL_CHOICES = [
        ('0', 'Protocolo'),
        ('1', 'Analista 1 (Licitações e Contratos)'),
        ('2', 'Analista 2 (Liquidações)'),
        ('3', 'Usuário Geral (Todos)'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    level = models.CharField(
        max_length=1, choices=USER_LEVEL_CHOICES, default='3')

    def __str__(self):
        return f'{self.user.username} Profile'

# Signal to create or update user profile when a User is created/updated


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    instance.profile.save()
