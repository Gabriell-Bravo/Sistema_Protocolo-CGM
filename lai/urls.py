from django.urls import path
from . import views, views_extensao
app_name='lai'
urlpatterns=[path('',views.dashboard,name='dashboard'),path('falabr/pendentes/',views.pendentes,name='pendentes'),path('falabr/exportar/',views.exportar_falabr,name='exportar_falabr'),
    path('falabr/extensao/',views.extensao,name='extensao'),path('falabr/extensao/baixar/',views.extensao_baixar,name='extensao_baixar'),
    path('memorandos/',views.memorandos,name='memorandos'),
    path('falabr/memorandos/gerar/',views.memorandos_gerar,name='memorandos_gerar'),
    path('falabr/trazer/iniciar/',views.trazer_iniciar,name='trazer_iniciar'),
    path('falabr/automacao/iniciar/',views.automacao_iniciar,name='automacao_iniciar'),path('falabr/automacao/estado/',views.automacao_estado,name='automacao_estado'),path('falabr/automacao/cancelar/',views.automacao_cancelar,name='automacao_cancelar'),path('falabr/automacao/zip/',views.automacao_zip,name='automacao_zip'),path('falabr/automacao/abrir-pasta/',views.automacao_abrir_pasta,name='automacao_abrir_pasta'),
    path('ext/api/ping/',views_extensao.ping,name='ext_ping'),path('ext/api/leitura/',views_extensao.leitura,name='ext_leitura'),path('ext/api/progresso/',views_extensao.progresso,name='ext_progresso'),path('ext/api/pedido/',views_extensao.pedido,name='ext_pedido'),path('ext/api/falha/',views_extensao.falha,name='ext_falha'),path('ext/api/concluir/',views_extensao.concluir,name='ext_concluir'),
    path('importar/',views.importar,name='importar'),
    path('cadastros/',views.cadastros,name='cadastros'),path('cadastros/<str:slug>/novo/',views.cadastro,name='cadastro_novo'),path('cadastros/<str:slug>/<int:pk>/',views.cadastro,name='cadastro_editar'),
    path('nova/',views.nova,name='nova'),path('gestao/',views.gestao,name='gestao'),path('exportar/',views.exportar,name='exportar'),
    path('demanda/<int:pk>/',views.detalhe,name='detalhe'),path('demanda/<int:pk>/reimportar/',views.importar,name='reimportar'),
    path('demanda/<int:pk>/revisar/',views.nova,name='revisar'),path('demanda/<int:pk>/acao/<str:tipo>/',views.acao,name='acao'),
    path('documento/<uuid:doc_id>/',views.documento,name='documento'),path('importacao/<uuid:imp_id>/',views.original_importacao,name='original'),
    path('memorando/<int:memo_id>/pdf/',views.memorando_pdf,name='pdf'),path('memorando/<int:memo_id>/<str:tipo>/',views.memorando_acao,name='memorando_acao'),
    path('envio/<int:com_id>/',views.reconciliar,name='reconciliar'),path('recurso/<int:recurso_id>/etapa/',views.etapa,name='etapa'),
    path('recurso/<int:recurso_id>/encerrar/',views.encerrar_recurso,name='encerrar_recurso'),
    path('etapa/<int:etapa_id>/decisao/',views.decisao,name='decisao'),path('etapa/<int:etapa_id>/prazo/',views.decisao,{'prazo':True},name='prazo_etapa')]
