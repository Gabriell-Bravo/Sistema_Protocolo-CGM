# Guia de uso — Sistema de Protocolo CGM

Este guia é para o **dia a dia**. Cada pessoa vê menus diferentes, conforme o papel da conta. Leia só a parte que vale para você.

As palavras em **negrito** são os nomes dos botões e dos menus, do jeito que aparecem na tela.

| Se o seu papel é… | Você… | Depois do login abre… |
|---|---|---|
| **Protocolo** | Registra a entrada e a saída | Processos Protocolo |
| **Analista – Licitações e Contratos** | Analisa processos desse grupo | Fila de análise |
| **Analista – Liquidações** | Analisa liquidações e controla os números de relatório | Fila de análise |
| **Gestão** | Acompanha, prioriza e conclui diligências. Pode somar funções de Protocolo, Licitações e/ou Liquidações no menu **Funções** | Dashboard |
| **LAI – Acesso à Informação** | Acompanha os pedidos da Lei de Acesso à Informação (Fala.BR). Só vê a aba **LAI** | LAI |

Não tem conta, esqueceu a senha ou o menu não bate com o seu trabalho? Fale com quem passou o acesso.

**Dica:** em quase todas as listas, o **número do processo é um link**. Clique nele para abrir a ficha.

---

## Sumário

