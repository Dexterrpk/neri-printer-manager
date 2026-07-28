# Arquitetura

## Componentes

```text
PySide6 (app.py) / CLI (cli.py)
            |
            v
serviços sem privilégio
core, host_locator, device_discovery, smart_install,
health, reports, sharing, backup
            |
            | operação administrativa enumerada + dados validados
            v
pkexec -> /usr/libexec/neri-printer-helper
            |
            v
CUPS / systemd / APT / Samba / arquivos de backup
```

A janela possui sete páginas, mas uma única classe `MainWindow`. `app.py` é o
único ponto de entrada gráfico; a instalação guiada usa diretamente
`HostPrinterLocator`, `RichDiscoveryService` e `SmartPrinterInstaller`.

## Concorrência da interface

Operações de rede e sistema são executadas por `QRunnable` no `QThreadPool`. Os
valores dos widgets são capturados na thread da interface antes da criação do
trabalho. O resultado volta por sinais Qt; workers não leem nem alteram widgets.

## Descoberta e instalação

`HostPrinterLocator` resolve o host, testa somente 631, 9100, 515, 445 e 139 e
produz objetos `LocatedPrinter`. Na porta 631 ele consulta `lpstat -h host:631 -e`
para diferenciar um servidor CUPS de uma impressora IPP direta.

`SmartPrinterInstaller` ordena as tentativas, evita colisão de nome, cria a fila,
retoma, verifica no CUPS e envia uma página de teste. Uma tentativa incompleta é
removida antes da seguinte.

Filas com URI `implicitclass://` são anúncios efêmeros do `cups-browsed`. Elas
podem ser mostradas na descoberta, mas não são contadas como instalações locais.

## PolicyKit e helper

A política autoriza somente o caminho fixo do helper. O helper aceita estas
famílias de operação:

- criar/remover/pausar/retomar fila e cancelar trabalho;
- instalar/reinstalar pacotes presentes no catálogo interno;
- ativar CUPS, Avahi ou Samba e reiniciar CUPS;
- reparar permissões somente de filtros/backends com cabeçalho executável válido;
- compartilhar/descompartilhar uma fila e configurar a conta Samba atual;
- criar backup em pasta permitida do usuário solicitante.

Uma segunda validação ocorre dentro desse processo. Caminhos de comandos são
absolutos, o ambiente é reduzido e o retorno é higienizado.

## Credenciais SMB

Na descoberta, `smbclient` recebe um arquivo temporário `0600`. Na instalação, a
senha passa por `stdin` do helper; somente dentro do processo privilegiado é
montada a URI exigida pelo backend SMB. O helper usa `python3-cups` para enviá-la
no pedido IPP local, sem argumento de subprocesso. A URI devolvida à interface não
contém *userinfo*.

## Diagnóstico

Cada probe gera um `HealthCheck` independente. Exceções isoladas viram aviso e
não interrompem os demais probes. `RepairService` traduz somente ações enumeradas
e repete a verificação correspondente depois da mudança.

## Empacotamento

O `.deb` inclui a aplicação e o PySide6 já instalados em um diretório privado.
Nenhum ambiente virtual é criado e nenhum comando `pip` é executado na máquina do
usuário durante a instalação. Por causa dos binários do PySide6, o pacote usa a
arquitetura real da máquina de build, nunca `Architecture: all`. O Samba e drivers
adicionais são recomendações; `cups-browsed` é apenas sugestão.
