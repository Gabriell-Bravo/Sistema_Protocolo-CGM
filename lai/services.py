import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import *
from .permissions import exigir
from .prazos import somar, marco

def evento(d, user, tipo, **dados):
    return Evento.objects.create(demanda=d, usuario=user, tipo=tipo, dados=dados)

def documento_da_demanda(doc, d):
    if not doc or doc.demanda_id != d.pk: raise ValidationError('Comprovante deve pertencer à mesma demanda.')

@transaction.atomic
def confirmar(d, user, motivo):
    exigir(user, 'operar', d)
    d = Demanda.objects.select_for_update().get(pk=d.pk)
    if d.conferido_em: raise ValidationError('Demanda já conferida.')
    if not motivo.strip(): raise ValidationError('Registre a conferência e eventual divergência de datas.')
    if d.vencimento_original < d.marco_inicial or d.prazo_interno > d.vencimento_original:
        raise ValidationError('Revise o marco e os prazos.')
    d.conferido_em = timezone.now()
    d.status = 'CADASTRADA'
    d.motivo_conferencia = motivo
    d.save()
    evento(d, user, 'CONFERENCIA', motivo=motivo, vencimento=d.vencimento_original.isoformat())
    return d

def minuta(d):
    model = ModeloMemorando.objects.filter(ativo=True).order_by('-id').first()
    if not model: raise ValidationError('Cadastre um modelo de memorando ativo.')
    try:
        text = model.texto.format(nup=d.nup, resumo=d.resumo, prazo_interno=d.prazo_interno.strftime('%d/%m/%Y'),
            prazo_externo=d.vencimento.strftime('%d/%m/%Y'))
    except (KeyError, ValueError): raise ValidationError('Modelo contém variável inválida.')
    return model, text

@transaction.atomic
def emitir(d, user, texto=None, cobranca=False, chave=None):
    op = exigir(user, 'expedir', d)
    d = Demanda.objects.select_for_update().get(pk=d.pk)
    if not d.conferido_em or d.encerrada: raise ValidationError('Confirme a demanda antes de expedir; demanda encerrada não admite cobrança.')
    if cobranca and not d.precisa_resposta_interna: raise ValidationError('Resposta interna já recebida.')
    if chave:
        previous = Comunicacao.objects.filter(chave=chave).first()
        if previous: return previous.memorando
    model, generated = minuta(d)
    anterior = d.memorandos.filter(cancelado=False).first()
    text = texto.strip() if texto else generated
    if cobranca and anterior: text = f'Reiteração ao Memorando nº {anterior}.\n\n' + text
    if not text: raise ValidationError('Texto obrigatório.')
    ano = timezone.localdate().year
    Sequencia.objects.get_or_create(ano=ano)
    # UPDATE adquire bloqueio também no PostgreSQL; a transação mantém a reserva até a gravação.
    Sequencia.objects.filter(ano=ano).update(valor=F('valor') + 1)
    seq = Sequencia.objects.get(ano=ano)
    m = Memorando.objects.create(demanda=d, numero=seq.valor, ano=ano, texto=text,
        destinatario=d.secretaria.nome, email=d.secretaria.email,
        signatario=f'{op.nome}\n{op.cargo}\n{op.unidade}', modelo_versao=model.versao,
        anterior=anterior if cobranca else None, emitido_por=user)
    Comunicacao.objects.create(memorando=m, chave=chave or f'memo:{m.pk}',
        message_id=f'<lai-{uuid.uuid4().hex}@{settings.DEFAULT_FROM_EMAIL.split("@")[-1]}>', cobranca=cobranca)
    d.status = 'AGUARDANDO' if d.status == 'CADASTRADA' else d.status
    d.save()
    evento(d, user, 'MEMORANDO_EMITIDO', numero=str(m), modelo=model.versao)
    return m

