# Segurança

O Neri Printer Manager foi criado por **Cleiton Neri — Neri Infotech** para resolver problemas de impressão sem transformar a ferramenta em um administrador de infraestrutura.

## Princípio principal

O sistema pode diagnosticar e corrigir impressão no host local e na impressora selecionada.

Ele **não deve administrar a rede do ambiente**.

## Ações fora do escopo

O projeto não deve alterar automaticamente:

- Zentyal;
- firewall, `iptables`, `nftables` ou UFW;
- DNS;
- DHCP;
- gateway;
- rotas;
- VLAN;
- NetworkManager;
- netplan;
- interfaces de rede;
- roteadores, switches ou outros servidores;
- computadores remotos.

Também não deve executar:

- brute force;
- tentativa automática de senha;
- enumeração agressiva;
- varredura ampla desnecessária;
- comandos remotos via SSH, WinRM, RPC ou equivalentes.

## Modo portátil

A forma recomendada de uso é:

```bash
curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/run.sh | bash
```

O lançador baixa uma revisão portátil fixa, executa em arquivo temporário e remove esse arquivo ao terminar.

O código portátil trabalha com `umask 077`, usa locale previsível e limita URIs aos esquemas de impressão conhecidos.

## Alterações no CUPS

Antes de mudanças relevantes, o programa deve criar backup temporário dos arquivos afetados.

Após alteração em configuração global, deve executar:

```bash
cupsd -t
```

Se a validação falhar:

1. não reiniciar o CUPS com a configuração inválida;
2. restaurar o backup quando possível;
3. informar o erro ao técnico.

## Menor impacto possível

Uma falha em uma impressora não deve provocar alterações em todas as filas.

Exemplos:

- fila pausada → retomar somente aquela fila;
- permissão negada → corrigir somente a fila afetada;
- backend HP falhando → tratar HPLIP/HPCUPS;
- erro de Ghostscript → tratar Ghostscript somente quando confirmado;
- trabalho preso → cancelar o job selecionado, não todos por padrão.

## Rede

Quando o equipamento selecionado usa IP, o programa pode testar somente o destino necessário, por exemplo nas portas 631, 9100, 515 ou 445 conforme o protocolo.

Esse teste não autoriza escanear toda a rede nem alterar firewall ou roteamento.

## Credenciais

Senhas e tokens não devem aparecer em logs ou argumentos de processos sempre que for possível evitá-los.

A linha instalada 2.x usa higienização de URIs, campos de senha e cabeçalhos de autorização e possui helper PolicyKit com operações enumeradas.

## Linha instalada 2.x

A interface e a CLI rodam preferencialmente como usuário comum. Operações administrativas passam por um helper específico que não aceita comandos livres.

Pacotes, serviços e ações privilegiadas devem permanecer em listas conhecidas e validadas.

## Relato de vulnerabilidade

Não publique credenciais, senhas, tokens, logs completos de produção ou informações sensíveis de topologia em issue pública.

Ao relatar uma falha, informe apenas o necessário para reproduzir o problema com segurança.

## Regra de ouro

```text
diagnosticar
→ corrigir minimamente
→ validar
→ testar
```

Nunca:

```text
problema desconhecido
→ resetar tudo
```
