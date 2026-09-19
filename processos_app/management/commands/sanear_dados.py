"""Saneamento dos dados legados (itens 54, 55, 58 e 60).

Uso:
    python manage.py sanear_dados            # só relatório, não grava nada
    python manage.py sanear_dados --aplicar  # aplica as correções DERIVADAS

Regra: só é corrigido automaticamente o que pode ser deduzido com segurança
de outro dado do próprio registro. O restante é LISTADO para decisão humana.

FAÇA BACKUP ANTES DE --aplicar (./backup_banco.sh).
"""

from datetime import datetime, time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from processos_app.models import EventoProcesso, Pendencia, Processo

LIMITE_LISTAGEM = 30


class Command(BaseCommand):
    help = 'Relatório e saneamento dos dados legados (use --aplicar para gravar).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--aplicar', action='store_true',
            help='Aplica as correções derivadas. Sem esta opção nada é gravado.')

    # ------------------------------------------------------------------
    def _titulo(self, texto):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(texto))

    def _listar(self, qs, campos):
        for linha in qs.values_list(*campos)[:LIMITE_LISTAGEM]:
            self.stdout.write('   - ' + ' | '.join(str(v) for v in linha))
        total = qs.count()
        if total > LIMITE_LISTAGEM:
            self.stdout.write(f'   ... e mais {total - LIMITE_LISTAGEM}.')

    # ------------------------------------------------------------------
    def handle(self, *args, **opcoes):
        aplicar = opcoes['aplicar']
        modo = 'APLICANDO correções' if aplicar else 'SOMENTE RELATÓRIO (nada será gravado)'
        self.stdout.write(self.style.WARNING(f'Saneamento de dados — {modo}'))

        with transaction.atomic():
            self._saidas_legadas(aplicar)
            self._tem_pendencia(aplicar)
            self._recorrente(aplicar)
            self._numero_relatorio()
            self._cadastros_sem_vinculo()
            self._acervo_legado()

        self.stdout.write('')
        if aplicar:
            self.stdout.write(self.style.SUCCESS('Concluído. Correções derivadas aplicadas.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Relatório concluído. Rode novamente com --aplicar para gravar.'))

    # 1) item 58 — saída gravada só em data_saida ---------------------------
    def _saidas_legadas(self, aplicar):
        self._titulo('1. Processos com data de saída mas sem SAIDA_CONCLUIDA (item 58)')
        qs = (Processo.objects
              .filter(data_saida__isnull=False, cancelado_em__isnull=True)
              .exclude(situacao_tramite='SAIDA_CONCLUIDA'))
        total = qs.count()
        self.stdout.write(f'   Encontrados: {total}')
        if not total or not aplicar:
            return

        tz = timezone.get_current_timezone()
        eventos = []
        alterados = []
        for p in qs.iterator(chunk_size=500):
            quando = datetime.combine(p.data_saida, p.hora_saida or time(0, 0))
            p.situacao_tramite = 'SAIDA_CONCLUIDA'
            p.saida_concluida_em = p.saida_concluida_em or timezone.make_aware(quando, tz)
            alterados.append(p)
            eventos.append(EventoProcesso(
                processo=p, tipo='SAIDA_CONCLUIDA', criado_em=timezone.now(),
                descricao='Saída registrada no sistema anterior (saneamento de dados).',
                dados={'saneamento': True, 'data_saida': p.data_saida.isoformat(),
                       'destino': p.destino or ''}))
        Processo.objects.bulk_update(
            alterados, ['situacao_tramite', 'saida_concluida_em'], batch_size=500)
        EventoProcesso.objects.bulk_create(eventos, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f'   Corrigidos: {len(alterados)}'))

    # 2) item 31 — campo tem_pendencia divergente das pendências reais ------
    def _tem_pendencia(self, aplicar):
        self._titulo('2. Campo "tem_pendencia" divergente das pendências registradas (item 31)')
        abertas = Pendencia.objects.filter(
            processo=OuterRef('pk'), status__in=Pendencia.STATUS_ABERTOS)
        base = Processo.objects.annotate(aberta=Exists(abertas))

        marcado_sem_registro = base.filter(tem_pendencia='SIM', aberta=False)
        registro_sem_marca = base.filter(aberta=True).exclude(tem_pendencia='SIM')

        self.stdout.write(
            f'   Marcados SIM sem pendência aberta registrada: {marcado_sem_registro.count()} '
            '(NÃO corrigido automaticamente — pode ser pendência anotada só no campo; '
            'o sistema passou a usar apenas os registros de Pendência)')
        self._listar(marcado_sem_registro, ['id', 'numero_processo', 'secretaria'])

        n = registro_sem_marca.count()
        self.stdout.write(f'   Com pendência aberta mas marcados NÃO: {n}')
        if n and aplicar:
            ids = list(registro_sem_marca.values_list('id', flat=True))
            Processo.objects.filter(id__in=ids).update(tem_pendencia='SIM')
            self.stdout.write(self.style.SUCCESS(f'   Corrigidos para SIM: {n}'))

    # 3) item 54 — recorrente fora do padrão ------------------------------
    def _recorrente(self, aplicar):
        self._titulo('3. Campo "recorrente" fora do padrão SIM/NAO (item 54)')
        qs = Processo.objects.exclude(recorrente__in=['SIM', 'NAO'])
        self.stdout.write(f'   Encontrados: {qs.count()} (a migration 0017 já converteu as variações conhecidas)')
        self._listar(qs, ['id', 'numero_processo', 'recorrente'])
        # Não há conversão automática: valor desconhecido exige decisão.

    # 4) item 55 — número de relatório duplicado ---------------------------
    def _numero_relatorio(self):
        self._titulo('4. Números de relatório repetidos (item 55)')
        dup = (Processo.objects
               .exclude(Q(numero_relatorio__isnull=True) | Q(numero_relatorio=''))
               .filter(cancelado_em__isnull=True)
               .values('numero_relatorio')
               .annotate(qtd=Count('id'))
               .filter(qtd__gt=1)
               .order_by('-qtd'))
        self.stdout.write(f'   Números repetidos: {dup.count()} '
                          '(nenhuma trava de unicidade foi criada — decisão pendente)')
        for linha in dup[:LIMITE_LISTAGEM]:
            procs = Processo.objects.filter(
                numero_relatorio=linha['numero_relatorio'],
                cancelado_em__isnull=True).values_list('numero_processo', flat=True)
            self.stdout.write(f"   - {linha['numero_relatorio']} ({linha['qtd']}x): "
                              + ', '.join(procs))

    # 5) itens 19–21 — texto sem vínculo com os cadastros --------------------
    def _cadastros_sem_vinculo(self):
        self._titulo('5. Registros sem vínculo com os cadastros (itens 19 a 21)')
        sem_especie = Processo.objects.filter(especie_fk__isnull=True)
        sem_secretaria = Processo.objects.filter(secretaria_fk__isnull=True)
        sem_destino = (Processo.objects.filter(destino_fk__isnull=True)
                       .exclude(Q(destino__isnull=True) | Q(destino='')))
        self.stdout.write(f'   Sem espécie vinculada: {sem_especie.count()}')
        self._listar(sem_especie.values('especie').annotate(n=Count('id')).order_by('-n'),
                     ['especie', 'n'])
        self.stdout.write(f'   Sem secretaria vinculada: {sem_secretaria.count()}')
        self._listar(sem_secretaria.values('secretaria').annotate(n=Count('id')).order_by('-n'),
                     ['secretaria', 'n'])
        self.stdout.write(f'   Destino em texto sem unidade cadastrada: {sem_destino.count()} '
                          '(cadastre a unidade em Gestão > Cadastros e rode a vinculação)')
        self._listar(sem_destino.values('destino').annotate(n=Count('id')).order_by('-n'),
                     ['destino', 'n'])

    # 6) acervo anterior à nova tramitação --------------------------------
    def _acervo_legado(self):
        self._titulo('6. Acervo anterior à nova tramitação (saída pelo caminho de transição)')
        cadastro = EventoProcesso.objects.filter(
            processo=OuterRef('pk'), tipo='PROCESSO_CADASTRADO')
        qs = (Processo.objects
              .filter(situacao_tramite='DISPONIVEL', analista_responsavel__isnull=True,
                      data_saida__isnull=True, cancelado_em__isnull=True)
              .annotate(tem_cadastro=Exists(cadastro))
              .filter(tem_cadastro=False))
        self.stdout.write(f'   Processos ativos sem evento de cadastro: {qs.count()} '
                          '(podem receber saída direta pelo Protocolo até o acervo zerar)')
