"""Apoio comum aos testes. Rodar com:  python manage.py test processos_app

Sem as variáveis POSTGRES_*, o settings usa SQLite — os testes rodam em
qualquer máquina com as dependências do requirements.txt instaladas.
"""

import datetime

from django.contrib.auth.models import User
from django.test import TestCase

from processos_app.models import EspecieProcesso, Processo, UnidadeAdministrativa
from processos_app.services import processos as svc_processos
from processos_app.services import tramitacao

LIC = 'LICITACOES_E_CONTRATOS'
LIQ = 'LIQUIDACOES'


def criar_usuario(username, papel, **extra):
    """O signal post_save cria o Profile; aqui só definimos o papel."""
    user = User.objects.create_user(username=username, password='senha-teste-123',
                                    first_name=username.capitalize(), **extra)
    user.profile.papel = papel
    user.profile.save()
    return user


class BaseProcessoTestCase(TestCase):
    """Usuários de cada papel + espécies de teste nos dois grupos."""

    @classmethod
    def setUpTestData(cls):
        cls.protocolo = criar_usuario('protocolo', 'PROTOCOLO')
        cls.analista_lic = criar_usuario('ana_lic', 'ANALISTA_LICITACOES')
        cls.analista_lic2 = criar_usuario('beto_lic', 'ANALISTA_LICITACOES')
        cls.analista_liq = criar_usuario('caio_liq', 'ANALISTA_LIQUIDACOES')
        cls.gestao = criar_usuario('gestora', 'GESTAO')

        cls.especie_lic = EspecieProcesso.objects.create(
            nome='Espécie Teste Licitação', grupo=LIC, ativo=True)
        cls.especie_liq = EspecieProcesso.objects.create(
            nome='Espécie Teste Liquidação', grupo=LIQ, ativo=True,
            gera_relatorio=True)
        cls.especie_monit = EspecieProcesso.objects.create(
            nome='Espécie Teste Monitorada', grupo=LIC, ativo=True,
            tipo_monitoramento='TRIMESTRAL')
        cls.unidade = UnidadeAdministrativa.objects.create(
            nome='Unidade de Teste', ativo=True)

    # ------------------------------------------------------------------
    def dados_protocolo(self, especie=None, **extra):
        especie = especie or self.especie_lic
        dados = {
            'numero_processo': extra.pop('numero_processo', '1234/2026'),
            'volume': '1',
            'secretaria': 'Unidade de Teste',
            'data_entrada': '2026-09-01',
            'hora_entrada': '10:00',
            'especie': especie.nome,
            'especie_id': str(especie.id),
            'genero': especie.grupo,
            'objeto': 'Objeto de teste',
            'contratada': 'Empresa X',
            'recorrente': 'NAO',
        }
        dados.update(extra)
        return dados

    def novo_processo(self, especie=None, **extra):
        return svc_processos.criar_processo(self.dados_protocolo(especie, **extra),
                                            self.protocolo)

    def preencher_analise(self, processo, **campos):
        """Preenche direto no banco os campos exigidos para liberar."""
        valores = {'status_analise': 'PROSSEGUIMENTO_SEM_RESSALVA',
                   'numero_despacho': '10/2026', 'destino': 'Unidade de Teste'}
        valores.update(campos)
        Processo.objects.filter(id=processo.id).update(**valores)
        processo.refresh_from_db()
        return processo

    def processo_em_analise(self, analista=None, especie=None, completo=True):
        analista = analista or self.analista_lic
        processo = self.novo_processo(especie)
        tramitacao.assumir(processo.id, analista)
        processo.refresh_from_db()
        if completo:
            self.preencher_analise(processo)
        return processo

    def processo_disponivel_retirada(self):
        processo = self.processo_em_analise()
        tramitacao.liberar_assinatura(processo.id, self.analista_lic)
        tramitacao.disponibilizar_retirada(processo.id, self.protocolo)
        processo.refresh_from_db()
        return processo

    @staticmethod
    def hoje():
        return datetime.date.today()
