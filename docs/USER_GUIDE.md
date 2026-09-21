# Manual de uso

Este manual descreve o uso recomendado do **Neri Printer Manager Portable**, criado por **Cleiton Neri — Neri Infotech** para suporte rápido em Linux Mint.

## Executar

Abra o terminal como usuário normal e rode:

```bash
curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/run.sh | bash
```

Não precisa instalar o aplicativo. O lançador baixa uma revisão portátil fixa, executa em `/tmp` e remove os arquivos temporários ao terminar.

## Fluxo recomendado

1. Escolha a impressora.
2. Execute o diagnóstico.
3. Leia o problema identificado e a evidência.
4. Só aplique a correção quando o diagnóstico indicar uma ação segura.
5. Envie uma página de teste.
6. Confirme se o trabalho concluiu e se a folha saiu fisicamente.

O programa foi pensado para corrigir o mínimo necessário, não para resetar todo o ambiente de impressão.

## O que é verificado

O diagnóstico pode analisar:

- serviço e configuração do CUPS;
- estado da fila;
- permissão para imprimir;
- trabalhos pendentes;
- URI da impressora;
- PPD/driver;
- filtros do CUPS;
- Ghostscript;
- backend `hp`, `usb`, `ipp`, `socket`, `lpd` ou `smb`;
- HPLIP/HPCUPS;
- presença de impressora USB e serial;
- comunicação com o endereço específico de uma impressora de rede;
- mensagens recentes do `error_log`.

## Correção segura

Antes de alterações importantes, o programa cria backup temporário da configuração relevante. Quando `cupsd.conf` é alterado, a configuração precisa passar em:

```bash
cupsd -t
```

Se a validação falhar, o CUPS não deve ser reiniciado com a configuração quebrada. A rotina tenta restaurar o estado anterior.

## Impressora HP / HPLIP

Se o trabalho entra na fila, passa pelos filtros e o log registra algo como:

```text
Backend hp returned status 1 (failed)
```

isso indica uma falha no backend HPLIP. O sistema deve tratar esse cenário como problema de backend/driver, e não simplesmente como "trabalho retido".

## Impressoras USB iguais

Duas impressoras do mesmo modelo não são automaticamente duplicadas. Sempre que possível, o sistema usa o serial USB para distinguir os equipamentos.

## Rede

O modo portátil não administra a rede do ambiente.

Ele não altera firewall, DNS, DHCP, gateway, rota, VLAN, NetworkManager ou Zentyal. Quando uma impressora de rede precisa ser testada, a verificação é direcionada ao host daquela impressora e à porta de impressão correspondente.

## Fila de impressão

Evite apagar todos os trabalhos sem necessidade. O ideal é identificar e cancelar apenas o job problemático.

## "Inativa" no `lpstat`

Em muitos casos, uma impressora exibida como `inativa; habilitada` está apenas ociosa (`idle`). Isso não significa, por si só, que exista defeito.

## Quando o programa não consegue confirmar a solução

O programa deve diferenciar:

- **Problema resolvido:** há evidência de que o trabalho passou corretamente pelo CUPS/backend;
- **Correção aplicada, impressão não confirmada:** a parte lógica foi corrigida, mas é necessário validar a saída física.

## Linha instalada 2.x

A interface gráfica PySide6 e a CLI continuam no repositório para quem quiser uma instalação permanente. Para atendimento rápido em máquinas Linux Mint, prefira o modo portátil.

## Autor

**Cleiton Neri — Neri Infotech**  
GitHub: `Dexterrpk`
