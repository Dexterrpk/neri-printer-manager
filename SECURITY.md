# Política e modelo de segurança

## Versões suportadas

Correções de segurança são aplicadas à linha 2.x. Versões anteriores devem ser
atualizadas antes de uma investigação.

## Fronteira de privilégio

A interface e a CLI rodam como usuário comum. O executável
`/usr/libexec/neri-printer-helper` é o único componente elevado pelo PolicyKit.
Ele rejeita execução direta sem UID efetivo 0, valida novamente todos os valores e
aceita apenas operações enumeradas no código.

O helper não aceita comandos livres, caminhos de executável vindos do usuário,
pacotes fora do catálogo ou unidades `systemd` arbitrárias. Todos os subprocessos
usam caminhos absolutos e ambiente reduzido.

## Credenciais

- Senhas SMB não são opções de linha de comando. O helper usa a API Python do
  CUPS para transmitir a URI no pedido IPP local, sem criar um `lpadmin` com senha.
- A descoberta usa um arquivo temporário de modo `0600`, apagado em bloco `finally`.
- Logs, mensagens, relatórios e bundles passam por higienização recursiva.
- O CUPS pode persistir a URI necessária ao backend SMB em seu arquivo de
  configuração protegido pelo sistema. O backup que inclui esse arquivo é criado
  com modo `0600`; trate-o como material confidencial.

## Rede e compartilhamento

O programa não abre portas de firewall automaticamente. O CUPS é publicado com
as regras de rede local, e o Samba usa `guest ok = no`. Autorize portas no firewall
somente para uma rede confiável.

## Relato de vulnerabilidade

Não publique credenciais, logs integrais ou detalhes exploráveis em uma issue
pública. Abra primeiro um contato privado com o mantenedor do repositório e inclua:

- versão afetada e distribuição;
- cenário mínimo de reprodução;
- impacto observado;
- pacote de suporte somente depois de revisar seu conteúdo.

Se não houver canal privado configurado no GitHub, abra uma issue sem detalhes
sensíveis solicitando um meio de contato.
