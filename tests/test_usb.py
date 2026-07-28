from neri_printer_manager.usb import UsbPrinterService


def test_hplip_usb_uri_has_a_friendly_identity() -> None:
    assert UsbPrinterService._identity("hp:/usb/HP_LaserJet_Pro_M402?serial=ABC") == (
        "HP",
        "HP LaserJet Pro M402",
    )
