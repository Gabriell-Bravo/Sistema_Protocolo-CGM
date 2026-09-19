# Sistema de Protocolo e Gestão de Processos — CGM
## Relatório de alterações (Blocos A a E) — para o TI

Base recebida: `Sistema_2_Claude_exato.zip` (migrations até 0015).
Entrega: projeto completo, back-end e front-end, com migrations 0016 e 0017.

> **Leia primeiro a seção 9 (Pontos de atenção).** O código foi verificado
> de forma estática (sintaxe, tipos, rotas, templates e migrations x models),
> mas **não foi executado**: o ambiente em que foi preparado não tinha acesso
> ao PyPI para instalar o Django. A execução dos testes é o primeiro passo do TI.

---

## 1. Roteiro de implantação (ordem obrigatória)

```bash
# 1. TESTAR NO NOTEBOOK, antes de subir. Sem .env na pasta = SQLite automático.
#    (Se existir .env com POSTGRES_*, o Django tenta o Postgres "db" e falha fora do docker.)
pip install -r requirements.txt
DJANGO_DEBUG=True python manage.py check
DJANGO_DEBUG=True python manage.py makemigrations --check --dry-run   # esperado: "No changes detected"
DJANGO_DEBUG=True python manage.py test processos_app                 # 78 testes

# 2. NO SERVIDOR: backup do banco ATUAL, antes de qualquer coisa
./backup_banco.sh                      # gera backups/protocolo_AAAAMMDD_HHMMSS.dump

# 3. Criar o .env a partir do modelo (nunca versionar o .env)
cp env.example .env                    # preencher DJANGO_SECRET_KEY, senhas, hosts
                                       # (manter os mesmos POSTGRES_* que o banco já usa)

# 4. Subir
docker compose build
docker compose up -d                   # o compose já roda migrate + collectstatic

# 5. Saneamento: primeiro SÓ relatório, depois aplicar
docker exec protocolo_web python manage.py sanear_dados
docker exec protocolo_web python manage.py sanear_dados --aplicar

# 6. Conferir o papel de cada usuário (Gerenciar usuários)
# 7. Agendar 1x/dia (cron do servidor):
#    docker exec protocolo_web python manage.py atualizar_status_monitoramento
```

Reverter: `docker exec -i protocolo_db pg_restore -U <usuario> -d <banco> --clean --if-exists < backups/<arquivo>.dump`
e voltar a imagem anterior.

---

## 2. Arquivos criados

| Arquivo | Finalidade |
|---|---|
| `processos_app/__init__.py` | Não existia no zip recebido. Torna o app um pacote Python normal (necessário para a descoberta de testes). Se o projeto do servidor já tiver, é o mesmo arquivo vazio. |
| `processos_app/admin.py` | Admin do Django só para apoio do TI (Profile e cadastros). **Processo não é registrado de propósito.** |
| `processos_app/services/processos.py` | Criação única de processo (itens 17/18), whitelist de edição por papel (item 51), análise. |
| `processos_app/services/pendencias.py` | Ciclo de pendências e diligências (itens 25–34). |
| `processos_app/services/cadastros.py` | Unidades, espécies e prioridades para formulários e vínculos (itens 19–22). |
| `processos_app/services/gestao_pessoas.py` | Indisponibilidades e disponibilidade do dia (itens 23, 24, 48). |
| `processos_app/services/monitoramento.py` | Regra única de monitoramento (itens 41–44). |
| `processos_app/services/indicadores.py` | Cards, equipe, indicadores do período e tempos (itens 47–50). |
| `processos_app/views_pendencias.py` | Telas e ações de Diligências / Atendimentos. |
| `processos_app/views_gestao.py` | Cadastros, Gestão de Pessoas CGM e Dashboard. |
| `processos_app/migrations/0016_cadastros_gestao_pessoas.py` | 5 tabelas novas, 4 vínculos, carga inicial e conversão dos textos. |
| `processos_app/migrations/0017_recorrente_indices.py` | Normaliza `recorrente` (SIM/NAO) e cria 5 índices. |
| `processos_app/management/commands/sanear_dados.py` | Relatório e correção dos dados legados. |
| `processos_app/management/commands/atualizar_status_monitoramento.py` | Grava o status de monitoramento (para agendar). |
| `processos_app/tests/` (6 arquivos) | 78 testes automatizados (item 64). |
| `templates/gestao/dashboard.html`, `cadastros.html`, `pessoas.html`, `diligencias.html` | Telas novas da Gestão. |
| `templates/analista/atendimentos.html` | Atendimentos indicados ao analista (item 30). |
| `templates/includes/paginacao.html` | Paginação que preserva filtros (item 56). |
| `env.example`, `.gitignore`, `.dockerignore`, `backup_banco.sh` | Credenciais fora do código e da imagem (item 61); backup. |
| `docs/RELATORIO_ALTERACOES.md` | Este relatório. |

