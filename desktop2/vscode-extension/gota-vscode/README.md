# Gota para o VS Code

Usa o modelo do **Gota** (que roda neste computador, offline) para programar dentro do VS Code. Nada sai do PC.

## Como ligar
1. No Gota, abra **Conexões** e ative **Integração com o VS Code** (o Gota instala esta extensão e liga um servidor que só aceita conexões deste computador, com senha).
2. Reabra o VS Code. Na barra de status aparece **Gota**.

## O que faz
Selecione um trecho e use o menu de contexto (botão direito > **Gota**) ou a paleta de comandos (Ctrl+Shift+P > "Gota"):

* **Explicar a seleção**
* **Corrigir ou melhorar a seleção**, **Refatorar**, **Documentar**: o Gota mostra a proposta numa **comparação lado a lado** e só aplica se você confirmar.
* **Criar testes para a seleção**
* **Gerar código aqui**: descreva em português e ele escreve no cursor (com a mesma confirmação).
* **Perguntar** (Ctrl+Alt+K): pergunte sobre o arquivo ou o trecho selecionado.

## Limites
O modelo é pequeno (2B) e a janela de contexto é curta: funciona melhor em trechos de algumas dezenas de linhas. Revise sempre o que ele propõe.
