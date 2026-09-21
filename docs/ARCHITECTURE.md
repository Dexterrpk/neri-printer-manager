# Arquitetura

O Neri Printer Manager mantém duas linhas complementares:

1. **modo portátil**, recomendado para suporte rápido e sem instalação permanente;
2. **aplicação instalada 2.x**, com interface PySide6, CLI e helper PolicyKit.

Projeto criado e mantido por **Cleiton Neri — Neri Infotech**.

## Modo portátil

Fluxo principal:

```text
run.sh
  ↓
baixa revisão portátil fixa
  ↓
/tmp/neri-printer-manager.*
  ↓
diagnóstico local
  ↓
correção específica, se confirmada
  ↓
validação + página de teste
  ↓
limpeza dos arquivos temporários
```

O lançador `run.sh` não executa a versão mutável da `main`. Ele aponta para uma revisão portátil fixa, permitindo que o uso em máquinas de produção permaneça previsível.

## Escopo de segurança

O modo portátil trabalha no host local e na impressora selecionada. Ele não foi desenhado para administrar infraestrutura.

Não deve alterar:

- Zentyal;
- firewall;
- DNS ou DHCP;
- gateway ou roteamento;
- VLAN;
- NetworkManager;
- interfaces de rede;
- roteadores, switches ou hosts remotos.

Para equipamentos de rede, as sondagens são direcionadas somente ao destino selecionado e às portas normais de impressão.

## Motor de diagnóstico

A sequência preferida é:

```text
CUPS
 ↓
configuração
 ↓
fila
 ↓
permissão
 ↓
job
 ↓
URI / dispositivo
 ↓
PPD / driver
 ↓
filtro
 ↓
backend
 ↓
comunicação
```

O diagnóstico deve ser baseado em evidência. Um erro antigo no log não deve ser tratado como falha atual sem relação com um trabalho recente.

## Motor de reparo

Cada correção é específica para a condição encontrada. A arquitetura evita o padrão "reinstalar tudo".

Exemplos:

- fila pausada → habilitar somente aquela fila;
- permissão negada → corrigir somente a política da fila afetada;
- `Backend hp returned status 1` → verificar/reparar HPLIP/HPCUPS;
- Ghostscript com erro confirmado → reparar Ghostscript;
- configuração CUPS inválida → backup, correção localizada e validação.

## Proteção do CUPS

Alterações relevantes seguem a ideia de transação:

```text
estado atual
 ↓
backup
 ↓
alteração
 ↓
cupsd -t
 ↓
validou? ── não → rollback
   │
   sim
   ↓
reinício quando necessário
 ↓
teste
```

Isso evita reiniciar o serviço com um `cupsd.conf` quebrado.

## Parsing previsível

Comandos CUPS são interpretados com locale previsível:

```text
LC_ALL=C
LANG=C
LANGUAGE=C
```

Isso evita erros de parsing causados pela tradução da saída, como interpretar partes de mensagens (`or`, `pdftopdf`) como se fossem nomes de impressoras.

## Aplicação instalada 2.x

A linha gráfica continua usando:

```text
PySide6 / CLI
      ↓
serviços sem privilégio
      ↓
PolicyKit + helper enumerado
      ↓
CUPS / systemd / pacotes permitidos
```

O helper administrativo não aceita comandos livres. Operações privilegiadas são limitadas a um catálogo conhecido e os dados são validados antes da execução.

## Credenciais

Senhas não devem aparecer em linha de comando, log ou relatório. A base instalada inclui higienização de URIs, campos de senha, tokens e cabeçalhos de autorização.

## Princípio de projeto

A regra principal é:

```text
diagnosticar exatamente
→ corrigir minimamente
→ validar
→ testar
```

Nunca:

```text
não sei o problema
→ resetar tudo
```
