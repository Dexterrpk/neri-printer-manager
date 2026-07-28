# Histórico de mudanças

Este projeto segue versionamento semântico.

## 2.0.1 — 2026-07-28

### Corrigido

- Instalação no Linux Mint 21 e 22 com dependência GLib compatível com as duas
  bases Ubuntu.
- O pacote passa a trazer a aplicação Python pronta, sem criar ambiente virtual
  nem executar `pip` durante o `apt install`.
- O helper PolicyKit e os lançadores usam diretamente o runtime empacotado.
- Ferramentas de desenvolvimento do PySide6 que não são usadas pelo aplicativo
  deixaram de aumentar o tamanho do instalador.

## 2.0.0 — 2026-07-21

### Adicionado

- Interface única com sete áreas: início, rede, filas locais, trabalhos,
  diagnóstico, compartilhamento e ferramentas.
- Enumeração das filas reais de um CUPS remoto para o fluxo Mint→Mint.
- Instalação SMB autenticada com senha por entrada padrão e API local do CUPS,
  sem exposição em linhas de comando.
- Definição de impressora padrão, compartilhamento/descompartilhamento por fila,
  conta Samba, backup privilegiado e relatórios higienizados.
- Detecção explícita de filas automáticas `implicitclass://`.
- Testes de regressão de segurança, empacotamento Debian e CI Python 3.10/3.12.

### Alterado

- Todas as operações administrativas passaram a usar um único helper PolicyKit
  com lista de permissões.
- Colisões de nome agora interrompem a instalação em vez de substituir uma fila.
- O compartilhamento do CUPS ficou limitado à rede local e agora desativa
  explicitamente acesso irrestrito e administração remota.
- `cups-browsed` deixou de ser dependência instalada automaticamente.
- Instalador, bootstrap e `.deb` agora preservam atualizações anteriores e usam a
  versão/arquitetura reais do projeto.
- Pontos de entrada, assistente e serviços legados sem consumidores foram
  removidos; `app.py` passou a ser a única interface gráfica.

### Corrigido

- Divergência entre a versão do pacote e a versão exposta pelo aplicativo.
- Leituras de widgets Qt a partir de *workers* e retenção desnecessária de senha
  no campo da interface.
- Falsos positivos causados por erros antigos no `error_log` do CUPS.
- Dispositivos fictícios (`network ipp`, `network socket`) listados pelo backend
  do CUPS e formatação de endereços IPv6 anunciados pelo Avahi.
- Detecção de impressoras USB expostas pelo backend `hp:/usb/` do HPLIP.
- Condição de corrida na troca de proprietário dos arquivos de backup.
- Vazamento potencial de URI autenticada em logs e pacotes de suporte.
- Operações administrativas sem tempo limite e atualização APT iniciada antes da
  validação da lista de pacotes.
- Rollback incompleto do instalador quando uma etapa posterior à troca de versão
  falhava.

## 1.5.0

- Central de saúde unificada e correção verificável.
- Descoberta enriquecida, instalação USB e suporte inicial a compartilhamento.