@transaction.atomic
def prorrogar(d, user, **dados):
    exigir(user, 'prorrogar', d)
    d = Demanda.objects.select_for_update().get(pk=d.pk)
    if not d.conferido_em or d.encerrada or d.prorrogacoes.exists(): raise ValidationError('Prorrogação indisponível neste estado.')
    documento_da_demanda(dados.get('comprovante'), d)
    hoje = timezone.localdate()
    if dados['ciencia_em'] > hoje or dados['ciencia_em'] > d.vencimento_original:
        raise ValidationError('A ciência deve ocorrer até o prazo original e não pode ser futura.')
    expected = somar(d.vencimento_original, 10, d.politica)
    if dados['novo_prazo'] <= d.vencimento_original or dados['novo_prazo'] > expected:
        raise ValidationError(f'Novo prazo deve ser posterior ao original e até {expected:%d/%m/%Y}. Divergência exige revisão da política.')
    if not dados['justificativa'].strip() or not dados['registro_falabr'].strip(): raise ValidationError('Justificativa e registro no Fala.BR obrigatórios.')
    p = Prorrogacao.objects.create(demanda=d, usuario=user, **dados)
    evento(d, user, 'PRORROGACAO', de=d.vencimento_original.isoformat(), para=p.novo_prazo.isoformat(), justificativa=p.justificativa)
    return p

@transaction.atomic
def responder(d, user, **dados):
    exigir(user, 'operar', d)
    d = Demanda.objects.select_for_update().get(pk=d.pk)
    if not d.conferido_em or d.encerrada: raise ValidationError('Demanda não disponível para resposta.')
    documento_da_demanda(dados['comprovante'], d)
    if dados['data'] > timezone.localdate() or dados['data'] < d.cadastro_falabr:
        raise ValidationError('Data da resposta inválida.')
    if dados['tipo'] == 'FINAL' and not dados.get('referencia', '').strip():
        raise ValidationError('Informe a referência do registro no Fala.BR.')
    old = d.status
    r = Resposta.objects.create(demanda=d, usuario=user, **dados)
    d.status = {'INTERNA':'RESPOSTA_INTERNA', 'PARCIAL':'COMPLEMENTACAO', 'FINAL':'RESPONDIDA'}[r.tipo]
    if r.tipo == 'FINAL': d.respondida_em = r.data
    if r.tipo == 'PARCIAL': d.ciclo += 1
    d.save()
    if r.tipo != 'PARCIAL':
        Comunicacao.objects.filter(memorando__demanda=d, cobranca=True, status='PENDENTE').update(status='CANCELADO')
    d.alertas.update(ativo=False)
    evento(d, user, 'RESPOSTA', de=old, para=d.status, resposta=r.pk)
    return r

@transaction.atomic
def redirecionar(d, user, secretaria, motivo):
    op = exigir(user, 'operar', d)
    if not (op.acesso_global or op.secretarias.filter(pk=secretaria.pk).exists()): raise ValidationError('Secretaria fora do seu escopo.')
    d = Demanda.objects.select_for_update().get(pk=d.pk)
    if d.encerrada: raise ValidationError('Demanda encerrada.')
    anterior = d.secretaria_id
    d.secretaria = secretaria
    d.ciclo += 1
    if d.conferido_em: d.status = 'CADASTRADA'
    d.save()
    Comunicacao.objects.filter(memorando__demanda=d, status='PENDENTE').update(status='CANCELADO')
    evento(d, user, 'REDIRECIONAMENTO_INTERNO', anterior=anterior, nova=secretaria.pk, motivo=motivo, prazo_preservado=d.vencimento.isoformat())

@transaction.atomic
def criar_recurso(d, user, **dados):
    exigir(user, 'recorrer', d)
    documento_da_demanda(dados['documento'], d)
    if dados['ciencia'] > dados['protocolo_em'] or dados['protocolo_em'] > timezone.localdate():
        raise ValidationError('Confira as datas de ciência e protocolo.')
    r = Recurso.objects.create(demanda=d, criado_por=user, **dados)
    evento(d, user, 'RECURSO_CADASTRADO', recurso=r.pk, protocolo=r.protocolo)
    return r

