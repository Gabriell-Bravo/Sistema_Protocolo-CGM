import datetime

from django.urls import reverse
from django.utils import timezone

from ..models import Processo
from ..services import indicadores
from .base import BaseProcessoTestCase


def _dia(texto):
    return datetime.date.fromisoformat(texto)


def _momento(texto, hora=10):
    naive = datetime.datetime.combine(_dia(texto), datetime.time(hora, 0))
    return timezone.make_aware(naive)


class FluxoEntradasSaidasTest(BaseProcessoTestCase):
    """Gráfico principal do dashboard: quantos entraram e quantos saíram."""

    def _processo(self, numero, entrada, saida=None):
        processo = self.novo_processo(numero_processo=numero)
        campos = {'data_entrada': _dia(entrada)}
        if saida:
            campos['saida_concluida_em'] = _momento(saida)
        Processo.objects.filter(id=processo.id).update(**campos)
        return processo

    def test_conta_entradas_saidas_e_acervo_por_dia(self):
        self._processo('1/2026', '2026-03-01', '2026-03-02')
        self._processo('2/2026', '2026-03-01')
        self._processo('3/2026', '2026-03-03', '2026-03-03')
        self._processo('4/2026', '2026-02-20', '2026-03-03')  # já estava na CGM

        dados = indicadores.fluxo(_dia('2026-03-01'), _dia('2026-03-04'), 'dia')
        por_dia = {b['chave']: b for b in dados['baldes']}

        self.assertEqual(dados['unidade'], 'dia')
        self.assertEqual(len(dados['baldes']), 4)
        self.assertEqual(
            (por_dia['2026-03-01']['entradas'], por_dia['2026-03-01']['saidas']), (2, 0))
        self.assertEqual(
            (por_dia['2026-03-02']['entradas'], por_dia['2026-03-02']['saidas']), (0, 1))
        self.assertEqual(
            (por_dia['2026-03-03']['entradas'], por_dia['2026-03-03']['saidas']), (1, 2))
        self.assertEqual(dados['totais']['entradas'], 3)
        self.assertEqual(dados['totais']['saidas'], 3)
        self.assertEqual(dados['totais']['saldo'], 0)
        # Acervo ao fim bate com o estoque dos indicadores do período.
        periodo = indicadores.periodo(_dia('2026-03-01'), _dia('2026-03-04'))
        self.assertEqual(dados['totais']['estoque_inicial'], periodo['estoque_inicial'])
        self.assertEqual(dados['totais']['estoque_final'], periodo['estoque_final'])
        self.assertEqual(dados['baldes'][-1]['acervo'], periodo['estoque_final'])

    def test_agrupa_por_semana_mes_e_ano(self):
        self._processo('10/2026', '2026-01-05', '2026-01-20')  # segunda
        self._processo('11/2026', '2026-01-07')
        self._processo('12/2026', '2026-02-10', '2026-02-11')
        self._processo('13/2025', '2025-12-15', '2026-01-02')

        semanas = indicadores.fluxo(_dia('2026-01-05'), _dia('2026-01-25'), 'semana')
        self.assertEqual([b['chave'] for b in semanas['baldes']],
                         ['2026-01-05', '2026-01-12', '2026-01-19'])
        self.assertEqual([b['entradas'] for b in semanas['baldes']], [2, 0, 0])
        self.assertEqual([b['saidas'] for b in semanas['baldes']], [0, 0, 1])

        meses = indicadores.fluxo(_dia('2026-01-01'), _dia('2026-02-28'), 'mes')
        self.assertEqual([b['rotulo'] for b in meses['baldes']], ['jan/26', 'fev/26'])
        self.assertEqual([b['entradas'] for b in meses['baldes']], [2, 1])
        self.assertEqual([b['saidas'] for b in meses['baldes']], [2, 1])

        anos = indicadores.fluxo(_dia('2025-01-01'), _dia('2026-12-31'), 'ano')
        self.assertEqual([b['rotulo'] for b in anos['baldes']], ['2025', '2026'])
        self.assertEqual([b['entradas'] for b in anos['baldes']], [1, 3])

    def test_periodo_longo_sobe_a_unidade_para_nao_gerar_barras_demais(self):
        dados = indicadores.fluxo(_dia('2025-01-01'), _dia('2026-12-31'), 'dia')
        self.assertEqual(dados['unidade'], 'mes')
        self.assertLessEqual(len(dados['baldes']), 62)

    def test_compara_com_periodo_anterior_e_respeita_filtros(self):
        self._processo('20/2026', '2026-03-10')
        self._processo('21/2026', '2026-03-11')
        self._processo('22/2026', '2026-03-02')  # período anterior (10 dias antes)
        outro = self.novo_processo(self.especie_liq, numero_processo='23/2026')
        Processo.objects.filter(id=outro.id).update(data_entrada=_dia('2026-03-10'))

        dados = indicadores.fluxo(_dia('2026-03-10'), _dia('2026-03-19'), 'dia')
        self.assertEqual(dados['totais']['entradas'], 3)
        self.assertEqual(dados['anterior']['entradas'], 1)
        self.assertEqual(dados['anterior']['var_entradas'], 200)

        so_liquidacoes = indicadores.fluxo(
            _dia('2026-03-10'), _dia('2026-03-19'), 'dia', grupo=outro.genero)
        self.assertEqual(so_liquidacoes['totais']['entradas'], 1)

    def test_data_invertida_e_cancelado_fora(self):
        cancelado = self._processo('30/2026', '2026-03-10')
        Processo.objects.filter(id=cancelado.id).update(cancelado_em=timezone.now())
        self._processo('31/2026', '2026-03-10')
        dados = indicadores.fluxo(_dia('2026-03-12'), _dia('2026-03-09'), 'dia')
        self.assertEqual(dados['inicio'], '2026-03-09')
        self.assertEqual(dados['totais']['entradas'], 1)

    def test_pagina_traz_os_dados_do_grafico_e_aceita_unidades(self):
        self._processo('40/2026', '2026-03-10', '2026-03-11')
        self.client.force_login(self.gestao)
        url = reverse('gestao_dashboard')

        pagina = self.client.get(url + '?inicio=2026-03-01&fim=2026-03-31&unidade=dia')
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, 'id="dash-fluxo-dados"')
        self.assertContains(pagina, 'Entraram × saíram por dia')
        self.assertEqual(pagina.context['fluxo']['totais']['entradas'], 1)
        self.assertEqual(pagina.context['fluxo']['totais']['saidas'], 1)

        for unidade, esperado in (('semana', 12), ('mes', 12), ('ano', 5)):
            resposta = self.client.get(url + f'?unidade={unidade}')
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.context['unidade'], unidade)
            self.assertEqual(len(resposta.context['fluxo']['baldes']), esperado)

        # Dia sem datas = hoje, com os 6 dias anteriores como contexto.
        invalida = self.client.get(url + '?unidade=quinzena')
        self.assertEqual(invalida.context['unidade'], 'dia')
        self.assertTrue(invalida.context['fluxo']['modo_dia'])
        self.assertEqual(len(invalida.context['fluxo']['baldes']), 7)
        self.assertEqual(invalida.context['inicio'], timezone.localdate())

        self.client.force_login(self.protocolo)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_dia_mostra_so_o_dia_escolhido_com_contexto(self):
        self._processo('50/2026', '2026-03-10', '2026-03-10')
        self._processo('51/2026', '2026-03-10')
        self._processo('52/2026', '2026-03-09', '2026-03-10')
        self._processo('53/2026', '2026-03-08')

        dados = indicadores.fluxo(
            _dia('2026-03-10'), _dia('2026-03-10'), 'dia', contexto_dias=6)
        self.assertTrue(dados['modo_dia'])
        self.assertEqual(dados['destaque'], '2026-03-10')
        self.assertEqual(dados['rotulo_anterior'], 'dia anterior')
        self.assertEqual(
            [b['chave'] for b in dados['baldes']][0], '2026-03-04')
        self.assertEqual(len(dados['baldes']), 7)
        # Totais só do dia escolhido; as barras anteriores ficam no gráfico.
        self.assertEqual(dados['totais']['entradas'], 2)
        self.assertEqual(dados['totais']['saidas'], 2)
        self.assertEqual(dados['anterior']['entradas'], 1)
        ultimo = dados['baldes'][-1]
        self.assertEqual((ultimo['entradas'], ultimo['saidas']), (2, 2))
        # "Na CGM": início = fim do dia anterior; fim = fim do dia escolhido.
        anterior = dados['baldes'][-2]
        self.assertEqual(dados['totais']['estoque_inicial'], anterior['acervo'])
        self.assertEqual(dados['totais']['estoque_final'], ultimo['acervo'])
        periodo = indicadores.periodo(_dia('2026-03-10'), _dia('2026-03-10'))
        self.assertEqual(dados['totais']['estoque_final'], periodo['estoque_final'])

        # Sem contexto, vários dias, ou outra unidade: não é "modo dia".
        sem_contexto = indicadores.fluxo(
            _dia('2026-03-10'), _dia('2026-03-10'), 'dia')
        self.assertEqual(len(sem_contexto['baldes']), 1)
        varios = indicadores.fluxo(
            _dia('2026-03-08'), _dia('2026-03-10'), 'dia', contexto_dias=6)
        self.assertFalse(varios['modo_dia'])
        self.assertEqual(len(varios['baldes']), 3)

    def test_pagina_dia_aceita_so_a_data_inicial_e_nao_passa_de_hoje(self):
        self._processo('60/2026', '2026-03-10')
        self.client.force_login(self.gestao)
        url = reverse('gestao_dashboard')

        um_dia = self.client.get(url + '?unidade=dia&inicio=2026-03-10')
        self.assertEqual(um_dia.context['inicio'], _dia('2026-03-10'))
        self.assertEqual(um_dia.context['fim'], _dia('2026-03-10'))
        self.assertTrue(um_dia.context['fluxo']['modo_dia'])
        self.assertEqual(um_dia.context['fluxo']['totais']['entradas'], 1)
        self.assertContains(um_dia, 'Entraram × saíram em 10/03/2026')
        self.assertContains(um_dia, 'data-dia-nav="-1"')

        futuro = self.client.get(url + '?unidade=dia&inicio=2999-01-01')
        self.assertEqual(futuro.context['inicio'], timezone.localdate())

        varios = self.client.get(
            url + '?unidade=dia&inicio=2026-03-08&fim=2026-03-10')
        self.assertFalse(varios.context['fluxo']['modo_dia'])
        self.assertEqual(len(varios.context['fluxo']['baldes']), 3)


