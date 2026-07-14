# Neri Printer Manager

Aplicativo para descobrir, instalar, compartilhar, diagnosticar e administrar impressoras no Linux Mint e derivados Ubuntu.

## Versão atual: 1.4.0

### Principais recursos

- Busca por IP, hostname, DNS, mDNS e NetBIOS.
- Impressoras IPP/IPPS, JetDirect, LPD e compartilhamentos SMB autenticados.
- Descoberta com nome da impressora, modelo, hostname, IP, protocolo e fila local separados.
- Instalação inteligente com busca em `lpinfo -m` por PPD/driver do fabricante.
- Prioridade para HPLIP/HPCUPS, Gutenprint e Foomatic compatíveis.
- Uso de PCL/PostScript genérico somente como último recurso.
- Credenciais SMB aplicadas na URI de instalação com codificação segura.
- Ativação da fila e envio automático de página de teste após instalar.
- Remoção automática da fila quando a tentativa falha.
- Instalação USB, compartilhamento, diagnóstico, filtros, filas e relatórios.

## Primeira instalação no Linux Mint

Em um usuário com `sudo`:

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates
cd ~
git clone https://github.com/Dexterrpk/neri-printer-manager.git
cd neri-printer-manager
sudo bash ./install.sh
neri-printer-manager
```

## Instalação usando `su`

Use quando o usuário logado não pertence ao grupo de administradores, mas você possui a senha do root:

```bash
cd ~/neri-printer-manager
git restore install.sh 2>/dev/null || true
git pull --ff-only
PROJECT_DIR="$PWD"
su -c "cd '$PROJECT_DIR' && bash ./install.sh --fast"
neri-printer-manager
```

O `su -c` instala como root e retorna ao usuário comum. Não abra a interface gráfica como root.

## Atualização mais rápida

Com `sudo`:

```bash
cd ~/neri-printer-manager
git restore install.sh 2>/dev/null || true
git pull --ff-only
sudo bash ./install.sh --fast
```

Sem `sudo`, usando a senha do root:

```bash
cd ~/neri-printer-manager
git restore install.sh 2>/dev/null || true
git pull --ff-only
PROJECT_DIR="$PWD"
su -c "cd '$PROJECT_DIR' && bash ./install.sh --fast"
```

O modo `--fast` não executa APT, reutiliza o ambiente Python íntegro, reinstala somente o programa, executa testes e mantém rollback.

## Reparo completo

Com `sudo`:

```bash
cd ~/neri-printer-manager
git pull --ff-only
sudo bash ./install.sh --repair
```

Com `su`:

```bash
cd ~/neri-printer-manager
git pull --ff-only
PROJECT_DIR="$PWD"
su -c "cd '$PROJECT_DIR' && bash ./install.sh --repair"
```

## Instalar impressora compartilhada por Windows ou outro computador

1. Abra **Encontrar na rede**.
2. Digite o hostname ou IP do computador.
3. Informe o usuário exatamente como o servidor espera, por exemplo:

```text
same
suporte
DOMINIO\same
COMPUTADOR\suporte
```

4. Informe a senha e clique em **Buscar**.
5. Selecione a impressora encontrada e clique em **Instalar selecionada**.

Na versão 1.4.0 o programa:

1. usa as credenciais informadas para descobrir a fila SMB;
2. codifica usuário e senha corretamente na URI usada pelo backend SMB;
3. pesquisa drivers instalados com `lpinfo -m`;
4. tenta primeiro o PPD mais compatível com o nome/modelo da fila;
5. usa HPLIP/HPCUPS, Gutenprint ou Foomatic quando houver correspondência;
6. deixa drivers genéricos para o final;
7. ativa e libera a fila no CUPS;
8. envia uma página de teste automaticamente;
9. remove a fila caso a tentativa falhe.

> Não grave senhas no GitHub ou no README. As credenciais são informadas na interface e usadas durante a instalação.

## Verificar a instalação

```bash
neri-printer-manager
neri-printer-cli --help
/opt/neri-printer-manager/venv/bin/python -m pip show neri-printer-manager | grep Version
/opt/neri-printer-manager/venv/bin/python -m pip check
```

Log da instalação:

```bash
su -c "tail -n 200 /var/log/neri-printer-manager-install.log"
```

## Instalar impressora USB

1. Conecte e ligue a impressora.
2. Abra **Ferramentas**.
3. Clique em **Procurar USB**.
4. Confira fabricante, modelo e driver recomendado.
5. Selecione a impressora e clique em **Instalar USB selecionada**.
6. Abra **Minhas impressoras** e confirme a página de teste.

## Compartilhar uma impressora USB ou local

1. Abra **Minhas impressoras** e selecione a fila.
2. Abra **Compartilhamento**.
3. Clique em **Compartilhar impressora selecionada**.
4. Autorize a ação administrativa.

## Desenvolvimento

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

## Segurança

A interface roda como usuário comum. Ações administrativas usam PolicyKit. Nomes de filas, URIs e pacotes são validados e nenhum comando externo é executado com `shell=True`.

## Estado de homologação

A versão 1.4.0 melhora a instalação SMB autenticada e a seleção automática de PPD. A confirmação final ainda depende do modelo físico, driver disponível, políticas SMB, firewall e configuração do computador que compartilha a impressora.
