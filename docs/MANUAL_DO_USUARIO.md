# Manual do usuário — Sistema de Protocolo CGM

Este manual é para quem **usa o sistema no dia a dia**: Protocolo, Analista e Gestão.

Cada pessoa vê menus diferentes, conforme o papel da conta. Leia só a parte que vale para você.

| Se o seu papel é… | Você… | Depois do login abre… |
|---|---|---|
| **Protocolo** | Registra a entrada e a saída do processo | Processos Ativos |
| **Analista – Licitações e Contratos** | Analisa processos desse grupo | Fila de análise |
| **Analista – Liquidações** | Analisa processos de liquidação | Fila de análise |
| **Gestão** | Acompanha, prioriza e diligencia | Dashboard |

Não tem conta, esqueceu a senha ou o menu não bate com o seu trabalho? Fale com quem passou o acesso.

---

## Sumário

1. [Como entrar, sair e se virar na tela](#1-como-entrar-sair-e-se-virar-na-tela)
2. [Como o processo anda no sistema](#2-como-o-processo-anda-no-sistema)
3. [Protocolo](#3-protocolo)
4. [Analista (Licitações e Liquidações)](#4-analista-licitações-e-liquidações)
5. [Gestão](#5-gestão)
6. [Dúvidas frequentes](#6-dúvidas-frequentes)

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

### Menu e aparência

- O menu fica à esquerda. O botão de **menu** (ícone de três linhas) recolhe ou expande.
- O ícone de lua/sol no topo troca entre **modo claro** e **modo escuro**. A preferência fica salva no seu navegador.
- No rodapé do menu aparece o seu nome e o seu papel.
- Cada papel vê só os menus que lhe dizem respeito. Isso é normal.

---

## 2. Como o processo anda no sistema

O sistema acompanha a passagem física do processo pela CGM.

```
Entrada (Protocolo)
    → Fila (Disponível para análise)
    → Um analista assume (Em análise)
    → Analista encaminha para o Controlador
    → Gestão recolhe o processo para o Controlador assinar (no papel)
    → Protocolo disponibiliza para retirada
    → Protocolo registra a saída
    → Finalizado (e, em alguns casos, monitoramento depois)
```

Às vezes o analista **direciona a assinatura** para um colega. Nesse caso o processo fica **Direcionado para assinatura** até o colega **liberar**.

A assinatura do Controlador **não** é feita no sistema: é no papel. O sistema só registra que o processo está pronto para assinar e, depois, que já pode ser retirado.

### Situações que você vai ver na tela

| Situação | O que significa |
|---|---|
| Disponível para análise | Entrou e ainda ninguém assumiu |
| Em análise por [nome] | Um analista está com ele |
| Direcionado para [nome] | Foi encaminhado para outro analista assinar/liberar |
| Com o Controlador | Pronto para o Controlador assinar (no papel) |
| Disponível para retirada | Já pode ser retirado pelo órgão |
| Saída concluída | Já saiu da CGM |

**Cancelar** não apaga o processo. O registro fica, com o motivo. Só a Gestão cancela.

---

## 3. Protocolo

O Protocolo registra a **entrada**, acompanha o que está na casa e registra a **saída**.

Enquanto a análise e a assinatura ainda não estiverem organizadas no dia a dia, **não precisa esperar essas etapas**. Em **Processos Ativos**, o botão de saída (ícone de porta) registra a saída na hora.

**Menu:** Novo Processo · Processos Ativos · Retirada · Finalizados · Alterar Senha · Sair

### 3.1 Cadastrar um processo novo

1. Clique em **Novo Processo**.
2. Preencha:

   - **Número do processo** (obrigatório). Se o número já passou pela CGM, o sistema sugere os dados da última vez.
   - **Volume**
   - **Secretaria** (lista das unidades cadastradas)
   - **Data** e **hora de entrada** (já vêm com o momento atual; só mude se o registro for depois da chegada física)
   - **Espécie** — ao escolher, o sistema mostra o **grupo** (Licitações e Contratos ou Liquidações) e, se for o caso, o tipo de **monitoramento**
   - **Objeto**
   - **Contratada / Favorecido / Interessado**, se a espécie exigir
   - **É recorrente?** (padrão: Não)

3. Clique em **Salvar Processo**.

Se a espécie ainda não existir no cadastro, use **Outros (espécie não cadastrada)**, digite o nome e escolha o grupo. Depois peça à Gestão para cadastrar essa espécie, se ela for recorrente.

**O que o Protocolo não preenche na entrada:** prioridade, analista, despacho, destino de saída. Isso acontece depois, no momento certo.

### 3.2 Processos Ativos

Aqui estão os processos **ainda na CGM** (sem saída). Na coluna **Situação**, se estiver em análise, aparece o nome de quem assumiu.

Você pode:

- Buscar por número, secretaria, objeto, contratada etc.
- Filtrar por prioridade, situação, grupo e espécie.
- **Editar** dados de protocolo (lápis): número, volume, secretaria, entrada, espécie, objeto, contratada, recorrente.
- **Registrar saída** (ícone de porta): o processo sai da CGM na hora, mesmo que ainda não tenha passado por análise.
- Abrir o **Histórico** (quantas vezes o processo já passou pela CGM).

Você **não** cancela processo, **não** assume análise e **não** muda prioridade.

### 3.3 Retirada

Há duas formas de registrar a saída.

**Do dia a dia (sem esperar análise)** — em **Processos Ativos**, clique no botão de saída (ícone de porta) na linha do processo. Confirme. Pronto.

**Quando a tramitação completa estiver em uso**

**Passo 1 — Depois que o Controlador assinou (no papel)**

Na lista **Aguardando assinatura do Controlador**, clique em **Disponibilizar para retirada**.

**Passo 2 — Quando o órgão vier buscar**

1. Na lista **Processos disponíveis para retirada**, marque os processos.
2. Confira o **destino**. Se estiver errado, clique em **Alterar destino**, informe o novo destino e quem autorizou.
3. Clique em **Registrar saída**.

A saída em lote: ou registra todos os marcados, ou não registra nenhum.

### 3.4 Finalizados

Processos que já saíram. Dá para filtrar, ver o histórico e **Exportar Excel** (é obrigatório informar o período de saída).

Alguns processos pedem **monitoramento** depois da saída (pendente, atrasado, concluído ou não aplicável). Quem conclui o monitoramento é Analista ou Gestão — o Protocolo só consulta.

### Rotina do dia — Protocolo

1. Chegou processo → **Novo Processo** → **Salvar Processo**.
2. Acompanhar em **Processos Ativos**.
3. O processo saiu → em **Processos Ativos**, botão de saída (ícone de porta).
4. Se precisar de planilha → **Finalizados** → **Exportar Excel**.

---

## 4. Analista (Licitações e Liquidações)

Os dois analistas trabalham do mesmo jeito. A diferença é o **grupo** que cada um vê:

- **Licitações e Contratos** — só processos desse grupo; usa **Nº de despacho**.
- **Liquidações** — só processos desse grupo; o sistema pode gerar o **Número do relatório** ao assumir; o campo de valor aparece como **Valor analisado**.

**Menu:** Fila de análise · Atendimentos indicados · Alterar Senha · Sair

Você **não** cadastra processo, **não** registra saída, **não** muda prioridade e **não** indica atendimento de diligência (isso é da Gestão).

### 4.1 Fila de análise

Os cards no topo mostram quantos estão **disponíveis**, **com você**, **com o Controlador**, com prazo vencido e com atendimento indicado.

A lista padrão (**Para trabalhar**) traz só o que você ainda pode agir: disponíveis, os que estão com você e os direcionados a você. Processo já enviado ao Controlador **não** aparece nessa lista — só no número do card. Clique no card se quiser ver quais são; não há o que analisar neles.

Filtros: **Para trabalhar**, **Disponíveis**, **Comigo**, **Direcionados para mim**, **Vencidos**.

Na linha do processo:

| Botão | Quando usar |
|---|---|
| **Assumir processo** | Está disponível e você vai analisar |
| **Analisar** | Já está com você |
| **Liberar assinatura** | Foi direcionado para você só para liberar |
| **Ver** | Só consultar |

### 4.2 Analisar o processo

1. Na fila, clique em **Assumir processo** (se ainda estiver disponível) ou em **Analisar**.
2. Preencha a análise:
   - Status da análise (Prosseguimento sem ressalva, com ressalva, Não Prosseguimento, Devolução para saneamento…)
   - **Nº de despacho** (Licitações) **ou** **Número do relatório** (Liquidações)
   - **Destino**
   - Valor, período e observação, quando couber
3. Clique em **Salvar análise** sempre que quiser gravar o andamento.

Para **liberar para assinatura** ou **direcionar**, o sistema exige pelo menos: status da análise (não use “Não Aplicável”), número de despacho ou de relatório, e destino. Algumas espécies também exigem valor.

**Encaminhar:** clique em **Encaminhar**. Abre a lista com três opções:

- **Para o Controlador** — a análise está pronta e o processo segue para assinatura.
- **Para outro analista** — escolha o colega. Quem analisou continua sendo você; o colega só encaminha ao Controlador.
- **Para a fila (sem análise)** — o processo volta a ficar disponível, sem analista. Os dados da tentativa são limpos.

As duas primeiras só ligam com a análise preenchida.

### 4.4 Pendências

Se faltar documento ou informação:

1. Escreva o texto em **Nova pendência**.
2. Clique em **Adicionar**.

A Gestão trata a diligência fora do sistema e, depois, indica o atendimento. Quando isso acontecer, você vê a pendência em **Atendimentos indicados**.

Aí você pode:

- **Confirmar resolução** — a pendência fica resolvida.
- **Atendimento insuficiente** — explique o que ainda falta; a pendência volta para a Gestão.

Se a pendência foi cadastrada por engano, cancele (ícone) e informe o motivo. O registro não é apagado.

Pendências de passagens anteriores da CGM aparecem só para leitura.

### 4.5 Atendimentos indicados

Menu próprio com o que a Gestão já sinalizou. Dá para **Abrir processo**, **Confirmar resolução** ou marcar **Atendimento insuficiente**.

### Rotina do dia — Analista

1. Abra a **Fila de análise**.
2. **Assuma** um processo disponível (do seu grupo).
3. Preencha a análise e **Salvar análise**.
4. Se faltar algo, **Adicionar** pendência.
5. Quando estiver completo: **Encaminhar** e escolha o destino.
6. Olhe **Atendimentos indicados** no começo do dia.

---

## 5. Gestão

A Gestão **acompanha e organiza**. Não assume processo, não preenche análise e não libera assinatura.

Na tela do processo aparece um aviso de consulta: você **vê**, mas não pratica ato de analista.

**Menu:** Processos Ativos · Finalizados · Dashboard · Gestão de Processos · Para assinar · Diligências · Gestão de Pessoas CGM · Cadastros · Alterar Senha · Sair

### 5.1 Dashboard

Visão geral da casa: quantos estão em tramitação, disponíveis, em análise, para assinar, para retirar, vencidos, urgentes, com diligência etc.

Os cards são clicáveis e levam à lista correspondente.

Dá para filtrar por período, grupo, analista, secretaria e espécie. Há também o quadro da **equipe de análise** (ordem alfabética, sem ranking) e tempos médios.

### 5.2 Gestão de Processos

Fila completa dos dois grupos. Use para ver o estoque e **alterar a prioridade** no seletor da linha (grava na hora). O card **Com o Controlador** mostra quantos já foram encaminhados para assinatura.

A ação da linha é **Ver** — não existe **Assumir** para a Gestão.

Se um analista assumiu por engano e o processo ficou preso, use **Fila sem análise**. O processo volta a ficar disponível.

### 5.3 Para assinar

Lista do que já foi **liberado para assinatura**. Use para saber o que recolher e levar ao Controlador. A assinatura em si é no papel.

Depois de assinado, o Protocolo faz **Disponibilizar para retirada**.

### 5.4 Diligências

Pendências abertas pelos analistas.

- **Aguardando atendimento** — ainda não foi tratada.
- **Atendimento indicado** — você já sinalizou no sistema que o órgão atendeu.

Fluxo:

1. Trate a diligência **fora** do sistema (telefone, ofício, e-mail — isso não é registrado aqui).
2. Quando o atendimento chegar, clique em **Indicar atendimento**.
3. O analista responsável confirma se resolveu ou se ainda está insuficiente.

A Gestão **não** conclui tecnicamente a pendência. Quem confirma é o analista.

### 5.5 Processos Ativos e Finalizados

Mesmas listas do Protocolo, com algumas diferenças:

- Gestão **não** edita dados de protocolo.
- Gestão **pode cancelar** o processo (ícone). Informe o **motivo**. O registro permanece.
- Em Finalizados, Gestão pode **Exportar Excel** e **Concluir monitoramento**.

Concluir monitoramento **não** é registrar saída. É só o acompanhamento periódico depois que o processo já saiu.

### 5.6 Gestão de Pessoas CGM

Registre férias, cursos e outras indisponibilidades da equipe.

1. Escolha o servidor, o tipo, o período (ou o dia da semana, se for recorrente) e, se quiser, uma observação.
2. Clique em **Registrar**.

**Desativar** um registro não apaga o histórico.

Essa informação aparece para o analista na hora de direcionar assinatura, mas **não bloqueia** o trabalho de ninguém.

### 5.7 Cadastros

Parametrize o sistema, sem excluir. Dá para **inativar** e **reativar**.

Abas:

- **Unidades Administrativas** — secretarias da lista de entrada
- **Espécies de Processo** — nome, grupo, monitoramento, se gera número de relatório, se exige contratada/valor etc.
- **Prioridades** — prazos
- **Tipos de Indisponibilidade** — férias, curso etc.

Para incluir: preencha **Novo registro** e clique em **Adicionar**. Para ajustar um existente: altere e **Salvar**.

Alguns campos ficam travados depois de criados (por exemplo, o grupo da espécie e o código da prioridade), para não bagunçar processos antigos.

### Rotina do dia — Gestão

1. Olhe o **Dashboard**.
2. Ajuste prioridades em **Gestão de Processos**, se preciso.
3. Use **Para assinar** para recolher o que vai ao Controlador.
4. Em **Diligências**, indique os atendimentos que já chegaram.
5. Mantenha **Cadastros** e **Gestão de Pessoas CGM** em dia.

---

## 6. Dúvidas frequentes

**Por que não vejo o menu Novo Processo / Fila / Dashboard?**  
O menu segue o papel da sua conta. Se estiver errado, fale com quem passou o acesso.

**Posso apagar um processo?**  
Não. A Gestão pode **cancelar**, mas o registro continua no histórico.

**O analista de Licitações vê processo de Liquidação?**  
Não. Cada analista só vê o próprio grupo. A Gestão vê os dois.

**Cadastrei a pendência. E agora?**  
A Gestão faz a diligência fora do sistema e clica em **Indicar atendimento**. Depois o analista confirma se resolveu.

**O processo precisa ser analisado para eu dar saída?**  
Não. Em **Processos Ativos**, o Protocolo registra a saída na hora. Análise e assinatura são etapas extras, para quando a casa estiver organizada.

**Onde assino o despacho no sistema?**  
Em lugar nenhum. A assinatura do Controlador é no papel. No sistema, o analista **encaminha para o Controlador** e a Gestão usa a tela **Para assinar** para saber o que recolher.

**O que é monitoramento?**  
Em algumas espécies, depois da saída a CGM acompanha o processo de tempos em tempos (pendente, atrasado ou concluído). Não é uma lista de tarefas do dia.

**Esqueci a senha.**  
Peça a quem passou o acesso para redefinir.

---

*Sistema de Protocolo e Gestão de Processos — Controladoria Geral do Município de Saquarema.*
