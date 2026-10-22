---
name: desenvolver-no-projeto
description: Use quando o pedido for programar, criar, corrigir, alterar, testar ou entender código de um projeto (um recurso novo, um bug, testes, refatoração).
keywords: programar, codar, código, projeto, função, classe, bug, erro, corrigir, criar, arquivo, teste, testes, refatorar, python, javascript, vscode, desenvolver
---
# Desenvolver em um projeto, em etapas

1. **Entenda antes de mexer.** Use `repo_map` para ver a estrutura e `read_file` nos arquivos que importam. Nunca invente o conteúdo de um arquivo e nunca mude o que não leu.
2. **Planeje em passos curtos** (3 a 5), na ordem em que serão feitos, e siga a ordem.
3. **Um arquivo por vez.**
   - Arquivo novo: `write_file` com o conteúdo COMPLETO e funcional (sem "..." nem trechos faltando).
   - Arquivo existente: `edit_file` com o trecho exato antigo e o novo. Mudanças pequenas e localizadas.
4. **Verifique.** Rode os testes: em Python, `python -m unittest` (já vem com o Python); em Node, `npm test`. Se o projeto não tem testes, rode o programa ou compile para ver se não há erro.
5. **Leia o resultado de verdade.** O código de saída 0 significa que passou (muitos programas escrevem no canal de erro mesmo quando dá certo). Se falhar, leia a mensagem, corrija a causa e rode de novo; não repita a mesma tentativa.
6. **Para mostrar uma mudança maior antes de aplicar**, use `vscode` com `diff`: abre o arquivo e a versão proposta lado a lado, sem alterar o original.
7. **Finalize** com o que foi feito, os arquivos tocados e como rodar. Se a tarefa for grande, entregue a primeira parte funcionando e diga o que falta.
8. Nunca instale pacotes, apague arquivos nem mexa fora da pasta do projeto sem o usuário pedir.
