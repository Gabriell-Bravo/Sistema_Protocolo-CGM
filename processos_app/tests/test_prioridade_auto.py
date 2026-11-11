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
                'nome': 'Prioridade Alta',
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

    def test_lista_todos_os_processos_so_ultima_analise_de_cada_numero(self):
        saude = self.novo_processo(
            contratada='CLARICIA FLORES Buffet',
            numero_processo='22899/2022',
            secretaria='Saúde',
        )
        Processo.objects.filter(id=saude.id).update(
            data_analise=datetime.date(2026, 3, 13),
            periodo='mar/2026',
        )
        passagem_antiga = self.novo_processo(
            contratada='CLARICIA FLORES Buffet',
            numero_processo='22899/2022',
            secretaria='Saúde',
        )
        Processo.objects.filter(id=passagem_antiga.id).update(
            data_analise=datetime.date(2024, 1, 10),
            periodo='jan/2024',
        )
        educacao = self.novo_processo(
            contratada='CLARICIA FLORES Ltda',
            numero_processo='20523/2023',
            secretaria='Educação',
        )
        Processo.objects.filter(id=educacao.id).update(
            data_analise=datetime.date(2025, 11, 28),
            periodo='nov/2025',
        )
        linhas = [
            linha
            for secao in prioridade_auto.listar_empresas_com_ultima_analise()
            for linha in secao['linhas']
            if linha['empresa'] == 'CLARICIA FLORES'
        ]
        self.assertEqual(
            [
                (linha['numero_processo'], linha['secretaria'], linha['periodo'])
                for linha in linhas
            ],
            [
                ('22899/2022', 'Saúde', 'mar/2026'),
                ('20523/2023', 'Educação', 'nov/2025'),
            ],
        )
        self.assertEqual(linhas[0]['prioridade'], 'Prioridade recorrente')
        self.assertEqual(linhas[0]['contratada'], 'CLARICIA FLORES Buffet')
        sem_processo = [
            linha
            for secao in prioridade_auto.listar_empresas_com_ultima_analise()
            for linha in secao['linhas']
            if linha['empresa'] == 'HASHIMOTO'
        ]
        self.assertEqual(len(sem_processo), 1)
        self.assertEqual(sem_processo[0]['numero_processo'], '')

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