## 3. Arquivos alterados

| Arquivo | O que mudou |
|---|---|
| `processos_app/models.py` | 5 models novos; 4 FKs em Processo; `recorrente` SIM/NAO; `grupo` derivado da espécie; `esta_ativo` considera saída legada; índices. |
| `processos_app/views.py` | Views só tratam HTTP e chamam os services. Cadastro, edição, listas, finalizados, exportação, saída, cancelamento, filas e tela do analista reescritos. Paginação. POST obrigatório nas ações. |
| `processos_app/views_tramitacao.py` | Seletor de direcionamento mostra a disponibilidade do dia. |
| `processos_app/services/permissions.py` | Novas capacidades (cadastros, consulta, cancelamento), tela inicial por papel. |
| `processos_app/services/tramitacao.py` | Correções (seção 7), prioridade pelo cadastro, `ativos()`/`finalizados()`, via de saída do acervo legado. |
| `processos_app/services/prazos.py` | Prazo lido do cadastro de Prioridades; regra da decisão pendente isolada (item 66). |
| `processos_app/urls.py` | Rotas dos Blocos B, C e D. |
| `processos_app/forms.py` | `ProcessoForm` com lista explícita de campos. |
| `protocolo_project/settings.py` | Segurança de produção (item 62) — ver seção 9. |
| `protocolo_project/settings_preview.py` | Liga DEBUG antes de importar o settings. |
| `Dockerfile` | Removidos GDAL/PROJ/binutils (não usados). |
| `docker-compose.yml` | Postgres só em 127.0.0.1; variáveis de hosts/HTTPS. |
| `static/css/app.css` | Estilos das telas novas (chips, cards clicáveis, paginação, destaques de fila). |
| `templates/*` (11 arquivos) | Menu por papel, formulário de entrada, listas, finalizados, fila do analista, tela do processo, histórico, gestão de usuários. |

Não foram removidos arquivos. Não foram alteradas migrations antigas (0001–0015).

---

## 4. Models e migrations

**Novos models** (migration 0016):
- `UnidadeAdministrativa` (nome único, sigla, ativo, ordem) — secretarias e destinos.
- `EspecieProcesso` (nome, grupo, exige contratada, exige valor, gera relatório,
  tipo de monitoramento, encerra monitoramento anterior; único por nome+grupo).
- `Prioridade` (código único, nome, prazo em dias, ordem).
- `TipoIndisponibilidade` e `Indisponibilidade` (dia único, período, recorrente, recorrente com vigência).

**Processo** ganhou `secretaria_fk`, `destino_fk`, `especie_fk`, `prioridade_fk`
(PROTECT: cadastro em uso não é apagado, só inativado). Os campos texto antigos
continuam sendo gravados em paralelo (item 60, remoção posterior).

**Carga inicial da 0016:** prioridades (Urgente 1 dia, Prioritário 2, Normal 7),
5 tipos de indisponibilidade, 23 secretarias, espécies das listas antigas do
formulário com a mesma regra de monitoramento que estava no código. Depois
converte o histórico: cada secretaria já gravada em texto que não esteja na
lista vira uma unidade (ativa, no fim da lista); espécies fora da lista oficial
viram cadastros **inativos**; tudo é vinculado por nome, sem diferenciar
maiúsculas; destinos em texto **não** criam unidades. Processos do grupo
"Outros" ficam sem espécie vinculada (aparecem no `sanear_dados`).

**0017:** `recorrente` passa a SIM/NAO (antes coexistiam 'NÃO' e 'NAO'); índices
em `data_saida`, `saida_concluida_em`, `liberado_assinatura_em`,
`cancelado_em` e pendência (`status`, `responsavel_tecnico`).

---

## 5. Endpoints

Todas as ações de escrita exigem **POST** e conferem papel + estado atual no service.

| Rota | Nome | Quem |
|---|---|---|
| `gestao/dashboard/` | `gestao_dashboard` | Gestão (tela inicial) |
| `gestao/cadastros/<slug>/` (+ `salvar/`, `<id>/alternar/`) | `gestao_cadastros*` | Gestão |
| `gestao/pessoas/` (+ `registrar/`, `<id>/desativar/`) | `gestao_pessoas*` | Gestão |
| `gestao/diligencias/` | `gestao_diligencias` | Gestão |
| `diligencias/<id>/indicar-atendimento/` | `pend_indicar_atendimento` | Gestão |
| `analista/atendimentos/` | `meus_atendimentos` | Analista |
| `pendencias/<id>/resolver/` · `insuficiente/` · `cancelar/` | `pend_*` | Responsável técnico (cancelar: também Gestão) |
| `deletar/<id>` | `deletar_processo` | Gestão — **agora cancela** com motivo; não apaga |
| `manage_users/delete/<id>/` | `delete_user` | Admin — **agora desativa/reativa**; não apaga |
| `processo/<id>/marcar_saida/` | `marcar_saida_processo` | Protocolo — só "Disponível para retirada" ou acervo legado |
| `processo/<id>/concluir_monitoramento/` | `concluir_monitoramento` | Analista do grupo / Gestão — não dá saída |