1. [Como entrar, sair e se virar na tela](#1-como-entrar-sair-e-se-virar-na-tela)
2. [Como o processo anda no sistema](#2-como-o-processo-anda-no-sistema)
3. [Protocolo](#3-protocolo)
4. [Analista de Licitações e Contratos](#4-analista-de-licitações-e-contratos)
5. [Analista de Liquidações](#5-analista-de-liquidações)
6. [O que os dois analistas fazem igual](#6-o-que-os-dois-analistas-fazem-igual)
7. [Gestão](#7-gestão)
8. [Histórico do processo](#8-histórico-do-processo)
9. [Dúvidas frequentes](#9-dúvidas-frequentes)

---

## 1. Como entrar, sair e se virar na tela

### Entrar

1. Abra o sistema no navegador.
2. Digite o **usuário** e a **senha**.
3. Clique em **Entrar**.

### Sair

No menu da esquerda, em **Conta**, clique em **Sair**.

### Alterar a própria senha

1. Menu **Alterar Senha**.
2. Informe a senha atual e a nova senha (duas vezes).
3. Clique em **Alterar senha**.

Se esqueceu a senha atual, peça a quem passou o acesso para redefinir. O sistema **não** envia senha por e-mail.

### Menu e aparência

- O menu fica à esquerda. O botão de **menu** (três linhas) recolhe ou expande.
- O ícone de lua/sol no topo troca entre **modo claro** e **modo escuro**. A preferência fica salva no seu navegador.
- No rodapé do menu aparecem o seu nome e o seu papel.
- Cada papel vê só os menus que lhe dizem respeito. Isso é normal.
- Em **Ajuda**, o item **Guia de uso** abre este material.

---

## 2. Como o processo anda no sistema

O sistema acompanha a passagem física do processo pela CGM.

```
Protocolo registra a entrada
    → Fica pendente (disponível para análise)
    → Um analista assume e analisa
    → Analista encaminha para o Controlador
    → Controlador assina no papel (não no sistema)
    → Protocolo registra a saída
    → Processo vai para Finalizados
```

A assinatura do Controlador **não** é feita no sistema: é no papel. O sistema só registra que o processo está pronto para assinar.

**Na prática de hoje:** o Protocolo **não precisa esperar** a análise para dar saída. Em **Processos Protocolo**, o botão de saída (ícone de seta para fora) registra a saída na hora.

### Situações que você vai ver na tela

| Situação | O que significa |
|---|---|
| Disponível para análise | Entrou e ainda ninguém assumiu |
| Em análise por [nome] | Um analista está com ele |
| Direcionado para [nome] | Foi encaminhado para outro analista |
| Com o Controlador | Pronto para o Controlador assinar (no papel) |
| Saída concluída | Já saiu da CGM |

**Cancelar** não apaga o processo. O registro fica, com o motivo. Só a Gestão (e o administrador) cancelam.

---

## 3. Protocolo

O Protocolo registra a **entrada**, acompanha o que está na casa e registra a **saída**.

**Menu:** Novo Processo · Processos Protocolo · Processos Contabilidade · Guia de uso · Alterar Senha · Sair

### 3.1 Cadastrar um processo novo

1. Clique em **Novo Processo**.
2. Preencha:

   - **Número do processo** (obrigatório). Se o número já passou pela CGM, o sistema preenche os dados da última passagem. Confira antes de salvar.
   - **Volume** — fica em branco de propósito: cada entrada pode ter volume diferente. Data e hora de saída também não são copiadas.
   - **Secretaria**
   - **Data** e **hora de entrada** (já vêm com o momento atual; só mude se o registro for depois da chegada física)
   - **Espécie** — ao escolher, o sistema mostra o **grupo** (Licitações e Contratos ou Liquidações)
   - **Objeto**
   - **Contratada / Favorecido / Interessado**, se a espécie exigir
   - **É recorrente?** (padrão: Não)

3. Clique em **Salvar Processo**.

Se a espécie ainda não existir no cadastro, use **Outros (espécie não cadastrada)**, digite o nome e escolha o grupo. Depois peça à Gestão para cadastrar essa espécie, se ela for recorrente.

**O que o Protocolo não preenche na entrada:** analista, despacho, destino de saída. Isso acontece depois, no momento certo.

### 3.2 Processos Protocolo

Esta é a tela principal. Junta **Ativos** (ainda na CGM) e **Finalizados** (já saíram).

**Abas no topo**

- **Ativos** — processos ainda na casa.
- **Finalizados** — processos com saída registrada.
- A **busca** procura nas duas abas ao mesmo tempo. Os resultados vêm com os ativos primeiro. Se o mesmo número já passou várias vezes, aparece **só a última** (a que ainda está na CGM ou a que saiu por último). Volumes e passagens anteriores ficam no **Histórico**.

**Filtros comuns**

- **Pendentes** — o que ainda precisa de análise (é o mesmo conjunto que a fila dos analistas vê).
- **Com análise** — já analisados, ainda na CGM.
- **Todos** — a lista completa. Use esta aba para **registrar a saída** no dia a dia.

Você pode:

- Buscar por número, secretaria, objeto, contratada etc.
- Filtrar por prioridade, situação, grupo e espécie.
- **Editar** dados de protocolo (lápis): número, volume, secretaria, entrada, espécie, objeto, contratada, recorrente.
- **Registrar saída** (ícone de seta para fora): o processo sai da CGM na hora.
- Abrir o **Histórico** (quantas vezes o processo já passou pela CGM).
- Clicar no **número do processo** para abrir a ficha.

Você **não** cancela processo, **não** assume análise e **não** muda prioridade.

### 3.3 Registrar a saída

1. Abra **Processos Protocolo**.
2. Use a aba **Todos** (ou **Ativos**) e localize o processo.
3. Clique no botão de saída (ícone de seta para fora).
4. Confirme.

Pronto. O processo passa para **Finalizados**.

Se precisar da planilha das saídas: na aba **Finalizados**, clique em **Exportar saídas** e informe o período.

### 3.4 Gerar planilha dos ativos

No topo de **Processos Protocolo**, o botão **Gerar planilha** baixa um Excel dos processos ainda em tramitação, com os filtros que você estiver usando.

### 3.5 Processos Contabilidade

Menu próprio, só para Protocolo, Gestão e administrador.

Aqui entram:

- processos da secretaria **Controladoria Geral do Município**;
- processos da espécie **Contabilidade**.

Eles **não** entram na fila dos analistas. Use esta tela para acompanhar e, se for o caso, registrar a saída.

### 3.6 Finalizados

Na aba **Finalizados** de **Processos Protocolo**:

- filtrar e buscar;
- ver o histórico;
- **Exportar saídas** (informe o período de saída).

### Rotina do dia — Protocolo

1. Chegou processo → **Novo Processo** → **Salvar Processo**.
2. Acompanhar em **Processos Protocolo**.
3. O processo saiu → aba **Todos** → botão de saída.
4. Se precisar de planilha dos que ainda estão na casa → **Gerar planilha**.
5. Se precisar de planilha das saídas → aba **Finalizados** → **Exportar saídas**.

---

## 4. Analista de Licitações e Contratos

Você só vê processos do seu grupo.

**Menu:** Fila de análise · Atendimentos indicados · Finalizados · Para assinar · Diligências · Controle de análise · Guia de uso · Alterar Senha · Sair

Você **não** cadastra processo, **não** registra saída e **não** muda prioridade.

### 4.1 Fila de análise

Os cards no topo mostram quantos estão **disponíveis**, **com você**, **com o Controlador**, com prazo vencido e com atendimento indicado.

A lista **Para trabalhar** traz o que você ainda pode agir: disponíveis, os que estão com você e os direcionados a você.

Clique no **número do processo** para abrir a ficha.

Na linha:

| Botão | Quando usar |
|---|---|
| **Assumir processo** | Está disponível e você vai analisar |
| **Analisar** | Já está com você |
| **Encaminhar ao Controlador** | A análise está pronta |
| **Ver** | Só consultar |

Se você assumiu por engano, **Devolver à fila** solta o processo de novo (a análise em andamento é limpa).

### 4.2 Controle de análise

Tela do grupo de Licitações. Mostra os ativos: **Disponíveis**, **Em análise** e **Para assinar**.

**Nova análise** abre a lista **Assumir**: processos pendentes ainda disponíveis, ordenados por prioridade. Ao assumir, a ficha de análise abre na hora.

O registro principal da análise de Licitações é o **arquivo anexado**. Observação e diligências são opcionais.

### 4.3 Anexar arquivos

Na ficha do processo (Licitações) existe o bloco **Arquivos anexados**.

1. Arraste o arquivo para a área pontilhada **ou** clique para escolher.
2. Aceita PDF, Word, Excel, imagem ou texto — até 15 MB cada.
3. Clique em **Anexar**.

Depois de anexado:

- o arquivo aparece na ficha **e no histórico**;
- você pode ver o preview;
- se for **Word (.docx)**, dá para baixar o original **e** uma cópia em **PDF** (o preview também mostra o PDF).

Anexar **não** substitui o encaminhamento ao Controlador. Análise, diligências e encaminhamento continuam disponíveis. Em **Liquidações** o mesmo bloco existe (Relatório anexado), mas o arquivo é **opcional** para encaminhar.

### Rotina do dia — Licitações

1. Abra a **Fila de análise** ou o **Controle de análise**.
2. **Assuma** um processo (ou use **Nova análise**).
3. Anexe o arquivo da análise.
4. Se faltar documento, registre a diligência.
5. **Encaminhar** → **Para o Controlador**.
6. Olhe **Atendimentos indicados** no começo do dia.

---

## 5. Analista de Liquidações

Você só vê processos do seu grupo.

**Menu:** Fila de análise · Atendimentos indicados · Finalizados · Para assinar · Diligências · Controle de relatório · Guia de uso · Alterar Senha · Sair

Você **não** cadastra processo, **não** registra saída e **não** muda prioridade.

### 5.1 Fila de análise

Funciona como a fila de Licitações. Os cards e os botões **Assumir**, **Analisar** e **Encaminhar** são os mesmos.

A fila mostra também processos que você já analisou e ainda estão na casa (por exemplo, depois de emitir o relatório e encaminhar).

### 5.2 Controle de relatório

Esta é a **planilha** das análises de Liquidações. Cada linha é uma análise com número de relatório.

**Abas da planilha** (grupos de numeração, conforme o cadastro).

No topo você pode ter:

- **Análises** — a planilha em si.
- **Números destinados** — números separados para usar depois.
- **Numeração** — ponto de partida da sequência (quem tem permissão).

O que dá para fazer na planilha:

- Buscar em qualquer campo (processo, relatório, espécie, valor, destino…).
- Clicar no **número do processo** para abrir a ficha.
- **Editar** a linha (lápis).
- **Nova análise** — começa uma análise pelo número do processo, mesmo que o Protocolo ainda não tenha cadastrado.
- **Importar Excel** — atualiza o grupo com a planilha. Peça confirmação antes: a importação substitui as linhas ativas daquele grupo.
- Marcar **sem relatório** quando o processo saiu sem peça.
- Vincular ou desvincular o processo da linha.
- Desfazer ou cancelar linha, conforme a permissão e a cor da linha.

**Cores (resumo):**

- **Amarelo** — saiu sem relatório (número pode ficar reservado).
- Linha **reservada** — número liberado ao voltar à fila; no mesmo dia o sistema reaproveita ao gerar número.

### 5.3 Nova análise (Liquidações)

1. No **Controle de relatório**, clique em **Nova análise**.
2. Informe o **nº do processo** e o **grupo de numeração**.
3. Clique em **Continuar**.
4. Preencha a análise (objeto, valor, destino, diligências, se houver).
5. Use **Gerar número e salvar** — isso emite o sequencial e grava na planilha.
6. Depois, **Encaminhar** para o Controlador.

Não precisa gerar o número e fechar a tela de uma vez: você gera, confere e só então encaminha.

### 5.4 Processo de origem / pagamento

Na liquidação existem dois números:

- o **número do processo** que está na CGM;
- o **processo de origem / pagamento**, quando for outro número.

As diligências usam os dois para localizar o processo certo (a planilha de pendências às vezes traz um, às vezes o outro).

### 5.5 Bolsa Atleta

Em espécies de Bolsa Atleta / auxílio:

- na **concessão**, o nº do processo já vem preenchido;
- na **prestação de contas**, o campo de prestação começa vazio para você informar.

### 5.6 Gerar número e encaminhar

Na ficha da análise:

1. Preencha os campos.
2. Se houver relatório em arquivo, anexe no bloco **Relatório anexado** (não é obrigatório).
3. Clique em **Gerar número e salvar** (grava na planilha).
4. Clique em **Encaminhar** e escolha o destino.

Marque **Sem relatório** se não houve peça. Mesmo assim o sistema pede número e data antes de encaminhar ao Controlador. O arquivo anexado **não** é exigido para enviar ao Controlador.

Se o número já tiver sido usado e estiver reservado (processo que saiu sem relatório), o sistema pergunta se você quer **reutilizar**.

### 5.7 Anexar o relatório (opcional)

Na ficha da liquidação (e em **Nova análise**) existe o bloco **Relatório anexado**, no mesmo formato de Licitações: arraste o arquivo, veja o preview e baixe depois no histórico.

O anexo **não é obrigatório**. Dá para encaminhar ao Controlador sem arquivo.

### Rotina do dia — Liquidações

1. Abra a **Fila de análise** ou o **Controle de relatório**.
2. **Nova análise** ou **Assumir** um pendente.
3. Preencha a análise → **Gerar número e salvar**. Anexe o relatório se houver (opcional).
4. Se faltar documento, registre a diligência.
5. **Encaminhar** → **Para o Controlador**.
6. Olhe **Atendimentos indicados** no começo do dia.

---

## 6. O que os dois analistas fazem igual

### 6.1 Analisar e salvar

1. Abra o processo (**Assumir** ou **Analisar**).
2. Preencha o que a tela pedir (status, destino, valor, observação…).
3. Clique em **Salvar análise** sempre que quiser gravar o andamento.

**Salvar não é o mesmo que encaminhar.**

Para encaminhar, em geral o sistema pede: status da análise (não use “Não Aplicável”), número (despacho ou relatório) e destino. Algumas espécies também exigem valor.

### 6.2 Encaminhar

Clique em **Encaminhar**. Abre três opções:

- **Para o Controlador** — a análise está pronta e o processo segue para assinatura.
- **Para outro analista** — escolha o colega. Quem analisou continua sendo você; o colega encaminha ao Controlador.
- **Para a fila (sem análise)** — o processo volta a ficar disponível. Os dados da tentativa são limpos. Não use isso só para passar um processo pela metade.

As duas primeiras só ligam com a análise preenchida.

### 6.3 Diligências na ficha do processo

Se faltar documento ou informação:

1. Escreva o texto em **Nova pendência** (pode ser um texto com vários itens; o sistema vira **checklist**).
2. Clique em **Adicionar**.

Depois você pode:

- **Imprimir checklist** — abre a folha no padrão visual da CGM para imprimir ou salvar PDF.
- Acompanhar o progresso (**itens feitos / total**).

A Gestão trata a diligência (telefone, ofício, e-mail — isso não é registrado aqui) e **conclui** no sistema. Em alguns fluxos a Gestão indica o atendimento e você confirma em **Atendimentos indicados**.

Se a pendência foi cadastrada por engano, cancele e informe o motivo. O registro não é apagado.

Pendências de passagens anteriores da CGM aparecem só para leitura.

### 6.4 Atendimentos indicados

Menu próprio com o que a Gestão já sinalizou como atendido.

Você pode:

- **Abrir processo** (ou clicar no número);
- **Confirmar resolução**;
- marcar **Atendimento insuficiente** (explique o que ainda falta);
- **Imprimir checklist**.

### 6.5 Finalizados e Para assinar

- **Finalizados** — processos que já saíram. Consulta e histórico.
- **Para assinar** — o que já foi encaminhado ao Controlador. Serve para saber o que recolher. A assinatura em si é no papel.

### 6.6 Consultar diligências

O menu **Diligências** do analista é de **consulta** (Licitações e Liquidações). Quem conclui é a Gestão ou o administrador. Clique no texto da diligência para ver o checklist.

---

## 7. Gestão

A Gestão **acompanha e organiza**. Sem funções extras, não assume processo, não preenche análise e não libera assinatura.

Na tela do processo aparece um aviso de consulta: você **vê**, mas não pratica ato de analista — até marcar essas funções.

**Menu:** Processos Protocolo · Processos Contabilidade · Dashboard · Processos · Diligências · Pessoas CGM · Cadastros · **Funções** · Guia de uso · Alterar Senha · Sair

### 7.0 Escolher funções (Gestão e administrador)

No menu **Funções**, marque o que a conta precisa operar, sem perder o papel de Gestão (ou de administrador):

- **Protocolo** — Novo Processo, correção cadastral e registro de saída.
- **Licitações e Contratos** — Fila de análise, anexos e Controle de análise.
- **Liquidações** — Fila de análise e Controle de relatório.

Dá para combinar. Exemplo: Protocolo + Liquidações. O menu passa a mostrar as duas áreas. O administrador também define isso na tela **Usuários**.

### 7.1 Dashboard

Visão geral da casa: quantos estão em tramitação, disponíveis, em análise, para assinar, vencidos, urgentes, com diligência etc.

Os cards são clicáveis e levam à lista correspondente.

Dá para filtrar por período, grupo, analista, secretaria e espécie. Há o quadro da **equipe de análise** (ordem alfabética, sem ranking) e tempos médios.

### 7.2 Processos

Fila completa dos dois grupos. Use para ver o estoque e **alterar a prioridade** no seletor da linha (grava na hora).

**Prioridade N/Recorrente** vale só nesta entrada. A próxima vez que o mesmo número entrar, ela **não** acompanha (diferente da urgência marcada como recorrente).

O card **Com o Controlador** mostra o que já foi encaminhado para assinatura — é a lista para recolher e levar ao Controlador.

Clique no **número do processo** para abrir a ficha (somente consulta).

Se um analista assumiu por engano e o processo ficou preso, use **Devolver à fila**. O processo volta a ficar disponível (a análise em andamento é limpa).

### 7.3 Diligências

Cada **linha** é uma diligência de um processo. Um processo pode ter várias.

**Abas de situação** (abertas, concluídas etc.) e filtro por grupo (Licitações / Liquidações).

O que dá para fazer:

- Buscar por processo, secretaria, texto, analista, objeto, contratada.
- Clicar no **número** para abrir o processo.
- Clicar no texto para ver o **checklist**.
- Ver o progresso (**itens feitos / total** daquela diligência).
- **Imprimir checklist** (folha no padrão da CGM).
- **Concluir diligência** — marca só os itens **desta** linha. Não conclui as outras diligências do mesmo processo.
- **Importar Excel** da planilha **CONTROLE DE PENDÊNCIAS**:
  - não cria processo novo;
  - ignora linha sem processo já cadastrado;
  - ignora diligência que já existe (mesmo texto);
  - localiza o processo pelo número **ou** pelo processo de origem/pagamento.

O processo só vai para o conjunto de **concluídos** quando **todas** as diligências dele estiverem concluídas.

O administrador também pode **desfazer a indicação de atendimento**, se ela tiver sido feita cedo demais.

### 7.4 Processos Protocolo e Processos Contabilidade

As mesmas listas do Protocolo, com diferenças:

- Gestão **não** edita dados de protocolo.
- Gestão **pode cancelar** o processo (ícone). Informe o **motivo**. O registro permanece.
- Em Finalizados, Gestão pode **Exportar saídas**.

### 7.5 Pessoas CGM

Registre férias, cursos e outras indisponibilidades da equipe.

1. Escolha o servidor, o tipo, o período (ou o dia da semana, se for recorrente) e, se quiser, uma observação.
2. Clique em **Registrar**.

**Desativar** um registro não apaga o histórico.

Essa informação aparece para o analista na hora de encaminhar a outro colega, mas **não bloqueia** o trabalho de ninguém.

### 7.6 Cadastros

Parametrize o sistema, sem excluir. Dá para **inativar** e **reativar**.

Abas:

- **Unidades Administrativas** — secretarias da lista de entrada
- **Espécies de Processo** — nome, grupo, se gera número de relatório, se exige contratada/valor etc.
- **Prioridades** — prazos
- **Tipos de Indisponibilidade** — férias, curso etc.

Para incluir: preencha **Novo registro** e clique em **Adicionar**. Para ajustar um existente: altere e **Salvar**.

Alguns campos ficam travados depois de criados (por exemplo, o grupo da espécie e o código da prioridade), para não bagunçar processos antigos.

### Rotina do dia — Gestão

1. Olhe o **Dashboard**.
2. Ajuste prioridades em **Processos**, se preciso.
3. Use o card **Com o Controlador** para recolher o que vai à assinatura.
4. Em **Diligências**, conclua o que já foi atendido (item a item) ou importe a planilha de pendências.
5. Mantenha **Cadastros** e **Pessoas CGM** em dia.

---

## 8. Histórico do processo

O botão de **histórico** (ícone de relógio) mostra, em blocos:

1. **Informações do processo** — número, volume, secretaria, espécie, entrada, saída, destino.
2. **Análise** — relatório, valor, período, processo de origem, observação. Em Licitações e Liquidações, os **arquivos anexados** (com preview e PDF do Word). Em Liquidações o anexo é opcional.
3. **Eventos da tramitação** — quem assumiu, encaminhou, deu saída etc.
4. **Diligências** — texto em checklist e o que já foi concluído.
5. **Passagens pela CGM** — cada vez que aquele número entrou na casa.

Passe o mouse (ou toque) nos cartões de informação para ler o que cada campo significa.

---

## 9. Dúvidas frequentes

**Por que não vejo o menu Novo Processo / Fila / Dashboard?**  
O menu segue o papel da sua conta. Gestão e administrador somam funções no menu **Funções**. Se ainda estiver errado, fale com quem passou o acesso.

**Posso apagar um processo?**  
Não no dia a dia. A Gestão pode **cancelar**, mas o registro continua no histórico.

**O analista de Licitações vê processo de Liquidação?**  
Não. Cada analista só vê o próprio grupo. A Gestão vê os dois.

**Cadastrei a diligência. E agora?**  
A Gestão trata fora do sistema e clica em **Concluir diligência** (marcando os itens atendidos). Se houver indicação de atendimento, o analista confirma em **Atendimentos indicados**.

**Concluir diligência finaliza o processo inteiro?**  
Não. Conclui **só aquela linha**. O processo fica concluído no módulo de diligências quando **todas** as diligências dele estiverem prontas.

**O processo precisa ser analisado para eu dar saída?**  
Não. Em **Processos Protocolo**, o Protocolo registra a saída na hora.

**Onde assino o despacho no sistema?**  
Em lugar nenhum. A assinatura do Controlador é no papel. No sistema, o analista **encaminha para o Controlador**.

**Para que serve o Controle de relatório?**  
É a planilha das análises de Liquidações: números, valores, destinos. Dá para importar Excel, gerar número e destinar números para depois.

**Para que serve o Controle de análise?**  
É a tela de Licitações para assumir, acompanhar e encaminhar, com destaque para o arquivo anexado.

**Como vejo um Word anexado?**  
Na ficha ou no histórico do processo de Licitações. O sistema mostra o preview em PDF e deixa baixar o Word original ou a cópia em PDF.

**A busca de Processos Protocolo não achou o processo na aba Ativos.**  
A busca olha **Ativos e Finalizados juntos**. Veja se ele já saiu (aba Finalizados) ou se está em **Processos Contabilidade**.

**Esqueci a senha.**  
Peça a quem passou o acesso para redefinir.

---

*Sistema de Protocolo e Gestão de Processos — Controladoria Geral do Município de Saquarema. Atualizado em outubro de 2026.*