@transaction.atomic
def nova_etapa(r, user, **dados):
    exigir(user, 'recorrer', r.demanda)
    r = Recurso.objects.select_for_update().get(pk=r.pk)
    if r.encerrado: raise ValidationError('Recurso encerrado.')
    previous = r.etapas.exclude(instancia='PROCURADORIA').last()
    inst = dados['instancia']
    if previous and not previous.decidida_em and inst != 'PROCURADORIA':
        raise ValidationError('Conclua a etapa anterior antes de abrir outra, salvo consulta à Procuradoria.')
    if not previous and inst not in ('SECRETARIA',): raise ValidationError('Inicie pela autoridade da Secretaria; documente exceções em procedimento validado.')
    if previous:
        if inst == 'SECRETARIA': raise ValidationError('A primeira instância já foi registrada neste recurso.')
        if inst == 'CGM' and not (previous.instancia=='SECRETARIA' and previous.resultado in ('NEGADO','PARCIAL')):
            raise ValidationError('Encaminhamento à CGM exige negativa total ou parcial na primeira instância.')
        if inst == 'COMISSAO' and not (previous.resultado in ('NEGADO','PARCIAL') and (previous.instancia=='CGM' or (r.tipo=='DESCLASSIFICACAO' and previous.instancia=='SECRETARIA'))):
            raise ValidationError('Confira a hipótese de recurso à Comissão.')
        if inst == 'CUMPRIMENTO' and previous.resultado not in ('PROVIDO','PARCIAL'):
            raise ValidationError('Cumprimento exige decisão de provimento total ou parcial.')
        if inst == 'PROCURADORIA' and (previous.instancia!='CGM' or previous.decidida_em or r.etapas.filter(instancia='PROCURADORIA',decidida_em=None).exists()):
            raise ValidationError('Consulta deve se vincular à etapa ativa da CGM e não pode duplicar consulta pendente.')
    if dados['recebida_em'] < r.protocolo_em or dados['recebida_em'] > timezone.localdate(): raise ValidationError('Data de recebimento inválida.')
    # Prazos não inferidos para Comissão nem para cumprimento determinado pela CGM.
    dias = 5 if inst in ('SECRETARIA', 'CGM', 'PROCURADORIA') else None
    if inst == 'CUMPRIMENTO' and previous and previous.instancia == 'SECRETARIA' and previous.resultado in ('PROVIDO','PARCIAL'): dias = 15
    if dias:
        calculado=somar(dados['recebida_em'],dias,r.demanda.politica)
        if dados.get('vencimento') and dados['vencimento']!=calculado:
            raise ValidationError('Prazo diverge da regra da instância. Confira a política de contagem antes de cadastrar.')
        dados['vencimento']=calculado
    if dados.get('vencimento') and dados['vencimento'] < dados['recebida_em']: raise ValidationError('Vencimento anterior ao recebimento.')
    e = EtapaRecurso.objects.create(recurso=r, **dados)
    evento(r.demanda, user, 'ETAPA_RECURSAL', etapa=e.pk, instancia=inst, fundamento=e.fundamento)
    return e

@transaction.atomic
def decidir(e, user, **dados):
    exigir(user, 'decidir', e.recurso.demanda)
    e = EtapaRecurso.objects.select_for_update().get(pk=e.pk)
    if e.decidida_em or e.suspensa_em: raise ValidationError('Etapa decidida ou suspensa.')
    if e.instancia=='CGM' and e.recurso.etapas.filter(instancia='PROCURADORIA',decidida_em=None).exists():
        raise ValidationError('Registre o retorno da consulta jurídica antes da decisão.')
    allowed = ('PARECER',) if e.instancia=='PROCURADORIA' else ('CUMPRIDO',) if e.instancia=='CUMPRIMENTO' else ('PROVIDO','NEGADO','PARCIAL')
    if dados['resultado'] not in allowed: raise ValidationError('Resultado incompatível com a etapa.')
    documento_da_demanda(dados['documento_decisao'], e.recurso.demanda)
    if dados['decidida_em'] < e.recebida_em or dados['comunicada_em'] < dados['decidida_em'] or dados['comunicada_em'] > timezone.localdate():
        raise ValidationError('Confira datas da decisão e da comunicação.')
    for key, val in dados.items(): setattr(e, key, val)
    e.save()
    evento(e.recurso.demanda, user, 'DECISAO_RECURSAL', etapa=e.pk, resultado=e.resultado)