class CardsDoDashboardTest(BaseProcessoTestCase):
    """Cards do topo: só os que importam, somando sempre o total em tramitação."""

    def test_cards_enxutos_e_retirada_conta_com_o_controlador(self):
        situacoes = ['DISPONIVEL', 'DISPONIVEL', 'EM_ANALISE', 'ASSINATURA_DIRECIONADA',
                     'AGUARDANDO_ASSINATURA', 'DISPONIVEL_RETIRADA', 'DISPONIVEL_RETIRADA']
        for indice, situacao in enumerate(situacoes, start=1):
            processo = self.novo_processo(numero_processo=f'{indice}/2026')
            Processo.objects.filter(id=processo.id).update(situacao_tramite=situacao)

        cartoes = {c['rotulo']: c['valor'] for c in indicadores.cards()}

        self.assertEqual(
            list(cartoes),
            ['Em tramitação', 'Disponíveis para análise', 'Em análise',
             'Com o Controlador', 'Urgentes', 'Diligências'])
        self.assertEqual(cartoes['Em tramitação'], 7)
        self.assertEqual(cartoes['Disponíveis para análise'], 2)
        self.assertEqual(cartoes['Em análise'], 2)
        self.assertEqual(cartoes['Com o Controlador'], 3)
        self.assertEqual(
            cartoes['Disponíveis para análise'] + cartoes['Em análise']
            + cartoes['Com o Controlador'],
            cartoes['Em tramitação'])

        situacao = {i['rotulo']: i['valor'] for i in indicadores.panorama()['situacao']}
        self.assertEqual(situacao['Com o Controlador'], 3)
        self.assertNotIn('Disponível para retirada', situacao)
