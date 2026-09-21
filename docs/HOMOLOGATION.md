# Homologação para produção

Checklist do Neri Printer Manager, criado por **Cleiton Neri — Neri Infotech**.

Testes automatizados ajudam a evitar regressões, mas não substituem impressora real, cabo, USB, driver e folha física.

## Modo portátil

- [x] Executa sem instalação permanente do aplicativo.
- [x] Usa diretório temporário em `/tmp`.
- [x] Remove os próprios arquivos temporários ao sair.
- [x] O lançador aponta para uma revisão portátil fixa.
- [x] Parsing de filas usa locale previsível.
- [x] Mensagens como `pdftopdf ... exited with no errors` não viram filas falsas.
- [x] Não contém rotina para alterar firewall, DNS, DHCP, gateway, rota, VLAN ou NetworkManager.
- [x] Não contém rotina para administrar Zentyal.
- [x] Não executa brute force ou descoberta de senha.
- [x] Teste de rede é direcionado ao destino selecionado.

## Diagnóstico

- [ ] CUPS ativo.
- [ ] CUPS parado.
- [ ] `cupsd.conf` inválido.
- [ ] `MaxJobs` inválido.
- [ ] fila pausada.
- [ ] fila recusando trabalhos.
- [ ] `client-error-not-authorized`.
- [ ] trabalho pendente.
- [ ] `filter failed`.
- [ ] erro de Ghostscript.
- [ ] PPD ausente ou inválido.
- [ ] backend ausente.
- [ ] `Backend hp returned status 1`.
- [ ] URI inválida.
- [ ] PrintSpy rejeitando URI.
- [ ] USB não localizado.
- [ ] duas impressoras iguais com seriais diferentes.
- [ ] destino de rede indisponível.

## Correções

- [ ] correção altera somente a fila selecionada quando possível;
- [ ] backup é criado antes de alteração relevante;
- [ ] `cupsd -t` é executado antes de reiniciar após alteração global;
- [ ] configuração inválida dispara rollback;
- [ ] página de teste é enviada após reparo;
- [ ] erro antigo de log não é apresentado como falha atual sem evidência recente.

## Hardware para validar

Prioridade de testes reais:

- [ ] HP LaserJet P1102/P1102w;
- [ ] HP LaserJet MFP 135a;
- [ ] Brother HL-1200/1202;
- [ ] Zebra ZD220/ZD230;
- [ ] Bematech MP-4200 TH;
- [ ] Epson USB;
- [ ] impressora IPP;
- [ ] impressora JetDirect 9100;
- [ ] fila SMB Windows→Mint e Mint→Windows.

## Segurança

Confirmar manualmente que nenhuma correção:

- [ ] modifica Zentyal;
- [ ] abre ou fecha porta de firewall;
- [ ] muda DNS, DHCP ou gateway;
- [ ] altera rota ou interface de rede;
- [ ] reinicia NetworkManager;
- [ ] executa comando em outro host;
- [ ] remove filas não selecionadas sem confirmação;
- [ ] cancela todos os jobs sem confirmação.

## Critério de liberação

Uma versão deve ser considerada estável para uso amplo somente depois de passar pelos cenários aplicáveis em hardware real e não apresentar regressão crítica de CUPS, impressão ou segurança.

A prioridade é sempre **segurança e previsibilidade antes de quantidade de recursos**.
