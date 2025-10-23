# processos_app/urls.py (Updated)

from django.urls import path
from . import views

urlpatterns = [
    path('', views.listar_processos, name='index'),
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
    # New URL for marking exit date/time
    path('processo/<int:process_id>/marcar_saida/',
         views.marcar_saida_processo, name='marcar_saida_processo'),  # NEW
    # User management
    path('register/', views.register, name='register'),
    path('manage_users/', views.manage_users, name='manage_users'),
    path('manage_users/update_level/<int:user_id>/',
         views.update_user_level, name='update_user_level'),
    path('manage_users/delete/<int:user_id>/',
         views.delete_user, name='delete_user'),
    # API endpoints for dynamic filters
    path('api/get_especies_by_genero/', views.get_especies_by_genero,
         name='get_especies_by_genero'),
    path('api/get_all_especies/', views.get_all_especies, name='get_all_especies'),
]
