"""Inicialização segura com descoberta, instalação USB e compartilhamento."""
from __future__ import annotations
import ipaddress,re,socket,sys
from urllib.parse import urlparse
from PySide6.QtWidgets import QApplication,QHBoxLayout,QLabel,QMessageBox
from .device_discovery import RichDiscoveryService
from .enhanced_app import EnhancedWindow
from .logging_config import configure_logging
from .usb import UsbPrinterService

class SafeRichDiscoveryService(RichDiscoveryService):
    @staticmethod
    def _valid_dns_host(host:str)->bool:
        if not host or len(host)>253 or ' ' in host:return False
        labels=host.rstrip('.').split('.')
        if any(not x or len(x.encode('utf-8',errors='ignore'))>63 for x in labels):return False
        try:host.encode('idna')
        except UnicodeError:return False
        return True
    @classmethod
    def _host_address(cls,uri:str)->tuple[str,str]:
        try:p=urlparse(uri); host=p.hostname or ''
        except (ValueError,UnicodeError):return '',''
        if not host:return ('Este computador' if uri.lower().startswith('usb:') else '','')
        try:
            ipaddress.ip_address(host); return host,host
        except ValueError:pass
        if p.scheme.lower()=='dnssd' or not cls._valid_dns_host(host):return host[:240],''
        try:return host,socket.gethostbyname(host)
        except (OSError,UnicodeError,ValueError):return host[:240],''

class SafeEnhancedWindow(EnhancedWindow):
    def __init__(self,*args,**kwargs):
        self.usb_items=[]
        super().__init__(*args,**kwargs)

    def _tools(self):
        page,layout=super()._tools()
        usb_title=QLabel('Impressoras USB'); usb_title.setObjectName('title'); layout.insertWidget(2,usb_title)
        self.usb_status=QLabel('Conecte a impressora USB e clique em Procurar USB.'); self.usb_status.setObjectName('muted'); layout.insertWidget(3,self.usb_status)
        self.usb_table=self._table(['Impressora USB','Fabricante','Modelo','Driver recomendado']); layout.insertWidget(4,self.usb_table)
        row=QHBoxLayout(); row.addWidget(self._button('Procurar USB',self.discover_usb,True)); row.addWidget(self._button('Instalar USB selecionada',self.install_usb)); row.addStretch(); layout.insertLayout(5,row)
        return page

    def _sharing(self):
        page,layout=super()._sharing()
        row=QHBoxLayout(); row.addWidget(self._button('Compartilhar impressora selecionada',self.share_selected_printer,True)); row.addStretch(); layout.addLayout(row)
        note=QLabel('Selecione primeiro a fila em Minhas impressoras. O programa habilita o compartilhamento CUPS e prepara o Samba para acesso autenticado.'); note.setObjectName('muted'); note.setWordWrap(True); layout.addWidget(note)
        return page

    def discover_devices(self):
        self.tools_status.setText('Consultando filas locais, CUPS, IPP, Avahi e a rede local...')
        self._run(SafeRichDiscoveryService().discover,self._show_discovered)

    def discover_usb(self):
        self.usb_status.setText('Procurando dispositivos USB e comparando drivers instalados...')
        self._run(UsbPrinterService().detect,self._show_usb)

    def _show_usb(self,items):
        self.usb_items=items
        self._fill(self.usb_table,[(i.name,i.manufacturer or 'Não informado',i.model or 'Não informado',i.driver_description) for i in items])
        self.usb_status.setText(f'{len(items)} impressora(s) USB encontrada(s).' if items else 'Nenhuma impressora USB detectada pelo CUPS.')
        if items:self.usb_table.selectRow(0)

    def install_usb(self):
        row=self.usb_table.currentRow()
        if row<0 or row>=len(self.usb_items):QMessageBox.information(self,'Selecione','Escolha uma impressora USB.');return
        item=self.usb_items[row]
        self._run(lambda:UsbPrinterService().install(item),lambda result:(QMessageBox.information(self,'USB instalada',result),self.refresh_printers()))

    def share_selected_printer(self):
        name=self._selected_printer()
        if not name:return
        self._run(lambda:UsbPrinterService().share(name),lambda text:(QMessageBox.information(self,'Compartilhamento',text),self.refresh_sharing()))

def main()->int:
    configure_logging(); app=QApplication(sys.argv); app.setApplicationName('Neri Printer Manager')
    window=SafeEnhancedWindow(); window.show(); return app.exec()
if __name__=='__main__': raise SystemExit(main())
