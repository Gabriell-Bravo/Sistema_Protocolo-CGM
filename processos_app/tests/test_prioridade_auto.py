from processos_app.models import Prioridade
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

    def test_sem_match_retorna_none(self):
        self.assertIsNone(
            prioridade_auto.detectar_codigo({'contratada': 'Empresa Qualquer'}),
        )

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
