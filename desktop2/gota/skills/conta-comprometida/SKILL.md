---
name: conta-comprometida
description: Use quando houver suspeita de conta de usuário ou administrador comprometida, phishing ou acesso indevido.
keywords: conta, comprometida, phishing, senha vazada, acesso indevido, mfa, regra de e-mail, sessão, incidente
---
# Conta comprometida: resposta imediata

1. **Contenha**: redefina a senha (de outro dispositivo limpo), **revogue sessões e tokens** (Entra/M365: Revoke sessions; AD: encerre sessões e troque a senha duas vezes se for conta privilegiada), desative a conta se houver atividade ativa.
2. **MFA**: remova métodos desconhecidos e exija novo registro. Revise aplicativos OAuth autorizados e dispositivos registrados.
3. **E-mail**: procure regras de encaminhamento/exclusão criadas pelo atacante, delegações e envios em massa.
4. **Investigue**: logins (4624/4625/4768/4769 no AD, sign-in logs na nuvem), IPs e horários fora do padrão, movimentação lateral, arquivos acessados. Preserve evidências (exporte logs, anote horários).
5. **Escopo**: a mesma senha foi usada em outro lugar? Outras contas receberam o mesmo phishing? Máquina do usuário precisa de varredura/reimagem.
6. **Recuperação e prevenção**: MFA resistente a phishing, bloqueio de legado de autenticação, treinamento, alertas de login arriscado. Em dados pessoais, avalie obrigação de comunicar (LGPD).
