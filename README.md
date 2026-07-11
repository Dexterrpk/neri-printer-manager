# Neri Printer Manager

Aplicativo para descobrir, instalar, diagnosticar e administrar impressoras no Linux Mint.

## Escopo da versão 1.0

- Impressoras USB, IPP/IPPS, JetDirect, LPD e SMB.
- Filas CUPS: listar, instalar, remover, pausar, retomar e testar.
- Descoberta por CUPS e Avahi.
- Diagnóstico de serviço, porta 631, comandos obrigatórios e rede local.
- Interface gráfica PySide6 e CLI para suporte remoto.
- Operações administrativas sem executar a interface como root.
- Validação de entradas, execução sem `shell=True`, timeout e logs rotativos.
- Testes, lint, CI e preparação para pacote Debian.

## Desenvolvimento

```bash
sudo apt update
sudo apt install -y python3-venv cups cups-client avahi-utils policykit-1
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
neri-printer-manager
```

## CLI

```bash
neri-printer-cli list
neri-printer-cli discover
neri-printer-cli diagnose
neri-printer-cli add --name RECEPCAO --uri socket://192.168.1.50:9100
```

## Segurança

A interface roda como usuário comum. Somente comandos específicos são elevados com `pkexec`. Nomes de filas e URIs passam por validação centralizada antes de qualquer alteração.

## Liberação para produção

O projeto será considerado homologado após os testes descritos em `docs/HOMOLOGATION.md` em Linux Mint real, incluindo USB, IP, compartilhamento Mint/Windows e usuário sem privilégios.
