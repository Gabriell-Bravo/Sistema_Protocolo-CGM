import re
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import *

class DataInput(forms.DateInput):
    input_type = 'date'
    def __init__(self, *a, **kw): super().__init__(*a, format='%Y-%m-%d', **kw)

class BaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if isinstance(f, forms.DateField): f.widget = DataInput(); f.input_formats=['%Y-%m-%d','%d/%m/%Y']
            if isinstance(f.widget, forms.Textarea): f.widget.attrs['rows']=4

class DemandaForm(BaseForm):
    class Meta:
        model = Demanda
        fields = ['nup','tipo','cadastro_falabr','marco_inicial','vencimento_original','prazo_interno','teor','resumo','secretaria','pessoal']
        labels = {'cadastro_falabr':'Data de cadastro no Fala.BR','marco_inicial':'Marco inicial confirmado',
            'vencimento_original':'Data-limite informada no Fala.BR', 'prazo_interno':'Prazo da secretaria',
            'teor':'Teor integral (confira com o PDF)', 'resumo':'Resumo operacional revisado','pessoal':'Contém informações pessoais'}
    def clean_nup(self):
        value=self.cleaned_data['nup'].strip()
        normalized=re.sub(r'\D','',value)
        if len(normalized)!=17: raise ValidationError('Informe a NUP com 17 dígitos, preservando zeros iniciais.')
        qs=Demanda.objects.filter(nup_normalizada=normalized)
        if self.instance.pk: qs=qs.exclude(pk=self.instance.pk)
        if qs.exists(): raise ValidationError('NUP já cadastrada. Abra a demanda e use reimportar PDF.')
        return value
    def clean(self):
        data=super().clean()
        start, end, internal = data.get('marco_inicial'), data.get('vencimento_original'), data.get('prazo_interno')
        if start and end and end < start: self.add_error('vencimento_original','Vencimento anterior ao marco inicial.')
        if internal and end and internal>end: self.add_error('prazo_interno','Prazo interno não pode ultrapassar o externo.')
        return data

class UploadForm(forms.Form):
    arquivo=forms.FileField(label='PDF exportado do Fala.BR', widget=forms.ClearableFileInput(attrs={'accept':'.pdf'}))

class AnexoForm(forms.Form):
    categoria=forms.ChoiceField(choices=Documento.CATEGORIAS)
    arquivo=forms.FileField(help_text='PDF, JPEG ou PNG. Até 15 MB. Outros formatos: converter antes de anexar.')

class ConfirmarForm(forms.Form):
    motivo=forms.CharField(label='Conferência dos dados e justificativa de divergências', widget=forms.Textarea(attrs={'rows':3}))

class MemorandoForm(forms.Form):
    texto=forms.CharField(widget=forms.Textarea(attrs={'rows':13}), label='Minuta revisada')
    cobranca=forms.BooleanField(required=False, label='Reiteração vinculada ao memorando anterior')

class ProrrogacaoForm(BaseForm):
    class Meta:
        model=Prorrogacao
        fields=['novo_prazo','justificativa','ciencia_em','registro_falabr','comprovante']

class RespostaForm(BaseForm):
    class Meta:
        model=Resposta
        fields=['tipo','texto','data','referencia','comprovante']

class RecursoForm(BaseForm):
    class Meta:
        model=Recurso
        fields=['tipo','decisao_recorrida','ciencia','protocolo_em','protocolo','fundamentos','documento']

class EtapaForm(BaseForm):
    class Meta:
        model=EtapaRecurso
        fields=['instancia','autoridade','recebida_em','vencimento','fundamento']
        help_texts={'vencimento':'Deixe vazio para cálculo de 5 dias nas instâncias previstas. Comissão não recebe prazo presumido.',
            'fundamento':'Indique artigo, hipótese aplicável e, se necessário, o ato que fundamenta o prazo manual.'}

class DecisaoForm(BaseForm):
    class Meta:
        model=EtapaRecurso
        fields=['resultado','decisao','decidida_em','comunicada_em','documento_decisao']
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw)
        for f in self.fields.values(): f.required=True

class PrazoEtapaForm(forms.Form):
    acao=forms.ChoiceField(choices=[('PRORROGAR','Prorrogar cumprimento +15 dias'),('SUSPENDER','Suspender prazo específico após consulta jurídica'),('RETOMAR','Retomar prazo suspenso')])
    data=forms.DateField(widget=DataInput(), initial=timezone.localdate)
    fundamento=forms.CharField(widget=forms.Textarea, label='Fundamento e interpretação jurídica aprovada para este ato')

class RedirecionarForm(forms.Form):
    secretaria=forms.ModelChoiceField(queryset=Secretaria.objects.filter(ativa=True))
    motivo=forms.CharField(widget=forms.Textarea)

class AutomacaoForm(forms.Form):
    auto_cobranca=forms.BooleanField(required=False,label='Habilitar emissão automática de cobranças para esta demanda')
    autorizacao_automacao=forms.CharField(widget=forms.Textarea, required=False, label='Ato/delegação que autoriza a expedição pelo operador responsável')
    def clean(self):
        d=super().clean()
        if d.get('auto_cobranca') and not d.get('autorizacao_automacao','').strip(): raise ValidationError('Informe a autorização institucional.')
        return d

class MotivoForm(forms.Form):
    motivo=forms.CharField(widget=forms.Textarea)

class EnvioForm(forms.Form):
    acao=forms.ChoiceField(choices=[('MANUAL','Registrar envio manual comprovado'),('REPETIR','Autorizar nova tentativa após reconciliação')])
    motivo=forms.CharField(widget=forms.Textarea)
    comprovante=forms.ModelChoiceField(queryset=Documento.objects.none())

class AssinaturaForm(forms.Form):
    documento=forms.ModelChoiceField(queryset=Documento.objects.none())
    metodo=forms.CharField(label='Método de assinatura / validação realizada', max_length=180)
