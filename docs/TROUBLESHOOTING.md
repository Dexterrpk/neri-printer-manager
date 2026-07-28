# Solução de problemas

## O programa não localiza a impressora

- Confirme energia, cabo e a mesma rede/VLAN.
- Teste primeiro o IP para separar falha de DNS/NetBIOS.
- Em outro Mint, confirme que a fila foi marcada como compartilhada.
- Em Windows, confirme **Compartilhamento de Arquivos e Impressoras** e as portas
  139/445 no perfil de rede privado.
- Execute **Corrigir problemas → Fazer diagnóstico completo**.

## A porta 631 responde, mas aparece uma fila incorreta

Um computador com CUPS não é necessariamente uma impressora direta. A versão 2.0
enumera as filas remotas; se nenhuma for publicada, ela oferece `/ipp/print`
somente como tentativa para um equipamento IPP direto.

## Há impressoras que eu nunca instalei

Verifique:

```bash
lpstat -v
systemctl status cups-browsed.service
```

URIs `implicitclass://` são filas automáticas publicadas na rede. O Neri Printer
Manager as separa das filas locais. O instalador não adiciona `cups-browsed`, mas
não desativa uma escolha anterior do administrador.

## IPP Everywhere falhou

Alguns equipamentos abrem a porta 631 sem implementar todos os atributos
driverless. Instale os drivers do fabricante/HPLIP e tente novamente. O aplicativo
também testa PCL/PostScript e, se abertas, as portas 9100/515.

## SMB pede senha ou retorna acesso negado

- Tente `DOMINIO\\usuario` ou `PC\\usuario`.
- Confirme que o compartilhamento é do tipo impressora, não uma pasta.
- Em Mint→Windows, configure a senha Samba na tela **Compartilhamento**.
- Senha Samba e senha de login podem ser diferentes.
- Não coloque a senha diretamente na URI ou no terminal.

## PolicyKit não abre ou a operação é recusada

Confira:

```bash
command -v pkexec
ls -l /usr/libexec/neri-printer-helper
ls -l /usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy
```

Execute novamente o instalador se helper ou política estiverem ausentes. Um
usuário comum precisa informar uma conta administrativa válida na janela.

## Obter informações de suporte

```bash
neri-printer-cli health
neri-printer-cli list --all
neri-printer-cli support-bundle "$HOME"
```

Revise o ZIP antes de compartilhar. O gerador remove credenciais conhecidas, mas
nomes de host, usuário da fila e topologia da rede ainda podem ser sensíveis.

Log da instalação:

```bash
sudo tail -n 200 /var/log/neri-printer-manager-install.log
```
