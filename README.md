# Neri Printer Manager

Ferramenta criada por **Cleiton Neri — Neri Infotech** para diagnosticar e corrigir problemas de impressoras no Linux Mint de forma simples, segura e objetiva.

O projeto nasceu de situações reais de suporte: impressora instalada que não imprime, fila retida, CUPS quebrado, erro de filtro, HPLIP, backend USB, SMB e falhas difíceis de identificar apenas pela interface do sistema.

A ideia central é simples:

**diagnosticar → explicar → corrigir somente o necessário → validar → testar**.

## Execução rápida — recomendada

Não precisa instalar o programa.

No terminal do Linux Mint, como usuário normal, execute:

```bash
curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/main/run.sh | bash
```

O `run.sh` é apenas um lançador curto. Ele baixa uma revisão portátil fixa e auditada, executa em área temporária e remove os arquivos temporários ao sair.

A revisão atualmente fixada pelo lançador é:

```text
4dabceec7e43c8e9f20e690fa8266f1e9b4c22d6
```

Para executar diretamente essa revisão imutável:

```bash
curl -fsSL https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/4dabceec7e43c8e9f20e690fa8266f1e9b4c22d6/portable/neri-printer-manager-portable.sh | bash
```

## O que a edição portátil faz

- lista as filas reais do CUPS;
- diagnostica CUPS, fila, permissão, URI, PPD, filtro, backend e comunicação;
- reconhece falhas comuns como `client-error-not-authorized`, `filter failed`, `Backend hp returned status 1`, erros de Ghostscript, URI inválida e trabalhos pendentes;
- trata HPLIP/HPCUPS quando há evidência de falha no backend HP;
- testa somente o destino selecionado em impressoras de rede;
- cria backup temporário antes de alterações relevantes;
- valida o CUPS com `cupsd -t` antes de reiniciar;
- faz rollback quando uma alteração de configuração não passa na validação;
- envia página de teste para confirmar o resultado;
- limpa os arquivos temporários do próprio programa ao encerrar.

As correções aplicadas ao CUPS, driver ou fila permanecem, naturalmente. O que desaparece é apenas o programa portátil baixado para aquela execução.

## Segurança

O Neri Printer Manager foi desenhado para cuidar de **impressão**, não para administrar a infraestrutura da rede.

O modo portátil não foi criado para alterar:

- Zentyal;
- firewall;
- DNS;
- DHCP;
- gateway;
- rotas;
- VLAN;
- NetworkManager;
- interfaces de rede;
- roteadores, switches ou outros servidores;
- computadores remotos.

Também não faz brute force, não tenta descobrir senhas e não executa varredura agressiva da rede.

Quando precisa verificar uma impressora de rede, o teste é direcionado somente ao endereço daquela impressora e às portas normais de impressão.

Consulte [SECURITY.md](SECURITY.md) para os limites completos.

## Filosofia de diagnóstico

O sistema não deve usar a abordagem:

```text
não sei o problema
→ reinstalar tudo
→ resetar tudo
```

A abordagem correta é:

```text
coletar evidências
→ identificar a causa
→ aplicar a menor correção possível
→ validar
→ testar impressão
```

Um exemplo real atendido pelo projeto foi uma HP LaserJet P1102w em que a fila e o filtro estavam funcionando, mas o log mostrava:

```text
Backend hp returned status 1 (failed)
```

O diagnóstico correto era falha no backend HPLIP, e não simplesmente "impressora retida".

## Versão com interface gráfica

O repositório também mantém a linha instalada com interface PySide6, CLI, PolicyKit, descoberta de rede e recursos adicionais. A versão empacotada atual dessa linha é **2.0.1**.

Ela continua disponível para ambientes em que uma instalação permanente faça sentido, mas para suporte rápido em máquinas Linux Mint a **edição portátil é a opção recomendada**.

## Documentação

- [Autoria](AUTHORS.md)
- [Manual de uso](docs/USER_GUIDE.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Solução de problemas](docs/TROUBLESHOOTING.md)
- [Homologação](docs/HOMOLOGATION.md)
- [Segurança](SECURITY.md)
- [Histórico de mudanças](CHANGELOG.md)

## Desenvolvimento

A base Python pode ser validada com:

```bash
bash scripts/validate.sh
```

Os testes automatizados cobrem validação de entradas, descoberta, segurança, parsing de saídas do CUPS e outras regressões conhecidas. A confirmação final de uma impressão ainda depende de hardware real, driver compatível e estado físico do equipamento.

## Autor

**Criado e mantido por Cleiton Neri — Neri Infotech**  
GitHub: `Dexterrpk`

Licenciado sob a [MIT License](LICENSE).
