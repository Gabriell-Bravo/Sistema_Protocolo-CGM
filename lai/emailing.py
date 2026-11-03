"""Fila persistente. Estados incertos nunca são reenviados automaticamente."""
import smtplib
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import Comunicacao, TentativaEnvio
from .pdf import gerar_memorando
from .permissions import exigir
from django.core.exceptions import PermissionDenied

def processar_email(pk):
    with transaction.atomic():
        c = Comunicacao.objects.select_for_update().select_related('memorando__demanda').get(pk=pk)
        if c.status != 'PENDENTE': return c.status
        m, d = c.memorando, c.memorando.demanda
        try: exigir(m.emitido_por,'expedir',d)
        except PermissionDenied:
            c.status='CANCELADO'; c.save(); return c.status
        if m.cancelado or (c.cobranca and (d.encerrada or not d.precisa_resposta_interna)):
            c.status='CANCELADO'; c.save(); return c.status
        if c.cobranca and (not d.auto_cobranca or not d.autorizacao_automacao):
            return 'PENDENTE'
        if getattr(settings, 'LAI_LIVE_EMAIL', False) and not d.politica.homologada:
            return 'AGUARDA_HOMOLOGACAO'
        c.status='PROCESSANDO'; c.save()
    status, detalhe = 'INCERTO', ''
    try:
        # Somente memorando: anexos pessoais permanecem no armazenamento privado.
        email = EmailMessage(f'LAI — Memorando {m}', f'Encaminhamos o memorando em anexo.\nAcesse o sistema institucional para os documentos autorizados.\n{settings.LAI_PUBLIC_URL}',
            settings.DEFAULT_FROM_EMAIL, [m.email], headers={'Message-ID': c.message_id})
        email.attach(f'memorando-{m.ano}-{m.numero}.pdf', gerar_memorando(m), 'application/pdf')
        count = email.send(fail_silently=False)
        status = ('ACEITO' if settings.LAI_LIVE_EMAIL else 'SIMULADO') if count else 'FALHA'
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        status, detalhe = 'FALHA', type(exc).__name__
    except Exception as exc:
        status, detalhe = 'INCERTO', type(exc).__name__
    with transaction.atomic():
        c = Comunicacao.objects.select_for_update().get(pk=pk)
        c.status=status; c.save()
        TentativaEnvio.objects.create(comunicacao=c, resultado=status, detalhe=detalhe)
    return status

def processar_fila():
    # Processo interrompido após envio pode ter entregado: exige reconciliação humana.
    Comunicacao.objects.filter(status='PROCESSANDO', atualizado_em__lt=timezone.now()-timedelta(minutes=10)).update(status='INCERTO')
    return [processar_email(pk) for pk in Comunicacao.objects.filter(status='PENDENTE').values_list('pk', flat=True)]