Slugs de cadastro: `unidades`, `especies`, `prioridades`, `tipos-indisponibilidade`.

---

## 6. Regras implantadas (por item do documento)

- **1–5 Papéis:** Gestão só visualiza e gerencia (prioridade, cancelamento, cadastros, pessoas, diligências); não assume nem edita análise nem dado de protocolo. Tela inicial por papel; Gestão abre no Dashboard.
- **6–16 Tramitação:** máquina de estados com trava de linha; análise completa obrigatória para direcionar e liberar; direcionamento para analista de qualquer grupo; assinatura substitutiva preserva o analista da análise; retorno e saída em lote "tudo ou nada"; alteração de destino com autorização e evento.
- **17–18 Entrada:** o formulário do Protocolo registra só dados de protocolo; o processo nasce Normal e sem técnico; criação passa por uma única função.
- **19–22 Cadastros:** secretaria, espécie e prioridade vêm do cadastro; o grupo é derivado da espécie; itens em uso não mudam de grupo/código e não são apagados.
- **23–24, 48 Gestão de Pessoas CGM:** registro de férias, cursos etc.; o seletor de direcionamento mostra "Férias até 30/09", mas **não bloqueia** (item 9).
- **25–34 Pendências:** criada pelo analista responsável, indicada pela Gestão, resolvida ou devolvida pelo técnico; nunca apagada (cancelada com motivo); pendências de passagens anteriores aparecem na tela do processo; `tem_pendencia` passou a ser calculado.
- **35–36:** processo cancelado e usuário desativado, nunca excluídos.
- **37–40 Filas:** filtros com contagem, destaque próprio para "Direcionado a você", coluna Contratada / Favorecido / Interessado nos dois grupos.
- **41–44 Monitoramento:** meses de calendário (31/01 + 3 meses = 30/04); regra única pela espécie; telas não gravam em GET; concluir monitoramento não dá saída; editar a data de entrada não reabre ciclo concluído.
- **45–46 Histórico:** eventos do processo e da pendência exibidos no histórico, com tempos do fluxo.
- **47–50 Dashboard:** 10 cards clicáveis, quadro da equipe, indicadores do período (recebidos, liberados, saídas, estoque, retornos, por grupo/secretaria/espécie), tempos médios.
- **51–53:** whitelist por papel; endpoints específicos; CSRF mantido e erros sem detalhe interno.
- **54–58:** recorrência normalizada; numeração de relatório concorrente preservada; paginação de 50; índices; ativo = não saiu e não foi cancelado.
- **61–63:** `.env` e bancos fora do versionamento e da imagem; produção segura por padrão; Django 5.2 LTS e python-dateutil mantidos.

---

## 7. Defeitos encontrados e corrigidos

1. **Liquidações nunca seriam liberadas para assinatura**: exigia "Número do despacho", campo que a tela de Liquidações não mostra. Agora exige o Número do relatório.
2. Direcionar com o seletor vazio causava **erro 500**.
3. "Concluir monitoramento" **gravava data de saída** e aceitava GET.
4. A lista de finalizados **gravava no banco ao ser aberta** (GET).
5. Cancelar exigia superusuário na tela e Gestão no service: **ninguém conseguia**.
6. O botão de saída **pulava toda a tramitação** (saía de qualquer estado).
7. O link "Ver" da Gestão levava ao login.
8. Excluir usuário **apagava** o usuário e sua autoria.
9. Editar qualquer campo de processo com monitoramento concluído **reabria o ciclo**.
10. Opção MENSAL existia no cálculo mas não nas escolhas do campo — removida.
11. `settings.py` tinha `INSTALLED_APPS += ['django.contrib.staticfiles.finders']` (entrada inválida) — removida.

---

## 8. Testes

78 testes em `processos_app/tests/`: permissões por papel, criação e whitelist,
máquina de estados, concorrência (sequencial), direcionamento, redirecionamento,
assinatura substitutiva, saída em lote e legado, destino, prioridade,
cancelamento, pendências/diligências, Gestão de Pessoas, monitoramento,
prazos, telas por papel (smoke), GET não grava, POST obrigatório, exportação
Excel e comandos de saneamento.

**Verificação feita aqui (estática):** compilação de todos os .py; pyright sem
erros relevantes (47 arquivos); 26 templates conferidos (tags, includes e as
58 rotas nomeadas usadas); estado final das 17 migrations idêntico aos models
(ou seja, `makemigrations` não deve gerar nada).