@transaction.atomic
def prazo_etapa(e, user, acao, data, fundamento):
    exigir(user, 'decidir', e.recurso.demanda)
    e = EtapaRecurso.objects.select_for_update().get(pk=e.pk)
    if e.decidida_em or data > timezone.localdate() or data < e.recebida_em: raise ValidationError('Etapa/data inválida.')
    p = e.recurso.demanda.politica
    if acao == 'PRORROGAR':
        if e.instancia != 'CUMPRIMENTO' or e.prorrogada or not e.vencimento or e.suspensa_em: raise ValidationError('Só cumprimento pode ser prorrogado uma vez.')
        anterior = e.recurso.etapas.filter(id__lt=e.id, instancia='SECRETARIA', resultado__in=['PROVIDO','PARCIAL']).last()
        if not anterior: raise ValidationError('Prorrogação de 15 dias exige hipótese do art. 13 §2º.')
        e.vencimento = somar(e.vencimento, 15, p)
        e.prorrogada = True
    elif acao == 'SUSPENDER':
        if not e.vencimento or e.suspensa_em or data > e.vencimento: raise ValidationError('Prazo não pode ser suspenso.')
        if not e.recurso.etapas.filter(instancia='PROCURADORIA', decidida_em=None).exists(): raise ValidationError('Registre a consulta jurídica primeiro.')
        e.suspensa_em = data
        e.saldo_suspenso = sum(1 for i in range(1, (e.vencimento-data).days+1) if not p.dias_uteis or __import__('lai.prazos', fromlist=['util']).util(data+timedelta(days=i), p))
    elif acao == 'RETOMAR':
        if not e.suspensa_em or data < e.suspensa_em: raise ValidationError('Suspensão não encontrada/data inválida.')
        e.vencimento = somar(data, e.saldo_suspenso, p)
        e.suspensa_em = None
        e.saldo_suspenso = None
    else: raise ValidationError('Ação inválida.')
    e.save()
    evento(e.recurso.demanda, user, 'PRAZO_RECURSAL', etapa=e.pk, acao=acao, data=data.isoformat(), fundamento=fundamento)

@transaction.atomic
def monitorar_demanda(pk, hoje):
    d = Demanda.objects.select_for_update().get(pk=pk)
    d.alertas.filter(chave__startswith=f'd:{d.pk}:').update(ativo=False)
    info = marco(d, hoje)
    if info:
        code, nivel, mensagem = info
        key = f'd:{d.pk}:c:{d.ciclo}:{code}'
        a, created = Alerta.objects.get_or_create(chave=key, defaults=dict(demanda=d, nivel=nivel, mensagem=mensagem))
        if not a.ativo: a.ativo=True; a.save(update_fields=['ativo'])
        if d.auto_cobranca and d.autorizacao_automacao and code in ('D10','D19','P8','ATRASO') and d.precisa_resposta_interna:
            if not Comunicacao.objects.filter(chave=key).exists():
                try: emitir(d, d.operador.usuario, cobranca=True, chave=key)
                except (ValidationError, __import__('django.core.exceptions', fromlist=['PermissionDenied']).PermissionDenied):
                    evento(d, None, 'COBRANCA_PENDENTE', motivo='Confira permissão, operador e modelo da automação.')
        if created: evento(d, None, 'ALERTA', marco=code)
    for e in EtapaRecurso.objects.filter(recurso__demanda=d, recurso__encerrado=False):
        key = f'recurso:{e.pk}'
        if not e.decidida_em and not e.suspensa_em and (e.vencimento is None or e.vencimento <= hoje+timedelta(days=1)):
            Alerta.objects.update_or_create(chave=key, defaults=dict(demanda=d, ativo=True, nivel='vermelho' if e.vencimento and e.vencimento<hoje else 'amarelo', mensagem=f'Recurso: {e.get_instancia_display()} — ' + ('prazo precisa ser definido' if not e.vencimento else f'vence {e.vencimento:%d/%m/%Y}')))
        else: Alerta.objects.filter(chave=key).update(ativo=False)

def monitorar(hoje=None):
    run = ExecucaoMonitor.objects.create()
    try:
        for pk in Demanda.objects.values_list('pk', flat=True): monitorar_demanda(pk, hoje or timezone.localdate())
        run.sucesso = True
        run.detalhe = 'Monitoramento concluído.'
    except Exception as exc:
        run.detalhe = 'Falha: ' + type(exc).__name__
        raise
    finally:
        run.fim = timezone.now(); run.save()
