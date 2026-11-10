import datetime

from processos_app.models import Prioridade, Processo
from processos_app.services import prioridade_auto
from processos_app.services import prazos

from .base import BaseProcessoTestCase


class PrioridadeAutoTest(BaseProcessoTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Prioridade.objects.update_or_create(
            codigo='URGENTE',
            defaults={
                'nome': 'Urgente',
                'prazo_dias': 1,
                'ordem': 10,
                'ativo': True,
                'palavras_chave': 'JP\nAMX\nELITE',
            },
        )
        Prioridade.objects.update_or_create(
            codigo='PRIORITARIO',
            defaults={
                'nome': 'Prioridade de obras',
                'prazo_dias': 2,
                'ordem': 20,
                'ativo': True,
                'palavras_chave': 'HYDRA\nMIDAS\nGLOBO',
            },
        )
        Prioridade.objects.update_or_create(
            codigo='RECORRENTE',
            defaults={
                'nome': 'Prioridade recorrente',
                'prazo_dias': 3,
                'ordem': 25,
                'ativo': True,
                'palavras_chave': 'CLARICIA FLORES\nR3M\nHASHIMOTO',
            },
        )
        Prioridade.objects.update_or_create(
            codigo='NORMAL',
            defaults={
                'nome': 'Normal',
                'prazo_dias': 7,
                'ordem': 40,
                'ativo': True,
                'palavras_chave': '',
            },
        )
        prazos.limpar_cache()

    def test_detecta_urgente_por_sigla(self):
        self.assertEqual(
            prioridade_auto.detectar_codigo({'contratada': 'JP Serviços'}),
            'URGENTE',
        )

    def test_detecta_obras(self):
        self.assertEqual(
            prioridade_auto.detectar_codigo({'contratada': 'Construtora HYDRA Ltda'}),
            'PRIORITARIO',
        )

    def test_detecta_recorrente(self):
        self.assertEqual(
            prioridade_auto.detectar_codigo({'contratada': 'CLARICIA FLORES buffet'}),
            'RECORRENTE',
        )

    def test_urgente_vence_recorrente(self):
        self.assertEqual(
            prioridade_auto.detectar_codigo({
                'contratada': 'JP',
                'objeto': 'serviço com HASHIMOTO',
            }),
            'URGENTE',
        )

    def test_n_recorrente_nao_detecta_por_palavra(self):
        Prioridade.objects.update_or_create(
            codigo='N_RECORRENTE',
            defaults={
                'nome': 'Prioridade N/Recorrente',
                'prazo_dias': 3,
                'ordem': 27,
                'ativo': True,
                'palavras_chave': 'EMPRESA SO DESTA VEZ',
            },
        )
        prazos.limpar_cache()
        self.assertIsNone(prioridade_auto.detectar_codigo({
            'contratada': 'EMPRESA SO DESTA VEZ Ltda',
        }))

    def test_sem_match_retorna_none(self):
        self.assertIsNone(
            prioridade_auto.detectar_codigo({'contratada': 'Empresa Qualquer'}),
        )

    def test_sugerir_retorna_termo_e_nome(self):
        achado = prioridade_auto.sugerir({'contratada': 'JP Serviços'})
        self.assertEqual(achado['codigo'], 'URGENTE')
        self.assertEqual(achado['termo'], 'JP')
        self.assertEqual(achado['nome'], 'Urgente')
        self.assertEqual(achado['prazo_dias'], 1)

    def test_criacao_aplica_prioridade_e_prazo(self):
        obras = self.novo_processo(
            contratada='HYDRA Engenharia',
            numero_processo='prio-obras/2026',
        )
        self.assertEqual(obras.prioridade, 'PRIORITARIO')
        self.assertEqual(obras.prazo_dias, 2)
        self.assertEqual(obras.prioridade_linha_class, 'tr-prio-obras')

        recorrente = self.novo_processo(
            contratada='R3M Alimentos',
            numero_processo='prio-rec/2026',
        )
        self.assertEqual(recorrente.prioridade, 'RECORRENTE')
        self.assertEqual(recorrente.prazo_dias, 3)
        self.assertEqual(recorrente.prioridade_linha_class, 'tr-prio-recorrente')

        urgente = self.novo_processo(
            contratada='AMX Locações',
            numero_processo='prio-urg/2026',
        )
        self.assertEqual(urgente.prioridade, 'URGENTE')
        self.assertEqual(urgente.prazo_dias, 1)
        self.assertEqual(urgente.prioridade_linha_class, 'tr-prio-urgente')

    def test_protocolo_pode_recusar_sugestao_automatica(self):
        processo = self.novo_processo(
            contratada='JP Serviços',
            prioridade='NORMAL',
            manter_prioridade_informada=True,
            numero_processo='prio-recusa/2026',
        )
        self.assertEqual(processo.prioridade, 'NORMAL')

    def test_lista_empresas_automaticas_por_prioridade(self):
        Prioridade.objects.filter(codigo='PRIORITARIO').update(
            palavras_chave='HYDRA\nM. COSTA\nM COSTA\nMIDAS')
        secoes = {
            s['codigo']: s for s in prioridade_auto.listar_empresas_automaticas()
        }
        self.assertEqual(
            [s['codigo'] for s in prioridade_auto.listar_empresas_automaticas()],
            ['URGENTE', 'PRIORITARIO', 'RECORRENTE'],
        )
        self.assertEqual(secoes['URGENTE']['empresas'], ['AMX', 'ELITE', 'JP'])
        # Variantes iguais (acento/espaço) viram uma só no PDF.
        self.assertEqual(secoes['PRIORITARIO']['empresas'], ['HYDRA', 'M. COSTA', 'MIDAS'])
        self.assertIn('HASHIMOTO', secoes['RECORRENTE']['empresas'])

    def test_lista_puxa_periodo_da_ultima_analise_do_processo(self):
        antigo = self.novo_processo(
            contratada='CLARICIA FLORES Buffet',
            numero_processo='100/2025',
        )
        Processo.objects.filter(id=antigo.id).update(
            data_analise=datetime.date(2025, 3, 1),
            periodo='jan/2025',
        )
        recente = self.novo_processo(
            contratada='CLARICIA FLORES Ltda',
            numero_processo='200/2026',
        )
        Processo.objects.filter(id=recente.id).update(
            data_analise=datetime.date(2026, 8, 15),
            periodo='jul a ago/2026',
        )
        por_empresa = {
            linha['empresa']: linha
            for secao in prioridade_auto.listar_empresas_com_ultima_analise()
            for linha in secao['linhas']
        }
        linha = por_empresa['CLARICIA FLORES']
        self.assertEqual(linha['numero_processo'], '200/2026')
        self.assertEqual(linha['periodo'], 'jul a ago/2026')
        self.assertEqual(
            linha['rotulo'],
            '200/2026 — CLARICIA FLORES Ltda — Prioridade recorrente — jul a ago/2026',
        )

    def test_pdf_empresas_automaticas_somente_administrador(self):
        from django.urls import reverse

        from .base import criar_usuario

        pdf = prioridade_auto.gerar_pdf_empresas_automaticas()
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 800)

        admin = criar_usuario('admin_prio', 'GESTAO', is_superuser=True)
        self.client.force_login(admin)
        resposta = self.client.get(reverse('gestao_prioridades_empresas_pdf'))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta['Content-Type'], 'application/pdf')
        self.assertTrue(resposta.content.startswith(b'%PDF'))
        self.assertIn(
            'empresas-prioridade-automatica-',
            resposta['Content-Disposition'],
        )
        pagina = self.client.get(reverse('gestao_cadastros', kwargs={'slug': 'prioridades'}))
        self.assertContains(pagina, 'PDF das empresas')
        self.assertContains(pagina, reverse('gestao_prioridades_empresas_pdf'))

        self.client.force_login(self.gestao)
        negado_gestao = self.client.get(reverse('gestao_prioridades_empresas_pdf'))
        self.assertEqual(negado_gestao.status_code, 403)
        pagina_gestao = self.client.get(
            reverse('gestao_cadastros', kwargs={'slug': 'prioridades'}))
        self.assertNotContains(pagina_gestao, 'PDF das empresas')

        self.client.force_login(self.protocolo)
        negado = self.client.get(reverse('gestao_prioridades_empresas_pdf'))
        self.assertEqual(negado.status_code, 403)
