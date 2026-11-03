import secrets
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from lai.models import Secretaria, Operador, PoliticaPrazo, ModeloMemorando, Demanda
from lai.services import confirmar, emitir, monitorar

class Command(BaseCommand):
    help='Cria demonstração fictícia. Exige DEBUG e SMTP desativado. Não usar em produção.'
    def add_arguments(self,parser): parser.add_argument('--usuario',default='demo.lai')
    def handle(self,*args,**opts):
        if not settings.DEBUG or getattr(settings,'LAI_LIVE_EMAIL',False): raise CommandError('Demonstração permitida apenas em ambiente local sem envio real.')
        username=opts['usuario']; user,created=get_user_model().objects.get_or_create(username=username)
        if created:
            password=secrets.token_urlsafe(14); user.set_password(password); user.first_name='Operador'; user.last_name='Demonstração'; user.save()
            self.stdout.write(f'Usuário: {username}\nSenha inicial local: {password}')
        else: self.stdout.write('Usuário existente; senha mantida.')
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='lai'))
        op,_=Operador.objects.get_or_create(usuario=user,defaults=dict(nome='Operador de demonstração',cargo='Operador LAI',email='operador@example.invalid',acesso_global=True,autoridade_recursal=True))
        policy,_=PoliticaPrazo.objects.get_or_create(versao='Demonstração v1 — dias corridos',defaults={'fundamento':'Configuração demonstrativa; validar contagem municipal antes da produção.'})
        ModeloMemorando.objects.get_or_create(versao='Padrão LAI v1')
        today=timezone.localdate()
        for i,(sigla,nome,resumo,days) in enumerate([('ADM','Secretaria de Administração','Informações sobre estrutura administrativa e quadro de cargos.',4),('EDU','Secretaria de Educação','Dados agregados de matrículas da rede municipal.',12),('SAU','Secretaria de Saúde','Informações públicas sobre unidades de atendimento.',19)],1):
            sec,_=Secretaria.objects.get_or_create(sigla=sigla,defaults=dict(nome=nome,email=f'{sigla.lower()}@example.invalid'))
            d,new=Demanda.objects.get_or_create(nup_normalizada=f'00000202600000{i}00',defaults=dict(nup=f'00000.2026.00000{i}-00',tipo='Acesso à Informação',cadastro_falabr=today-timedelta(days=days),marco_inicial=today-timedelta(days=days),vencimento_original=today+timedelta(days=20-days),prazo_interno=today+timedelta(days=max(0,18-days)),teor=resumo,resumo=resumo,secretaria=sec,operador=op,politica=policy,pessoal=False))
            if new:
                d=confirmar(d,user,'Dados fictícios conferidos para demonstração.')
                emitir(d,user)
        monitorar(); self.stdout.write(self.style.SUCCESS('Dados fictícios preparados. Não houve envio de e-mails.'))
