# Neri Printer Manager

Aplicativo para descobrir, instalar, compartilhar, diagnosticar e administrar impressoras no Linux Mint e derivados Ubuntu.

## Versão atual: 1.3.5

### Principais recursos

- Busca por IP, hostname, DNS, mDNS e NetBIOS.
- Impressoras IPP/IPPS, JetDirect, LPD e compartilhamentos SMB autenticados.
- Descoberta com nome da impressora, modelo, hostname, IP, protocolo e fila local separados.
- Resolução de hostname com timeout seguro: falhas de DNS/NetBIOS não interrompem a listagem.
- Instalação de impressora USB com comparação automática dos drivers disponíveis no CUPS.
- Preferência por drivers do fabricante, HPLIP/HPCUPS, Gutenprint e Foomatic; fallback PCL/PostScript.
- Compartilhamento da fila selecionada pelo CUPS e preparação do Samba.
- Filas CUPS: listar, instalar, remover, pausar, retomar e imprimir página de teste.
- Diagnóstico orientado de CUPS, filtros, PPDs, backends, permissões e dependências.

## Primeira instalação no Linux Mint

```bash
sudo apt-get update && sudo apt-get install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash -s -- --normal
```

A instalação normal verifica os pacotes do sistema e baixa somente os que estiverem ausentes.

## Atualização mais rápida

Use depois que o programa já estiver instalado:

```bash
cd ~/neri-printer-manager
git restore install.sh 2>/dev/null || true
git pull --ff-only
sudo bash ./install.sh --fast
```

O modo `--fast`:

- não executa `apt update`;
- não consulta nem reinstala pacotes APT;
- reutiliza o PySide6 e as demais dependências Python já instaladas quando o ambiente está íntegro;
- reinstala somente o pacote do Neri Printer Manager;
- executa testes e teste gráfico antes de concluir;
- mantém uma cópia para rollback durante a atualização;
- cria um ambiente novo automaticamente se detectar corrupção ou dependência ausente.

## Instalação normal pelo repositório

```bash
cd ~/neri-printer-manager
git restore install.sh 2>/dev/null || true
git pull --ff-only
sudo bash ./install.sh
```

## Reparo completo

```bash
cd ~/neri-printer-manager
git pull --ff-only
sudo bash ./install.sh --repair
```

O modo `--repair` reinstala as dependências do sistema e recria o ambiente do aplicativo.

## Comandos depois da instalação

Abra o programa como usuário comum:

```bash
neri-printer-manager
```

Verificação:

```bash
neri-printer-cli --help
/opt/neri-printer-manager/venv/bin/python -m pip show neri-printer-manager | grep Version
/opt/neri-printer-manager/venv/bin/python -m pip check
```

Log da instalação:

```bash
sudo tail -n 200 /var/log/neri-printer-manager-install.log
```

## Instalar impressora USB

1. Conecte e ligue a impressora.
2. Abra **Ferramentas**.
3. Clique em **Procurar USB**.
4. Confira fabricante, modelo e driver recomendado.
5. Selecione a impressora e clique em **Instalar USB selecionada**.
6. Abra **Minhas impressoras** e envie uma página de teste.

## Compartilhar uma impressora USB ou local

1. Abra **Minhas impressoras** e selecione a fila.
2. Abra **Compartilhamento**.
3. Clique em **Compartilhar impressora selecionada**.
4. Autorize a ação administrativa.

## Impressora compartilhada por Windows ou outro computador

Abra **Encontrar na rede**, informe hostname ou IP e, quando necessário, usuário e senha SMB. O programa tenta resolução DNS, mDNS e NetBIOS e lista as filas publicadas pelo computador informado.

## Desenvolvimento

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

## Segurança

A interface roda como usuário comum. O helper administrativo aceita somente uma lista fechada de operações. Nomes de filas, URIs e pacotes são validados e nenhum comando externo é executado com `shell=True`.

## Estado de homologação

A versão 1.3.5 possui instalação transacional, atualização rápida com reutilização segura do ambiente, testes automatizados e rollback. A validação final de hardware e rede depende dos testes reais em Linux Mint, pois modelos de impressora, firmware, drivers, firewall e políticas SMB variam entre ambientes.
