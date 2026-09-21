# Histórico de mudanças

Projeto criado e mantido por **Cleiton Neri — Neri Infotech**.

## 3.0.0-portable — 2026-09-20

### Adicionado

- edição portátil para Linux Mint, sem instalação permanente do aplicativo;
- execução simples por `run.sh`;
- lançador fixado em uma revisão portátil auditada;
- limpeza automática dos arquivos temporários ao sair;
- diagnóstico de CUPS, filas, permissões, URI, PPD, filtros, backends e comunicação;
- identificação de falha HPLIP por `Backend hp returned status 1`;
- tratamento de cenários de `client-error-not-authorized`, Ghostscript, filtros e trabalhos pendentes;
- backup temporário e validação com `cupsd -t` antes de reinícios após mudanças relevantes;
- rollback quando uma alteração de configuração não passa na validação;
- documentação revisada com foco em uso real, segurança e autoria.

### Segurança

- modo portátil não administra Zentyal, firewall, DNS, DHCP, gateway, rotas, VLAN ou NetworkManager;
- nenhuma rotina de brute force ou tentativa automática de senha;
- testes de rede limitados ao destino selecionado e portas de impressão;
- correções priorizam a menor alteração possível;
- jobs e filas não relacionados não devem ser modificados sem confirmação.

### Corrigido

- parsing de `lpstat` dependente do idioma;
- possibilidade de textos como `or` e `pdftopdf` serem tratados como nomes de impressora em scripts auxiliares;
- diagnóstico genérico de "retido" substituído por investigação baseada em fila, filtro, backend e log do trabalho.

## 2.0.1 — 2026-07-28

- compatibilidade de instalação com Linux Mint 21 e 22;
- pacote passou a incluir a aplicação Python pronta;
- helper PolicyKit e lançadores passaram a usar o runtime empacotado;
- redução de dependências de desenvolvimento no pacote final.

## 2.0.0 — 2026-07-21

- interface PySide6 unificada;
- descoberta de filas CUPS remotas;
- instalação SMB autenticada sem senha em linha de comando;
- definição de impressora padrão, compartilhamento por fila, backup e relatórios;
- detecção de `implicitclass://`;
- helper PolicyKit com ações enumeradas;
- testes de segurança e CI;
- correções em descoberta USB/HPLIP, logs, backup e validação administrativa.

## 1.5.0

- central de saúde;
- descoberta enriquecida;
- instalação USB;
- suporte inicial a compartilhamento.
