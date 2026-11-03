import shutil
import tempfile
from datetime import timedelta, date
from io import BytesIO
from unittest.mock import patch
from pathlib import Path
from django.conf import settings
from django.test import TestCase, override_settings, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader
from lai.models import *
from lai import services
from lai.arquivos import guardar, validar
from lai.emailing import processar_email, processar_fila
from lai.extracao import extrair
from lai.forms import DemandaForm
from lai.pdf import gerar_memorando
from lai.prazos import somar, marco

def pdf_falso():
    b=BytesIO(); c=Canvas(b)
    for i,line in enumerate(['Tipo de Manifestação: Acesso à Informação','NUP: 00000.2026.000001-00','Data de Cadastro: 01/10/2026','Data limite para resposta: 21/10/2026','Resumo: -','Teor: Solicito dados públicos fictícios.']):
        c.drawString(45,800-i*25,line)
    c.save(); return b.getvalue()

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
@override_settings(LAI_SOMENTE_ADMIN=False)
class FluxosTest(TestCase):
    def setUp(self):
        root=Path(settings.BASE_DIR)/'var'/'test-temp'
        root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.mkdtemp(dir=root)
        assert Path(self.temp).resolve().is_relative_to(root.resolve())
        self.override=override_settings(LAI_PRIVATE_ROOT=self.temp, LAI_LIVE_EMAIL=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',LAI_PUBLIC_URL='http://testserver',DEFAULT_FROM_EMAIL='lai@example.invalid')
        self.override.enable(); self.addCleanup(self.override.disable); self.addCleanup(shutil.rmtree,self.temp,True)
        self.u=get_user_model().objects.create_user('operador',password='teste-lai-123456')
        self.u.user_permissions.set(Permission.objects.filter(content_type__app_label='lai'))
        self.op=Operador.objects.create(usuario=self.u,nome='Operador Fictício',cargo='Operador',email='op@example.invalid',acesso_global=True,autoridade_recursal=True)
        self.sec=Secretaria.objects.create(nome='Secretaria Fictícia',sigla='SEC',email='sec@example.invalid')
        self.p=PoliticaPrazo.objects.create(versao='teste')
        ModeloMemorando.objects.create(versao='v1')
        self.today=timezone.localdate(); self.start=self.today-timedelta(days=19)
        self.d=Demanda.objects.create(nup='00000.2026.000001-00',tipo='Acesso à Informação',cadastro_falabr=self.start,marco_inicial=self.start,vencimento_original=self.start+timedelta(days=20),prazo_interno=self.today,teor='Texto fictício',resumo='Dados públicos',secretaria=self.sec,operador=self.op,politica=self.p)
        self.doc=guardar(self.d,SimpleUploadedFile('comprovante.pdf',pdf_falso()),'COMPROVANTE',self.u)
        self.client.force_login(self.u)
    def confirm(self): self.d=services.confirmar(self.d,self.u,'Campos conferidos.'); return self.d
    def recurso(self):
        return services.criar_recurso(self.d,self.u,tipo='NEGATIVA',decisao_recorrida='Decisão fictícia',ciencia=self.today-timedelta(days=2),protocolo_em=self.today,protocolo='REC-1',fundamentos='Revisão requerida',documento=self.doc)
    def etapa(self,r,**kwargs):
        return services.nova_etapa(r,self.u,instancia=kwargs.get('instancia','SECRETARIA'),autoridade='Autoridade fictícia',recebida_em=self.today,fundamento='Art. 13, §1º',vencimento=None)
    def decidir(self,e,resultado='PROVIDO'):
        services.decidir(e,self.u,resultado=resultado,decisao='Decisão motivada fictícia',decidida_em=self.today,comunicada_em=self.today,documento_decisao=self.doc)

    def test_extracao_campos(self):
        r=extrair(BytesIO(pdf_falso()))
        self.assertEqual(r['nup'],self.d.nup); self.assertEqual(r['vencimento_original'],'2026-10-21'); self.assertIn('fictícios',r['teor'])
    def test_nup_duplicada(self):
        form=DemandaForm(data={'nup':'00000202600000100'})
        self.assertFalse(form.is_valid()); self.assertIn('nup',form.errors)
    def test_expedicao_exige_conferencia(self):
        with self.assertRaises(ValidationError): services.emitir(self.d,self.u)
    def test_numeracao_e_idempotencia(self):
        self.confirm(); a=services.emitir(self.d,self.u,chave='unica'); b=services.emitir(self.d,self.u,chave='unica')
        c=services.emitir(self.d,self.u,cobranca=True)
        self.assertEqual(a.pk,b.pk); self.assertEqual(c.numero,a.numero+1); self.assertEqual(c.anterior_id,a.pk)
    def test_numero_cancelado_nao_reutilizado(self):
        self.confirm(); a=services.emitir(self.d,self.u); a.cancelado=True; a.save()
        b=services.emitir(self.d,self.u); self.assertEqual(b.numero,a.numero+1)
    def test_sequencia_ano_novo(self):
        self.confirm()
        with patch('lai.services.timezone.localdate',return_value=date(2027,1,1)): m=services.emitir(self.d,self.u)
        self.assertEqual((m.ano,m.numero),(2027,1))
    def test_pdf_tem_nup_e_numero(self):
        self.confirm(); m=services.emitir(self.d,self.u); pdf=gerar_memorando(m)
        text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
        self.assertIn(self.d.nup,text); self.assertIn(str(m),text)
    def test_monitor_consolida_e_nao_duplica(self):
        self.confirm(); self.d.auto_cobranca=True; self.d.autorizacao_automacao='Ato fictício'; self.d.save()
        services.monitorar(self.today); services.monitorar(self.today)
        self.assertEqual(Alerta.objects.filter(ativo=True).count(),1); self.assertEqual(Memorando.objects.count(),1)
        self.assertIn('D19',Alerta.objects.get().chave); self.assertFalse(Prorrogacao.objects.exists())
    def test_marco_d10(self):
        self.confirm(); self.assertEqual(marco(self.d,self.start+timedelta(days=10))[0],'D10')
        self.assertIsNone(marco(self.d,self.start+timedelta(days=9)))
    def test_resposta_interna_nao_encerra_externo(self):
        self.confirm(); services.responder(self.d,self.u,tipo='INTERNA',texto='Completa',data=self.today,referencia='',comprovante=self.doc)
        self.d.refresh_from_db(); self.assertFalse(self.d.encerrada); self.assertEqual(marco(self.d,self.today)[0],'FINAL')
    def test_resposta_final_exige_referencia(self):
        self.confirm()
        with self.assertRaises(ValidationError): services.responder(self.d,self.u,tipo='FINAL',texto='Resposta',data=self.today,referencia='',comprovante=self.doc)
    def test_resposta_final_encerra_alertas(self):
        self.confirm(); services.monitorar(self.today)
        services.responder(self.d,self.u,tipo='FINAL',texto='Resposta',data=self.today,referencia='registro Fala.BR fictício',comprovante=self.doc)
        services.monitorar(self.today); self.d.refresh_from_db()
        self.assertTrue(self.d.encerrada); self.assertFalse(Alerta.objects.filter(ativo=True).exists())
    def test_complementacao_reabre_ciclo(self):
        self.confirm(); services.responder(self.d,self.u,tipo='PARCIAL',texto='Faltam itens',data=self.today,referencia='',comprovante=self.doc)
        self.d.refresh_from_db(); self.assertEqual(self.d.ciclo,2); self.assertTrue(self.d.precisa_resposta_interna)
    def test_prorrogacao_formal_e_alerta_p8(self):
        self.confirm(); novo=self.d.vencimento_original+timedelta(days=10)
        services.prorrogar(self.d,self.u,novo_prazo=novo,justificativa='Busca documental',ciencia_em=self.today,registro_falabr='Registro fictício',comprovante=self.doc)
        self.assertEqual(marco(self.d,novo-timedelta(days=2))[0],'P8')
        with self.assertRaises(ValidationError): services.prorrogar(self.d,self.u,novo_prazo=novo,justificativa='Repetida',ciencia_em=self.today,registro_falabr='x',comprovante=self.doc)
    def test_prorrogacao_sem_justificativa(self):
        self.confirm()
        with self.assertRaises(ValidationError): services.prorrogar(self.d,self.u,novo_prazo=self.today+timedelta(days=10),justificativa='',ciencia_em=self.today,registro_falabr='x',comprovante=self.doc)
    def test_redirecionamento_preserva_prazo(self):
        self.confirm(); other=Secretaria.objects.create(nome='Outra',sigla='OUT',email='out@example.invalid')
        old=self.d.vencimento; services.redirecionar(self.d,self.u,other,'Competência'); self.d.refresh_from_db()
        self.assertEqual(self.d.vencimento,old); self.assertEqual(self.d.secretaria_id,other.pk)
    def test_email_simulado_nao_encerra_demanda(self):
        self.confirm(); m=services.emitir(self.d,self.u); c=m.comunicacoes.get()
        self.assertEqual(processar_email(c.pk),'SIMULADO'); self.d.refresh_from_db(); self.assertFalse(self.d.encerrada)
    def test_timeout_nao_reenvia(self):
        self.confirm(); c=services.emitir(self.d,self.u).comunicacoes.get()
        with patch('lai.emailing.EmailMessage.send',side_effect=TimeoutError): self.assertEqual(processar_email(c.pk),'INCERTO')
        with patch('lai.emailing.EmailMessage.send') as mock: processar_fila(); mock.assert_not_called()
    def test_resposta_cancela_cobranca_pendente(self):
        self.confirm(); c=services.emitir(self.d,self.u,cobranca=True).comunicacoes.get()
        services.responder(self.d,self.u,tipo='INTERNA',texto='Completa',data=self.today,referencia='',comprovante=self.doc)
        c.refresh_from_db(); self.assertEqual(c.status,'CANCELADO')
    def test_usuario_sem_escopo_nao_baixa(self):
        other=get_user_model().objects.create_user('outro'); other.user_permissions.set(Permission.objects.filter(content_type__app_label='lai'))
        Operador.objects.create(usuario=other,nome='Outro',cargo='Leitor',email='outro@example.invalid')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('lai:documento',args=[self.doc.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse('lai:dashboard')),self.d.nup)
    def test_sem_perfil_mesmo_superuser(self):
        u=get_user_model().objects.create_superuser('admin','admin@example.invalid','teste')
        self.client.force_login(u); self.assertEqual(self.client.get(reverse('lai:dashboard')).status_code,403)
    def test_arquivo_privado_sem_url(self):
        with self.assertRaises(ValueError): _=self.doc.arquivo.url
    def test_rejeita_executavel_disfarcado(self):
        with self.assertRaises(ValidationError): validar(SimpleUploadedFile('arquivo.pdf',b'MZexe'))
    def test_recurso_primeira_instancia_cinco_dias(self):
        e=self.etapa(self.recurso()); self.assertEqual(e.vencimento,self.today+timedelta(days=5))
    def test_cumprimento_quinze_mais_quinze(self):
        r=self.recurso(); e=self.etapa(r); self.decidir(e)
        c=self.etapa(r,instancia='CUMPRIMENTO'); self.assertEqual(c.vencimento,self.today+timedelta(days=15))
        services.prazo_etapa(c,self.u,'PRORROGAR',self.today,'Art. 13 §2º'); c.refresh_from_db()
        self.assertEqual(c.vencimento,self.today+timedelta(days=30))
        with self.assertRaises(ValidationError): services.prazo_etapa(c,self.u,'PRORROGAR',self.today,'Repetição')
    def test_comissao_sem_prazo_inventado(self):
        r=self.recurso(); e=self.etapa(r); self.decidir(e,'NEGADO'); e=self.etapa(r,instancia='CGM'); self.decidir(e,'NEGADO')
        e=self.etapa(r,instancia='COMISSAO'); self.assertIsNone(e.vencimento)
    def test_sem_competencia_nao_decide(self):
        e=self.etapa(self.recurso()); self.op.autoridade_recursal=False; self.op.save()
        self.u=get_user_model().objects.get(pk=self.u.pk)
        with self.assertRaises(PermissionDenied): self.decidir(e)
    def test_recurso_nao_altera_resposta_original(self):
        self.confirm(); services.responder(self.d,self.u,tipo='FINAL',texto='Negativa motivada',data=self.today,referencia='ref',comprovante=self.doc)
        self.recurso(); self.d.refresh_from_db(); self.assertEqual(self.d.status,'RESPONDIDA'); self.assertEqual(self.d.respostas.count(),1)
    def test_calendario_feriado_virada_ano(self):
        self.p.dias_uteis=True; self.p.feriados=['2027-01-01']
        self.assertEqual(somar(date(2026,12,31),1,self.p),date(2027,1,4))
    def test_politica_usada_imutavel(self):
        self.p.dias_uteis=True
        with self.assertRaises(ValidationError): self.p.save()
    def test_paginas_e_formularios(self):
        self.confirm(); services.emitir(self.d,self.u)
        urls=[reverse('lai:dashboard'),reverse('lai:detalhe',args=[self.d.pk]),reverse('lai:gestao'),reverse('lai:cadastros'),reverse('lai:importar'),reverse('lai:nova')]
        urls += [reverse('lai:acao',args=[self.d.pk,t]) for t in ['resposta','recurso','prorrogar','anexo','memorando','automacao','redirecionar']]
        for url in urls:
            with self.subTest(url=url): self.assertEqual(self.client.get(url).status_code,200)
    def test_csrf_em_mutacoes(self):
        c=Client(enforce_csrf_checks=True); c.force_login(self.u)
        self.assertEqual(c.post(reverse('lai:acao',args=[self.d.pk,'confirmar']),{'motivo':'x'}).status_code,403)
    def test_exportacao_neutraliza_formula(self):
        self.sec.nome='=HYPERLINK("malicioso")'; self.sec.save()
        text=self.client.get(reverse('lai:exportar')).content.decode('utf-8-sig'); self.assertIn("'=HYPERLINK",text)
    def test_upload_revisao_download_e_cadastro(self):
        resp=self.client.post(reverse('lai:importar'),{'arquivo':SimpleUploadedFile('nup.pdf',pdf_falso())})
        self.assertEqual(resp.status_code,302); imp=Importacao.objects.get()
        self.assertEqual(self.client.get(reverse('lai:original',args=[imp.pk])).status_code,200)
        self.assertContains(self.client.get(resp.url),'PDF original para conferência')
    def test_reimportacao_preserva_prazo(self):
        self.confirm(); original=self.d.vencimento_original
        resp=self.client.post(reverse('lai:reimportar',args=[self.d.pk]),{'arquivo':SimpleUploadedFile('nup.pdf',pdf_falso())})
        data={'nup':self.d.nup,'tipo':self.d.tipo,'teor':'Texto revisado','resumo':'Resumo revisto','pessoal':'on'}
        saved=self.client.post(resp.url,data)
        self.assertEqual(saved.status_code,302); self.d.refresh_from_db()
        self.assertEqual(self.d.vencimento_original,original); self.assertEqual(self.d.status,'CONFERENCIA')
        self.assertEqual(Demanda.objects.count(),1)

    def test_nao_pula_instancia_recursal(self):
        r=self.recurso(); e=self.etapa(r); self.decidir(e,'NEGADO')
        with self.assertRaises(ValidationError): self.etapa(r,instancia='COMISSAO')
    def test_prazo_recursal_nao_admite_ampliacao_arbitraria(self):
        with self.assertRaises(ValidationError): services.nova_etapa(self.recurso(),self.u,instancia='SECRETARIA',autoridade='Secretário',recebida_em=self.today,vencimento=self.today+timedelta(days=50),fundamento='Teste')
    def test_provimento_exige_cumprimento_para_encerrar(self):
        r=self.recurso(); e=self.etapa(r); self.decidir(e)
        result=self.client.post(reverse('lai:encerrar_recurso',args=[r.pk]),{'motivo':'Conclusão'})
        self.assertContains(result,'registre a etapa de cumprimento'); r.refresh_from_db(); self.assertFalse(r.encerrado)
    def test_suspensao_explicita_nao_altera_pedido(self):
        r=self.recurso(); e=self.etapa(r); self.decidir(e,'NEGADO'); cgm=self.etapa(r,instancia='CGM')
        consulta=self.etapa(r,instancia='PROCURADORIA'); original=self.d.vencimento
        services.prazo_etapa(cgm,self.u,'SUSPENDER',self.today,'Interpretação jurídica homologada de teste')
        cgm.refresh_from_db(); self.assertEqual(cgm.saldo_suspenso,5); self.assertEqual(self.d.vencimento,original)
        self.decidir(consulta,'PARECER'); services.prazo_etapa(cgm,self.u,'RETOMAR',self.today,'Parecer recebido')
        cgm.refresh_from_db(); self.assertIsNone(cgm.suspensa_em); self.assertEqual(cgm.vencimento,self.today+timedelta(days=5))
    def test_operador_inativo_nao_dispara_email(self):
        self.confirm(); c=services.emitir(self.d,self.u).comunicacoes.get()
        self.op.ativo=False; self.op.save(); self.assertEqual(processar_email(c.pk),'CANCELADO')
