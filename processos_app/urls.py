# processos_app/urls.py (Updated)

from django.urls import path
from . import views
from . import views_gestao as gest
from . import views_pendencias as pend
from . import views_tramitacao as tram

urlpatterns = [
    path('', views.inicio, name='index'),
    path('cadastrar', views.cadastrar_processo, name='cadastrar_processo'),
    path('salvar', views.salvar_processo, name='salvar_processo'),
    path('listar', views.listar_processos, name='listar_processos'),
    path('processo/<int:process_id>/historico',
         views.ver_historico_processo, name='ver_historico_processo'),
    path('atualizar/<int:id>', views.atualizar_processo, name='atualizar_processo'),
    path('finalizados', views.listar_finalizados, name='listar_finalizados'),
    path('exportar_finalizados_excel', views.exportar_finalizados_excel,
         name='exportar_finalizados_excel'),
    path('get_process_by_number/<str:numero_processo>',
         views.get_process_by_number, name='get_process_by_number'),
    path('deletar/<int:id>', views.deletar_processo, name='deletar_processo'),
    path('processo/<int:process_id>/concluir_monitoramento/',
         views.concluir_monitoramento, name='concluir_monitoramento'),
    path('processo/<int:process_id>/marcar_saida/',
         views.marcar_saida_processo, name='marcar_saida_processo'),
    path('register/', views.register, name='register'),
    path('manage_users/', views.manage_users, name='manage_users'),
    path('manage_users/update_level/<int:user_id>/',
         views.update_user_level, name='update_user_level'),
    path('manage_users/delete/<int:user_id>/',
         views.delete_user, name='delete_user'),
    path('api/get_especies_by_genero/', views.get_especies_by_genero,
         name='get_especies_by_genero'),
    path('api/get_all_especies/', views.get_all_especies, name='get_all_especies'),
    path('analista/', views.area_analista, name='area_analista'),
    path('analista/processo/<int:process_id>/',
         views.analista_processo, name='analista_processo'),
    path('analista/processo/<int:process_id>/assumir/',
         views.assumir_processo, name='assumir_processo'),
    path('analista/processo/<int:process_id>/pendencia/',
         views.adicionar_pendencia, name='adicionar_pendencia'),
    path('analista/pendencia/<int:pendencia_id>/remover/',
         views.remover_pendencia, name='remover_pendencia'),
    path('gestao/', views.gestao_processos, name='gestao_processos'),
    path('gestao/processo/<int:process_id>/prioridade/',
         views.gestao_alterar_prioridade, name='gestao_alterar_prioridade'),

    # ------------------------------------------------------------------
    # Bloco A — endpoints específicos de tramitação (item 52)
    # ------------------------------------------------------------------
    path('tramitacao/<int:process_id>/assumir/',
         tram.assumir, name='tram_assumir'),
    path('tramitacao/<int:process_id>/direcionar-assinatura/',
         tram.direcionar_assinatura, name='tram_direcionar_assinatura'),
    path('tramitacao/<int:process_id>/liberar-assinatura/',
         tram.liberar_assinatura, name='tram_liberar_assinatura'),
    path('tramitacao/<int:process_id>/disponibilizar-retirada/',
         tram.disponibilizar_retirada, name='tram_disponibilizar_retirada'),
    path('tramitacao/<int:process_id>/alterar-destino/',
         tram.alterar_destino, name='tram_alterar_destino'),
    path('tramitacao/<int:process_id>/destino/',
         tram.form_alterar_destino, name='tram_form_alterar_destino'),
    path('tramitacao/<int:process_id>/prioridade/',
         tram.alterar_prioridade, name='tram_alterar_prioridade'),
    path('tramitacao/<int:process_id>/cancelar/',
         tram.cancelar_processo, name='tram_cancelar_processo'),
    path('protocolo/retirada/',
         tram.processos_para_retirada, name='processos_para_retirada'),
    path('protocolo/registrar-saida/',
         tram.registrar_saida, name='tram_registrar_saida'),
    path('gestao/liberados-assinatura/',
         tram.liberados_para_assinatura, name='gestao_liberados_assinatura'),

    # ------------------------------------------------------------------
    # Bloco B — pendências e diligências (itens 25 a 34)
    # ------------------------------------------------------------------
    path('gestao/diligencias/',
         pend.diligencias, name='gestao_diligencias'),
    path('diligencias/<int:pendencia_id>/indicar-atendimento/',
         pend.indicar_atendimento, name='pend_indicar_atendimento'),
    path('analista/atendimentos/',
         pend.meus_atendimentos, name='meus_atendimentos'),
    path('pendencias/<int:pendencia_id>/resolver/',
         pend.confirmar_resolucao, name='pend_confirmar_resolucao'),
    path('pendencias/<int:pendencia_id>/insuficiente/',
         pend.atendimento_insuficiente, name='pend_atendimento_insuficiente'),
    path('pendencias/<int:pendencia_id>/cancelar/',
         pend.cancelar_pendencia, name='pend_cancelar'),

    # ------------------------------------------------------------------
    # Bloco C — cadastros parametrizáveis e Gestão de Pessoas CGM
    # ------------------------------------------------------------------
    path('gestao/cadastros/', gest.cadastros, name='gestao_cadastros_inicio'),
    path('gestao/cadastros/<slug:slug>/', gest.cadastros, name='gestao_cadastros'),
    path('gestao/cadastros/<slug:slug>/salvar/', gest.cadastro_salvar,
         name='gestao_cadastro_salvar'),
    path('gestao/cadastros/<slug:slug>/<int:registro_id>/alternar/',
         gest.cadastro_alternar, name='gestao_cadastro_alternar'),
    path('gestao/pessoas/', gest.pessoas, name='gestao_pessoas'),
    path('gestao/pessoas/registrar/', gest.pessoas_registrar,
         name='gestao_pessoas_registrar'),
    path('gestao/pessoas/<int:registro_id>/desativar/', gest.pessoas_desativar,
         name='gestao_pessoas_desativar'),

    # ------------------------------------------------------------------
    # Bloco D — dashboard e indicadores (itens 47 a 50)
    # ------------------------------------------------------------------
    path('gestao/dashboard/', gest.dashboard, name='gestao_dashboard'),
]
