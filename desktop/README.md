# Gota para Windows

O mesmo mordomo do celular, rodando no computador, **offline** (a internet só é usada para pesquisar, para o clima, para o Outlook e para o WhatsApp Web).
Este projeto é **independente** do `mobile/`: não usa nenhum arquivo dele.

## Como usar

| O que fazer | Como |
|---|---|
| Abrir pelo código | `run.bat` (usa o ambiente Python que já está em `.venv`) |
| Gerar o programa | `build.bat` (sai `dist\Gota\Gota.exe`; a pasta `models` é ligada ao lado dele, sem copiar) |
| Gerar uma pasta portátil para entregar | `build.bat copy` (copia os modelos para dentro de `dist\Gota\models`, ~5 GB) |
| Testes rápidos | `.venv\Scripts\python.exe tests\test_core.py` |
| Testes com o modelo de verdade | `.venv\Scripts\python.exe tests\live_route.py` (e os outros `tests\live_*.py`, `tests\gui_*.py`) |

Tudo que **não** é dado do usuário já vem no projeto, então **nada é baixado no primeiro uso**:

* `models\` — IA (Gemma 4 E2B, 2,5 GB), pintor de imagens (SDXS-512 + decodificador completo, 1,9 GB), voz masculina Piper, reconhecimento Vosk e Whisper (veja `models\README.md`).
* `.venv\` — as bibliotecas Python (precisa do Python 3.12 instalado; use `.venv\Scripts\python.exe -m pip ...`, não o `pip.exe`).
* `gota\assets\` — o gatinho animado, o ícone e as notas de TI (`gota\seed`).

Os dados do usuário ficam em `%APPDATA%\Gota` (conversas, memória, apelidos, chaves do Outlook e a sessão do WhatsApp). Imagens geradas vão para `Imagens\GOTA AI`. Erros ficam em `%APPDATA%\Gota\gota.log`.

## O que ele faz

| Função | No Windows |
|---|---|
| Conversas, várias, salvas, com título gerado pela IA; nome e tratamento; memória de fatos | sim |
| Texto selecionável e comandos/scripts em bloco separado com botão **Copiar** | sim |
| Respostas rápidas, pesquisa na web sempre pelo mais recente, clima e chuva | sim |
| Voz de mordomo, ditado 🎤, ligação 📞 (janelinha com o gato, balão e 3 botões) com memória da conversa | sim |
| Chamar o Gota | **Ctrl+Alt+G** (de novo cancela), ou "Hey Gota", ou o ícone perto do relógio |
| Ligar | **Ctrl+Alt+L** (de novo desliga) |
| Ver a tela (qualquer monitor: "analisa a tela 2") | sim, por conversa natural |
| Especialista em TI/segurança/Windows/Linux/Veeam, que aprende sozinho na internet | sim (`gota\seed` + base de conhecimento) |
| Agente no computador (arquivos, comandos, rede, disco, Git, relatórios...) | sim, com confirmação para o que é perigoso |
| **WhatsApp** (menu Conexões): mandar mensagem e prints (da tela toda ou de uma parte) a um contato | sim, pelo WhatsApp Web (não oficial), pedindo confirmação antes de enviar |
| **Outlook** (menu Conexões): agenda e e-mails importantes a responder | sim, pela API oficial da Microsoft, somente leitura |
| **Projetos de programação** (botões *Novo projeto* e *Selecionar projeto*; importar pasta existente) | o Gota trabalha dentro da pasta, em etapas (lê, planeja, escreve, testa e corrige), com uma permissão por sessão para editar aquela pasta; guarda cópia de arquivos reescritos |
| **VS Code**: botão *Abrir no VS Code*; se não estiver instalado, o Gota oferece baixar e instalar (pedindo permissão) | sim; a integração (menu Conexões) liga um servidor local protegido por senha e instala a **extensão do Gota** (explicar, corrigir, refatorar, testar, documentar e gerar código, com comparação antes de aplicar) |
| **Aprende sozinho**: se não sabe algo, acha a documentação oficial na internet (para bibliotecas, direto no PyPI/npm com os exemplos), baixa, confere que é do assunto e guarda na base para sempre | sim; vale para perguntas e para tarefas de programação (o agente usa `kb_learn` quando um erro mostra que não conhece a biblioteca) |
| Painéis à direita: **Tarefas em segundo plano** e **Arquivos** (só dentro de projetos) | sim; conversas e projetos são separados (a lista de conversas não mostra projetos) |
| Renomear conversas, lista de conversas | botões *Selecionar conversa* (renomear e apagar) e duplo clique no título |
| Alarmes, timers, abrir programas e apelidos ("whats 2") | sim |
| Imagens offline e anexar foto | sim |
| Ligar para números, SMS, contar notificações, gesto de borda, bolha | **só existem no celular** |

## Ideias do OpenClaude (reescritas do zero)

O [OpenClaude](https://github.com/Twigpine/openclaude) é um agente de programação de linha de comando que usa **modelos grandes na nuvem**. O repositório dele declara conter código derivado de código proprietário da Anthropic, sem autorização para distribuí-lo; por isso **nenhum código dele foi copiado** (importante para vender o Gota). Só ideias gerais foram reimplementadas aqui, rodando offline:

| Ideia dele | No Gota |
|---|---|
| Resposta em fluxo (streaming) | o texto aparece enquanto é escrito e a voz começa na primeira frase |
| Skills (`SKILL.md`) | `gota\skills` (8 de TI embutidas) e `%APPDATA%\Gota\skills` (as suas); menu **Habilidades**; o especialista e o agente seguem a que combina com o pedido |
| Roteamento simples × forte | contas, porcentagens, raízes e conversões de unidade respondidas na hora, sem modelo; modelo "aquecido" em segundo plano |
| Agente com plano e limite de passos | plano em passos antes de tarefas longas; no limite, resume o que foi feito e o que falta |
| Sub-agentes (explorar, verificar) | ferramenta `delegate`: um sub-agente que **só lê**, sem poder alterar nada |
| Agente de verificação | confere respostas curtas do agente contra o que as ferramentas realmente mostraram |
| Sessões em segundo plano | "faz isso em segundo plano e me avisa"; menu **Tarefas em segundo plano** |
| Mapa do repositório | ferramenta `repo_map` (estrutura, arquivos-chave, classes e funções) |
| Busca na web com reserva | Bing e, se falhar, DuckDuckGo |

**Não trazido, de propósito:** servidor gRPC, hooks e o "buddy" de terminal. São infraestrutura de desenvolvedor para a linha de comando e não fazem sentido num assistente local. Também não torna o modelo de 2B mais inteligente: isso depende do modelo, não do agente. A nuvem (OpenRouter/MiniMax) e a extensão do VS Code foram trazidas depois; veja as seções "Nuvem e offline" do [README raiz](../README.md) e "Integração com o VS Code" deste arquivo.

## Limites honestos

* **Programar:** o Gota segue o mesmo jeito de trabalhar de um agente de código (etapas, testes, correção), mas a qualidade do código é a de um modelo de 2B parâmetros: bom para funções, testes e ajustes pequenos; fraco em projetos grandes e em lógica difícil. Revise o que ele altera (há cópia dos arquivos reescritos em `%APPDATA%\Gota\backups`).
* A extensão do VS Code não pôde ser testada dentro do VS Code real (não instalado neste computador); foi testada com um VS Code simulado e contra o servidor.
* O modelo é pequeno (2B) e roda na CPU: a primeira mensagem de cada conversa leva alguns segundos a mais (o app já "aquece" o modelo em segundo plano).
* O envio pelo WhatsApp depende de o WhatsApp Web não mudar; o Outlook depende de a TI da empresa permitir o login.
* Não há cancelamento do som do computador: se tocar outra voz alto enquanto você fala, ele pode se confundir.

## Agente avançado

O agente (modo de tarefas, projetos e rotinas) ganhou, em camadas e sem deixar o chat comum mais lento:

| Recurso | O que faz |
|---|---|
| **Ferramentas em paralelo** | Várias consultas de leitura no mesmo passo (`"actions":[...]`) rodam ao mesmo tempo. |
| **Sub-agentes em paralelo** | `delegate` com até 4 tarefas ao mesmo tempo: explorar, verificar, planejar, revisar, redigir e **clone** (herda o contexto da conversa). Todos só leem. |
| **Modo plano** | Em tarefas de vários passos o plano aparece numa janela e só executa depois de **Executar**; uma lista de tarefas ao vivo mostra o andamento. Desligável em *Memória e rotinas*. |
| **Memória entre conversas** | Guarda sozinho (sem chamar o modelo) quem você é, como gosta das coisas, seus ambientes e referências. Janela *Memória e rotinas* para ver, corrigir e apagar. |
| **Conversas antigas** | A busca de conversas procura no conteúdo; a ferramenta `chat_search` retoma de onde parou. |
| **Documentos enormes** | `read_document` lê PDF/DOCX/texto de qualquer tamanho em partes ao mesmo tempo (com a nuvem) e responde a pergunta ou resume. |
| **Navegador geral** | `browser`: abre sites, lê a estrutura (elementos com `ref N`), clica, digita (nunca senhas), rola, tira print, lê erros do console e requisições de rede, testa em tela de celular/tablet/desktop. Site novo e cliques de envio/compra/apagar pedem permissão. |
| **Terminal e arquivos** | PowerShell e **Bash** (Git Bash ou WSL), notebooks **Jupyter** célula por célula, busca profunda na web (lê as melhores páginas). |
| **GitHub** | `github` usa o `gh`: PRs, issues e CI (criar/comentar pedem confirmação; apagar repositório, tokens e chaves são proibidos). `git_worktree` cria uma cópia isolada do projeto. |
| **Páginas e documentos** | `make_html` (páginas interativas), `make_chart` (gráficos claro/escuro), `make_slides` (PowerPoint), `serve_and_open` (servidor local + navegador). |
| **Rotinas e avisos** | Tarefas que rodam sozinhas em horário fixo, **só com consultas**, e avisam por notificação do Windows (e no celular com um tópico ntfy). |
| **MCP** | Servidores MCP de terceiros em *Integrações > Servidores MCP*; tudo que voltam é tratado como dados. |
| **Habilidades prontas** | `skill_install` instala um `SKILL.md` de um endereço, depois de mostrar o conteúdo. |
| **CLI e SDK** | `python main.py --cli "pergunta"` (ou sem pergunta, interativo) e `from gota.sdk import Gota`. |

**Segurança em camadas:** proibido (senhas, apagar repositório, chaves), pede confirmação (enviar, comprar, apagar, site novo, instalar) e livre (leitura). O que vem de páginas, arquivos, GitHub e servidores MCP é marcado como **dados externos**: nunca é obedecido como ordem. Rotinas rodam sem aprovação humana, então recusam qualquer ação que altere o computador.

**Limites honestos:** profundidade de raciocínio, janela de contexto, visão e fluência em outros idiomas dependem do modelo (o da nuvem é muito melhor que o Gemma offline). Não há sessões na nuvem nem ambiente isolado remoto: o Gota roda na sua máquina Windows. As páginas geradas guardam estado só no navegador (localStorage), sem banco compartilhado.
