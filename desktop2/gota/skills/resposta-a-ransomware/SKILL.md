---
name: resposta-a-ransomware
description: Use quando houver suspeita ou confirmação de ransomware (arquivos criptografados, nota de resgate, extensões estranhas); resposta defensiva a incidente.
keywords: ransomware, resgate, criptografados, malware, incidente, vírus, backup, isolar, contenção, imutável
---
# Resposta defensiva a ransomware

1. **Contenha primeiro**: desconecte a máquina da rede (cabo ou Wi-Fi) e, se possível, isole o segmento. Se precisar de evidências em memória, não force o desligamento de imediato. Não pague nem responda ao resgate antes de decidir com a gestão.
2. **Preserve**: anote horário, nome do computador, extensão dos arquivos e a nota de resgate (foto da tela). Não apague nada.
3. **Delimite**: procure a mesma extensão em compartilhamentos e outras máquinas; no AD, veja logons suspeitos (eventos 4624, 4625, 4672) e contas ou serviços novos (4720, 7045).
4. **Proteja os backups**: confirme que o repositório de backup não está acessível a partir das máquinas afetadas (no Veeam, repositório com imutabilidade ou Hardened, credenciais separadas, regra 3-2-1). Suspenda retenções que apagariam pontos antigos.
5. **Erradique e recupere**: refaça a origem a partir de imagem confiável, troque senhas e chaves (principalmente de contas privilegiadas), restaure de um ponto **anterior à infecção** e, antes de reconectar, varra o ponto restaurado (no Veeam, Secure Restore).
6. **Comunique**: gestão e jurídico (LGPD se houver dados pessoais) e registre a linha do tempo para aprender com o incidente.