**Não executado aqui:** `manage.py check`, `migrate`, `test`. É o passo 1 do roteiro.

---

## 9. Pontos de atenção para o TI (verificar)

**Antes de subir**
1. **Rodar os testes.** Se algum falhar, a mensagem indica o ponto; os testes foram escritos sem poder ser executados, então uma falha pode estar no próprio teste.
2. **`DJANGO_SECRET_KEY` é obrigatória** fora do modo DEBUG. Sem ela o sistema não sobe (proposital). `DEBUG` agora é **False por padrão**.
3. **`DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS`**: se o endereço de acesso (IP interno, porta) não estiver na lista, o Django responde 400 ou recusa o login por CSRF. Ajustar no `.env`.
4. **`DJANGO_HTTPS=True`** somente se houver HTTPS no proxy. Ligado sem HTTPS, o login deixa de funcionar (cookies seguros).
5. **Postgres agora escuta só em 127.0.0.1.** Se alguma ferramenta externa (pgAdmin em outra máquina, backup remoto) acessava a porta 5432, vai parar. Ajustar em `docker-compose.yml`.
6. **Dockerfile sem GDAL/PROJ.** O projeto não usa GeoDjango; se algum pacote externo precisar, recolocar.
7. Se o projeto do servidor tiver um arquivo `processos_app/tests.py`, **apagá-lo** (conflita com a pasta `tests/`). Se tiver `admin.py` próprio, comparar com o novo.

**Dados e usuários**
8. **Superusuário não tem mais atalho de permissão**: vale o papel. O usuário `admin` criado pelo compose nasce com papel Gestão. Quem opera precisa ter o papel correto em Gerenciar usuários.
9. Usuários antigos com nível '3' ("Usuário geral") viraram **Gestão** (0015). Quem de fato analisa precisa ser reclassificado como Analista.
10. **Rodar `sanear_dados`** e ler o relatório antes do `--aplicar`. Ele corrige só o que é deduzível (saídas gravadas só em `data_saida`; `tem_pendencia` NÃO→SIM quando há pendência aberta) e **lista** o resto: números de relatório repetidos, valores de recorrente desconhecidos, processos sem espécie/secretaria vinculada, destinos sem unidade.
11. **Destinos em texto não viraram unidades** automaticamente (evita criar lixo). Cadastrar em Gestão > Cadastros o que faltar.
12. **Secretarias do histórico** que não estavam na lista oficial entraram como unidades ativas. Se houver grafias diferentes da mesma secretaria ("Sec. Saúde" e "Saúde"), a Gestão inativa a duplicada em Cadastros.
13. **Espécies digitadas em "Outros" no passado** foram importadas **inativas**. A Gestão decide quais reativar.
14. **Acervo antigo**: como antes só o Protocolo usava o sistema, os processos que já estavam na casa não têm análise registrada. Para eles o botão de saída continua funcionando (via de transição, registrada como "legado" no histórico). Processo novo não usa essa via. **Remover a função `registrar_saida_legado` quando o acervo zerar** (o item 6 do `sanear_dados` mostra quantos faltam).
15. Analistas **não editam mais processos finalizados** pela lista (whitelist). Correções passam pelo Protocolo.
16. O campo `tem_pendencia` foi mantido no banco (item 60), mas não é mais usado pelas telas. Remover numa etapa futura.

**Decisões de projeto que diferem do texto do documento**
17. Nomes internos dos estados foram mantidos como estavam no sistema (decisão do usuário): `AGUARDANDO_ASSINATURA` aparece como "Liberado para assinatura".
18. **Item 66 (prazos) continua pendente**: dias corridos ou úteis, e contagem a partir da entrada ou da mudança de prioridade. A regra está isolada em `services/prazos.py` (`somar_prazo` e `data_base_do_prazo`) — hoje corridos, desde a entrada.
19. Nenhuma trava de unicidade no número do relatório (item 55): o `sanear_dados` lista os repetidos para decisão.
20. O teste de concorrência roda em sequência. Duas requisições realmente simultâneas só se testam em PostgreSQL (o SQLite não tem `select_for_update`).
21. O cookie CSRF **precisa continuar legível pelo JavaScript** (as telas usam `getCookie('csrftoken')`); não ativar `CSRF_COOKIE_HTTPONLY`.
22. Reverter a 0017 não restaura a grafia 'NÃO' com acento (não há como distinguir); o código novo e o antigo funcionam com 'NAO'.

---

## 10. Decisões ainda pendentes (administração)

- Política de prazos (item 66).
- Unicidade do número de relatório (item 55).
- Quando remover os campos texto legados e `tem_pendencia` (item 60).
- Quando encerrar a via de saída do acervo legado.
