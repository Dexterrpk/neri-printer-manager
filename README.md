# Neri Printer Manager

Aplicativo para descobrir, instalar, compartilhar, diagnosticar e administrar impressoras no Linux Mint e derivados Ubuntu.

## Versão atual: 1.5.0

### Principais recursos

- Busca por IP, hostname, DNS, mDNS e NetBIOS.
- Impressoras IPP/IPPS, JetDirect, LPD e compartilhamentos SMB autenticados.
- Descoberta com nome, modelo, hostname, IP, protocolo e fila local separados.
- Seleção automática de PPD/driver com HPLIP, HPCUPS, Gutenprint e Foomatic.
- Driver PCL/PostScript genérico somente como último recurso.
- Instalação USB, compartilhamento, filas, relatórios e pacote de suporte.
- Central de saúde com diagnóstico explicável, correção selecionada, correção automática segura e verificação pós-reparo.

## Instalação universal — método recomendado

Execute **como o usuário comum que utilizará o programa**, sem entrar antes em `su` ou em um shell root:

```bash
wget -qO- https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash
```

Caso `wget` não esteja disponível:

```bash
curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash
```

O instalador escolhe a autenticação nesta ordem:

1. usa `sudo` quando o usuário realmente possui autorização;
2. usa a janela gráfica do **PolicyKit**, permitindo informar ou escolher uma conta administrativa;
3. usa `su` somente quando não houver agente PolicyKit disponível;
4. encerra com uma mensagem clara quando nenhuma credencial administrativa válida estiver disponível.

A senha é solicitada na primeira operação administrativa real. Depois disso, `sudo` ou PolicyKit podem manter a autorização em cache por alguns minutos; isso é comportamento normal do Linux.

> A senha pedida pelo `su` é a senha do **root**, e pode ser diferente da senha do usuário comum. Em instalações Mint com root bloqueado, autorize pela janela gráfica do PolicyKit ou peça a um administrador da máquina.

Além da autenticação, o script:

- identifica o usuário comum e sua pasta pessoal;
- baixa ou atualiza o projeto;
- escolhe instalação normal na primeira execução e modo rápido nas atualizações;
- verifica os pacotes já instalados e baixa apenas o que estiver ausente;
- configura CUPS, Avahi e Samba;
- adiciona o usuário aos grupos `lp`, `lpadmin` e `sambashare`, quando existirem;
- instala atalhos globais e no menu;
- valida dependências, testes e abertura da interface;
- preserva a versão anterior se a atualização falhar.

## Atualização rápida

```bash
wget -qO- https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash -s -- --fast
```

O modo rápido não executa APT quando o ambiente existente está íntegro. Ele reutiliza PySide6 e as demais dependências, reinstala somente o programa, executa os testes e mantém rollback.

## Reparo completo

```bash
wget -qO- https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/bootstrap.sh | bash -s -- --repair
```

O reparo reinstala as dependências do sistema, recria o ambiente Python e reconfigura serviços, atalhos e permissões.

## Central de saúde e correção

Abra **Central de saúde e correção** e clique em **Fazer diagnóstico completo**.

A versão 1.5.0 verifica de forma independente:

- dependências obrigatórias;
- serviço e agendador do CUPS;
- porta local 631;
- Avahi/mDNS;
- Samba;
- filas instaladas e filas desativadas;
- trabalhos pendentes;
- disponibilidade do PolicyKit;
- filtros, backends, PPDs e Ghostscript.

A tela mostra quatro informações por linha:

1. área afetada;
2. situação em linguagem clara (`OK`, `ATENÇÃO` ou `PROBLEMA`);
3. o que foi encontrado;
4. solução recomendada.

### Botões

- **Ver detalhes:** mostra a causa e a evidência técnica.
- **Corrigir selecionado:** executa somente a ação da linha escolhida.
- **Corrigir automaticamente:** aplica apenas ações consideradas seguras, como instalar componentes obrigatórios, ativar serviços e reiniciar o CUPS.
- Depois de cada reparo, o programa repete o diagnóstico e informa se o problema realmente desapareceu.

O programa não altera automaticamente credenciais, endereço de impressora ou escolha específica de driver. Esses casos mostram uma orientação objetiva para evitar quebrar filas funcionais.

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

Se o usuário acabou de ser adicionado ao grupo `lpadmin`, encerre e abra a sessão do Mint uma vez para aplicar a nova associação.

Log da instalação:

```bash
pkexec tail -n 200 /var/log/neri-printer-manager-install.log
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

A interface roda como usuário comum. Ações administrativas usam PolicyKit. O helper aceita somente pacotes, serviços e operações presentes em uma lista interna. Nomes de filas e URIs são validados e nenhum comando externo é executado com `shell=True`.

## Estado de homologação

A versão 1.5.0 reorganiza a correção de erros em uma central unificada, com ações limitadas, confirmação e verificação pós-reparo. A confirmação final de impressão ainda depende do modelo físico, driver disponível, políticas SMB, firewall e configuração do computador que compartilha a impressora.
