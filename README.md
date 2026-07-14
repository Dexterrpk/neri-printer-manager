# Neri Printer Manager

Aplicativo para descobrir, instalar, compartilhar, diagnosticar e administrar impressoras no Linux Mint e derivados Ubuntu.

## Versão atual: 1.4.1

### Principais recursos

- Busca por IP, hostname, DNS, mDNS e NetBIOS.
- Impressoras IPP/IPPS, JetDirect, LPD e compartilhamentos SMB autenticados.
- Descoberta com nome, modelo, hostname, IP, protocolo e fila local separados.
- Seleção automática de PPD/driver com HPLIP, HPCUPS, Gutenprint e Foomatic.
- Driver PCL/PostScript genérico somente como último recurso.
- Instalação USB, compartilhamento, diagnóstico, filtros, filas e relatórios.

## Instalação universal — método recomendado

Execute **como o usuário comum que utilizará o programa**, sem entrar antes em um shell root:

```bash
wget -qO- https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash
```

O instalador detecta automaticamente o ambiente:

- usa `sudo` quando o usuário possui permissão;
- usa `su` e solicita a senha do root quando o usuário não possui `sudo`;
- identifica o usuário comum e sua pasta pessoal;
- baixa ou atualiza o projeto;
- escolhe instalação normal na primeira execução e modo rápido nas atualizações;
- verifica os pacotes já instalados;
- baixa somente as dependências ausentes;
- configura CUPS, Avahi e Samba;
- adiciona o usuário aos grupos `lp`, `lpadmin` e `sambashare`, quando existirem;
- instala o atalho global e um atalho no menu do usuário;
- valida dependências, testes e abertura da interface antes de concluir;
- preserva a versão anterior se a atualização falhar.

> Não execute o comando dentro de `su -` ou de um terminal já aberto como root. O próprio script solicita a autenticação necessária e retorna ao usuário comum.

Caso `wget` não esteja disponível, use:

```bash
curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash
```

## Atualização rápida

```bash
wget -qO- https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash -s -- --fast
```

O modo rápido não executa APT quando o ambiente existente está íntegro. Ele reutiliza PySide6 e as demais dependências, reinstala somente o Neri Printer Manager, executa os testes e mantém rollback.

## Reparo completo

```bash
wget -qO- https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash -s -- --repair
```

O reparo reinstala as dependências do sistema, recria o ambiente Python e reconfigura serviços, atalhos e permissões.

## Depois da instalação

Abra pelo menu do Mint ou execute como usuário comum:

```bash
neri-printer-manager
```

Verificação:

```bash
neri-printer-cli --help
/opt/neri-printer-manager/venv/bin/python -m pip show neri-printer-manager | grep Version
/opt/neri-printer-manager/venv/bin/python -m pip check
```

Se o usuário acabou de ser adicionado ao grupo `lpadmin`, encerre e abra a sessão do Mint uma vez para aplicar a nova associação de grupo.

Log da instalação:

```bash
su -c "tail -n 200 /var/log/neri-printer-manager-install.log"
```

## Impressora compartilhada por Windows ou outro computador

1. Abra **Encontrar na rede**.
2. Digite o hostname ou IP do computador.
3. Informe o usuário no formato exigido pelo servidor, por exemplo `same`, `suporte`, `DOMINIO\\same` ou `COMPUTADOR\\suporte`.
4. Informe a senha e clique em **Buscar**.
5. Selecione a impressora e clique em **Instalar selecionada**.

O programa usa as credenciais durante a instalação, procura o melhor PPD disponível, ativa a fila e envia uma página de teste. Senhas não devem ser gravadas no GitHub ou no README.

## Impressora USB

1. Conecte e ligue a impressora.
2. Abra **Ferramentas**.
3. Clique em **Procurar USB**.
4. Confira fabricante, modelo e driver recomendado.
5. Instale a impressora selecionada e confirme a página de teste.

## Segurança

A interface roda como usuário comum. Ações administrativas usam PolicyKit. Nomes de filas, URIs e pacotes são validados e nenhum comando externo é executado com `shell=True`.

## Estado de homologação

A versão 1.4.1 introduz o instalador universal com detecção de `sudo`/`su`, dependências incrementais, configuração de serviços, grupos e atalhos por usuário. A confirmação final de impressão ainda depende do modelo físico, driver disponível, políticas SMB, firewall e configuração do computador que compartilha a impressora.
