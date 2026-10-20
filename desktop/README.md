# Gota para Windows

O mesmo mordomo do celular, rodando no computador, **offline** (a internet só é usada para pesquisar e para o clima).

Rodar pelo código: Python 3.12, `pip install -r requirements.txt`, depois `python main.py`.
Gerar o programa: `pyinstaller Gota.spec --noconfirm` (sai a pasta `dist/Gota/Gota.exe`).
Testes: `python -m unittest discover -s tests`.

Na primeira vez ele pergunta seu nome, baixa o modelo (~2,5 GB), a voz masculina (~63 MB) e o reconhecimento de voz (~31 MB).
Tudo fica em `%APPDATA%\Gota` (conversas, memória, apelidos). Imagens vão para `Imagens\GOTA IA`.

| Função | No Windows |
|---|---|
| Conversas, várias, salvas; nome e tratamento; memória de fatos | igual |
| Respostas rápidas (hora, data, saudações), pesquisa na web sempre pelo mais recente, clima e chuva | igual (local pelo endereço de internet) |
| Voz de mordomo, ditado 🎤, ligação 📞 com memória, gatinho animado | igual (voz neural masculina offline) |
| Chamar o Gota | **Ctrl+Alt+G** em qualquer programa, ou "Hey Gota", ou o ícone perto do relógio |
| Abrir apps e apelidos ("whats 2") | programas do Menu Iniciar e da Microsoft Store |
| Alarmes e timers | sim (avisa com som e voz) |
| Agenda/resumo do dia | agenda do **Outlook clássico** instalado no PC |
| Imagens (offline, álbum GOTA IA) e anexar foto | sim; o pintor baixa (1,7 GB) na primeira imagem |
| WhatsApp | abre o WhatsApp Web com a mensagem pronta |
| Ligar, SMS, contar notificações, gesto de borda, bolha | **só existem no celular** |
