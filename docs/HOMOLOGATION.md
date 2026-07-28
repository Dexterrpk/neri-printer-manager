# Homologação para produção

Esta lista registra o que exige sistema ou hardware real. Testes automatizados não
substituem a confirmação da folha impressa.

## Ambientes

- [ ] Linux Mint 21.x / Python 3.10, instalação limpa.
- [ ] Linux Mint 22.x / Python 3.12, instalação limpa.
- [ ] Atualização da versão 1.5.0 pelo modo rápido.
- [ ] Instalação por bootstrap com usuário administrador.
- [ ] Uso por conta comum que autoriza com outra conta administrativa.
- [ ] Instalação e remoção do `.deb` da arquitetura correspondente.

## Impressoras e origens

- [ ] USB detectada, instalada e testada com driver do fabricante.
- [ ] IPP/IPPS driverless instalada e com página física.
- [ ] IPP sem suporte completo cai para PPD/PCL/PostScript.
- [ ] JetDirect (`socket://IP:9100`) instalada e testada.
- [ ] LPD (`lpd://IP/fila`) instalada e testada.
- [ ] Mint→Mint enumera duas ou mais filas CUPS e instala a escolhida.
- [ ] Windows→Mint com SMB anônimo, se a política do servidor permitir.
- [ ] Windows→Mint com `usuario`, `PC\\usuario` e `DOMINIO\\usuario`.
- [ ] Mint→Windows com fila CUPS/Samba e conta Samba autenticada.
- [ ] Hostname DNS, `.local`, IP e NetBIOS.
- [ ] IPv6 para IPP, JetDirect e LPD em ambiente compatível.

## Operações

- [ ] Listar somente filas realmente instaladas.
- [ ] Mostrar `implicitclass://` apenas como publicação remota.
- [ ] Bloquear colisão de nome sem alterar a fila existente.
- [ ] Definir padrão, pausar, retomar e remover.
- [ ] Enviar página de teste e cancelar um trabalho.
- [ ] Compartilhar e descompartilhar somente a fila escolhida.
- [ ] Cancelar a janela PolicyKit sem travar a interface.
- [ ] Diagnosticar com CUPS ativo, parado e ausente.
- [ ] Gerar HTML e ZIP sem credenciais reconhecíveis.
- [ ] Criar backup em `$HOME` e mídia montada; validar SHA-256.

## Segurança e estabilidade

- [x] Nenhum uso de `shell=True` no código Python.
- [x] Helper com operações, pacotes e serviços enumerados.
- [x] Entradas malformadas e nomes de driver arbitrários rejeitados.
- [x] Senha SMB fora de toda linha de comando (`pkexec` e `lpadmin`).
- [x] Acesso irrestrito e administração remota explicitamente desativados no CUPS.
- [x] CI executa Ruff, mypy, compileall e pytest.
- [ ] Inspeção manual de `/proc` durante autenticação SMB.
- [ ] Teste de concorrência trocando o destino do backup durante a criação.
- [ ] Revisão do pacote com `lintian` na distribuição alvo.

## Critério de liberação

Uma release só recebe a marca `stable` quando todos os itens aplicáveis ao escopo
da release forem registrados em hardware real, a CI estiver verde e não houver
falha crítica aberta. Até lá, o classificador do pacote permanece **Beta**.
