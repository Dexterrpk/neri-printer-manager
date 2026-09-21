# Solução de problemas

Guia rápido do **Neri Printer Manager**, criado por **Cleiton Neri — Neri Infotech**.

## Execução rápida

```bash
curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/run.sh | bash
```

## CUPS não inicia

Primeiro valide:

```bash
sudo cupsd -t
```

Se houver erro de configuração, não reinicie o serviço antes de corrigir ou restaurar o arquivo afetado.

Um caso real já encontrado foi:

```text
Missing integer value for MaxJobs
```

Isso significa que a diretiva `MaxJobs` estava sem valor inteiro válido.

## Impressora instala, mas o trabalho fica parado

Não trate "retido" como diagnóstico final. Verifique, nesta ordem:

- fila habilitada;
- fila aceitando trabalhos;
- permissão do usuário;
- filtros;
- backend;
- comunicação USB/rede;
- log do job.

## `client-error-not-authorized`

A fila ou política do CUPS está recusando a operação. Corrija somente a fila afetada e teste novamente.

## `Backend hp returned status 1 (failed)`

O trabalho chegou ao CUPS, mas o backend HPLIP falhou ao enviar os dados para a impressora.

Verifique:

- HPLIP;
- `printer-driver-hpcups`;
- backend `/usr/lib/cups/backend/hp`;
- `hp-probe`;
- `hp-plugin`, quando o modelo exigir;
- URI `hp:/usb/...`.

Esse erro não deve ser confundido com falha de `pdftopdf` quando o filtro terminou sem erro.

## `filter failed`

Verifique o log do job para identificar qual filtro falhou. Não aplique permissões globais em todos os filtros sem evidência.

Possíveis componentes envolvidos:

- `cups-filters`;
- Ghostscript;
- Foomatic;
- filtros específicos do fabricante;
- PPD.

## `PrintSpy: A URI do dispositivo é inválida`

Verifique se a fila está usando o backend esperado. Uma fila `hp:/usb/...` não deve ser convertida automaticamente para `printspy:`.

O PrintSpy deve ser tratado como backend específico, não como substituto universal dos demais.

## Impressora aparece como `inativa; habilitada`

Normalmente significa que está ociosa (`idle`). Não é, isoladamente, um erro.

## Existem duas impressoras do mesmo modelo

Compare o serial USB antes de remover qualquer fila. Duas HP P1102w, por exemplo, podem ser equipamentos físicos diferentes mesmo que os nomes das filas sejam parecidos.

## Surgiram filas estranhas como `or` ou `pdftopdf`

Isso é sinal de parsing incorreto da saída do CUPS, não de impressoras reais.

O código atual usa locale previsível e parser restrito a linhas reais de impressora para evitar esse tipo de erro.

## Impressora USB não aparece

Confira:

```bash
lsusb
lpinfo -v
```

Se a fila aponta para um serial específico, confirme que o mesmo serial aparece no dispositivo detectado.

## Impressora de rede não responde

Teste apenas o destino conhecido. Exemplos de portas normais de impressão:

- IPP: 631;
- JetDirect: 9100;
- LPD: 515;
- SMB: 445.

O Neri Printer Manager não deve escanear agressivamente a rede para resolver esse problema.

## Antes de reiniciar o CUPS

Sempre que houver alteração em configuração global:

```bash
sudo cupsd -t
```

Somente reinicie se a validação passar.

## Logs úteis

```bash
sudo tail -n 100 /var/log/cups/error_log
journalctl -u cups.service -n 100 --no-pager
```

Prefira relacionar mensagens ao ID do trabalho recente para evitar diagnosticar erro antigo como atual.

## Se o modo portátil fechar

Os arquivos temporários do programa são removidos. As correções que você autorizou no sistema de impressão permanecem.
