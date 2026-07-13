# Neri Printer Manager

Aplicativo para descobrir, instalar, compartilhar, diagnosticar e administrar impressoras no Linux Mint e derivados Ubuntu.

## Versão atual: 1.3.1

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

chmod +x install.sh
sudo bash ./install.sh
neri-printer-manager
```

## Atualização rápida sem verificar pacotes APT

Use somente quando as dependências já foram instaladas anteriormente:

```bash
cd ~/neri-printer-manager
git restore install.sh 2>/dev/null || true
git pull --ff-only
sudo bash ./install.sh --fast
neri-printer-manager
```

O modo `--fast` não executa `apt update` nem instala pacotes do sistema. Ele ainda cria uma instalação temporária, instala o pacote Python, executa os testes e só ativa a nova versão se tudo passar.

## Reparo completo

Para reinstalar todas as dependências do sistema e recriar o aplicativo:

```bash
cd ~/neri-printer-manager
git pull --ff-only
sudo bash ./install.sh --repair
```

## Ajuda do instalador

```bash
sudo bash ./install.sh --help
```

Sem opção, o instalador verifica os pacotes com `dpkg-query` e instala somente os que estiverem ausentes. Quando todos já estiverem instalados, o APT não é executado.

O instalador é transacional:

1. identifica e instala apenas dependências ausentes, exceto no modo `--fast`;
2. cria uma instalação temporária isolada;
3. valida dependências com `pip check`;
4. compila os módulos Python;
5. executa a suíte de testes usando o mesmo Python e PySide6 da nova versão;
6. constrói a janela em modo gráfico `offscreen`;
7. substitui a versão ativa somente se todas as verificações passarem;
8. restaura automaticamente a versão anterior se a ativação falhar.

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

A fila é marcada como compartilhada no CUPS. O Samba é preparado para acesso autenticado; usuários e senhas continuam sendo administrados pelo sistema.

## Impressora compartilhada por Windows ou outro computador

Abra **Encontrar na rede**, informe hostname ou IP e, quando necessário, usuário e senha SMB. O programa tenta resolução DNS, mDNS e NetBIOS e lista as filas publicadas pelo computador informado.

## Verificar versão e integridade

```bash
/opt/neri-printer-manager/venv/bin/python -m pip show neri-printer-manager | grep Version
/opt/neri-printer-manager/venv/bin/python -m pip check
neri-printer-cli --help
```

## Desenvolvimento

```bash
sudo apt install -y python3-venv cups cups-client avahi-utils policykit-1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

## Segurança

A interface roda como usuário comum. O helper administrativo aceita somente uma lista fechada de operações. Nomes de filas, URIs e pacotes são validados e nenhum comando externo é executado com `shell=True`.

## Estado de homologação

A versão 1.3.1 possui instalação transacional, testes automatizados e rollback. A validação final de hardware e rede depende dos testes reais em Linux Mint, pois modelos de impressora, firmware, drivers, firewall e políticas SMB variam entre ambientes. Use `docs/HOMOLOGATION.md` para registrar cada cenário validado no HRSAJ antes da implantação ampla.
