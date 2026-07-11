# Homologação para produção

## Ambientes

- [ ] Linux Mint 21.x atualizado.
- [ ] Linux Mint 22.x atualizado.
- [ ] Usuário administrador.
- [ ] Usuário comum sem sudo direto.

## Impressoras

- [ ] USB detectada e instalada.
- [ ] IPP/IPPS detectada e instalada.
- [ ] JetDirect (`socket://IP:9100`) instalada.
- [ ] LPD instalada.
- [ ] Compartilhamento SMB vindo do Windows.
- [ ] Impressora compartilhada do Mint acessada pelo Windows.

## Operações

- [ ] Listar filas.
- [ ] Adicionar e remover fila.
- [ ] Pausar e retomar.
- [ ] Imprimir página de teste.
- [ ] Cancelar autenticação sem travamento.
- [ ] Executar diagnóstico com CUPS ativo.
- [ ] Executar diagnóstico com CUPS parado.
- [ ] Gerar relatório técnico.

## Segurança e estabilidade

- [ ] Nenhum uso de `shell=True`.
- [ ] Entradas malformadas rejeitadas.
- [ ] Interface não executada como root.
- [ ] Timeout de comandos confirmado.
- [ ] Logs sem senhas ou credenciais SMB.
- [ ] Testes e CI aprovados.

## Critério de liberação

A release só recebe a marca `stable` quando todos os itens obrigatórios forem executados em hardware real e não houver falhas críticas abertas.
