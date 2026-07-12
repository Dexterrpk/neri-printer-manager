# Neri Printer Manager

Aplicativo para descobrir, instalar, compartilhar, diagnosticar e administrar impressoras no Linux Mint e derivados Ubuntu.

## Versão atual: 1.2.0

### Principais recursos

- Busca por IP, hostname, DNS, mDNS e NetBIOS.
- Impressoras IPP/IPPS, JetDirect, LPD e compartilhamentos SMB autenticados.
- Descoberta de impressoras locais e de rede com nome, modelo, host e IP separados.
- Instalação de impressora USB com comparação automática dos drivers disponíveis no CUPS.
- Preferência por drivers do fabricante, HPLIP/HPCUPS, Gutenprint e Foomatic; fallback PCL/PostScript.
- Compartilhamento da fila selecionada pelo CUPS e preparação do Samba.
- Filas CUPS: listar, instalar, remover, pausar, retomar e imprimir página de teste.
- Diagnóstico e correção orientada de CUPS, filtros, PPDs, backends, permissões e dependências.
- Interface executada como usuário comum; somente ações administrativas usam PolicyKit.

## Instalação ou atualização

```bash
sudo apt update
sudo apt install -y git ca-certificates
cd ~
if [ -d neri-printer-manager/.git ]; then
  cd neri-printer-manager
  git restore install.sh 2>/dev/null || true
  git pull --ff-only
else
  git clone https://github.com/Dexterrpk/neri-printer-manager.git
  cd neri-printer-manager
fi
sudo bash ./install.sh
neri-printer-manager
```

O instalador verifica e baixa antes da instalação todos os pacotes necessários, incluindo Python, ambiente virtual, PyTest, CUPS, Samba, HPLIP, Gutenprint, Foomatic, Avahi e bibliotecas gráficas do Qt. Os testes são executados antes da substituição dos atalhos instalados.

## Instalar impressora USB

1. Conecte e ligue a impressora.
2. Abra **Ferramentas**.
3. Clique em **Procurar USB**.
4. Confira fabricante, modelo e driver recomendado.
5. Selecione a impressora e clique em **Instalar USB selecionada**.

## Compartilhar uma impressora USB ou local

1. Abra **Minhas impressoras** e selecione a fila.
2. Abra **Compartilhamento**.
3. Clique em **Compartilhar impressora selecionada**.
4. Autorize a ação administrativa.

A fila é marcada como compartilhada no CUPS. O Samba é preparado para acesso autenticado; usuários e senhas continuam sendo administrados pelo sistema.

## Verificar versão

```bash
/opt/neri-printer-manager/venv/bin/pip show neri-printer-manager | grep Version
```

## Desenvolvimento

```bash
sudo apt install -y python3-venv python3-pytest cups cups-client avahi-utils policykit-1
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
neri-printer-manager
```

## Segurança

A interface roda como usuário comum. O helper administrativo aceita somente uma lista fechada de operações. Nomes de filas, URIs e pacotes são validados e nenhum comando externo é executado com `shell=True`.

## Homologação

Antes de uso amplo em produção, valide em Linux Mint real os cenários USB, IP, SMB com credenciais, compartilhamento Mint/Windows, página de teste e usuário sem privilégios conforme `docs/HOMOLOGATION.md`.
