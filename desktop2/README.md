# Gota Desktop 2 (motor opencode)

Cópia do Gota Desktop em que o modelo online vem do **opencode**, usando os modelos gratuitos dele (sem conta e sem chave de API). O restante (interface, roteador, voz, WhatsApp, agente, base de conhecimento) é o mesmo do `desktop`.

- **Como funciona:** o Gota inicia um `opencode serve` local (127.0.0.1, senha aleatória, só enquanto o Gota roda) e conversa com ele. Os prompts e o roteador continuam sendo do Gota; o opencode só fornece o modelo. Usa o agente `plan` (somente leitura) numa pasta vazia, então o modelo não mexe em arquivos.
- **O `opencode.exe` fica dentro do projeto** (`opencode/opencode.exe`, 172 MB, fora do git por causa do limite de 100 MB do GitHub; veja `opencode/README.md`). Nada é baixado durante o uso. `build.bat` o empacota no `Gota.exe`.
- **Modelo padrão:** `opencode/deepseek-v4.1-flash-free`. Reservas em corrida se o principal demorar: `glm-5.3-flash-free`, `nemotron-3.5-lightning-free`, `big-pickle`. Escolha outro com a configuração `oc_model`.
- **Imagens:** o texto é lido por OCR e enviado como texto (os modelos de visão gratuitos são muito lentos).
- **Medido neste PC:** perguntas técnicas de 1,7 a 6,8 s; análise de imagem anexada ~12 s; análise de job do Veeam na tela ~12 s.
- **Sem opencode:** o Gota usa o OpenRouter (configuração `engine` = `openrouter`) e, offline, o Gemma local.

Rodar: `run.bat`. Testes: `.venv\Scripts\python.exe -m unittest tests.test_core`.
