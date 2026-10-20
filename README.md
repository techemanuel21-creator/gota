# Gota

Assistente pessoal local e gratuito: um gato mordomo que vive no seu aparelho, funciona offline e conversa em português.

Dois projetos **independentes**: cada um tem seu próprio `.gitignore`, suas dependências e seus modelos, e nenhum usa arquivos do outro.

| Pasta | O que é | Como começar |
|---|---|---|
| [`mobile/`](mobile) | App Android (Kotlin), com o mesmo Gemma rodando no celular | abrir `mobile/` no Android Studio, ou `cd mobile` e `gradlew.bat assembleDebug` |
| [`desktop/`](desktop) | Programa para Windows (Python), com IA, voz, imagens, WhatsApp e Outlook | `desktop\run.bat` (veja `desktop/README.md`) |


## Instalar e atualizar o Gota Desktop (Windows)

No PowerShell (sem precisar de administrador):

```powershell
irm https://raw.githubusercontent.com/techemanuel21-creator/gota/main/desktop/install.ps1 | iex
```

Atualizar para a versão mais recente (mantém modelos, ambiente e seus dados):

```powershell
irm https://raw.githubusercontent.com/techemanuel21-creator/gota/main/desktop/update.ps1 | iex
```

O instalador usa o Python 3.12 (instala pelo winget se faltar), baixa o código, cria o ambiente e um atalho "Gota" na área de trabalho. Os modelos de IA (alguns GB) são baixados no primeiro uso.
