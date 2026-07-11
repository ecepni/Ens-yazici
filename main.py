# -*- coding: utf-8 -*-
"""
ENS Yazici Araci - Android (Kivy)
Micros Simphony yazici/ag araci - mobil surum.
Sadece ag uzerinden calisan islevler: Ping, Port testi, Ag tarama,
Test fisi yazdirma, Kayitli yazicilar.
"""

import socket
import subprocess
import threading
import json
import os
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore

# ── Renkler (acik tema, PC uygulamasiyla uyumlu) ──
C_BG      = (0.957, 0.965, 0.980, 1)   # #F4F6FA
C_CARD    = (1, 1, 1, 1)               # beyaz
C_TEXT    = (0.118, 0.145, 0.188, 1)   # #1E2530
C_SUB     = (0.42, 0.46, 0.525, 1)     # #6B7686
C_BLUE    = (0.231, 0.435, 0.878, 1)   # #3B6FE0
C_GREEN   = (0.180, 0.620, 0.322, 1)   # #2E9E52
C_ORANGE  = (0.878, 0.478, 0.204, 1)   # #E07A34
C_TEAL    = (0.106, 0.647, 0.627, 1)   # #1BA5A0
C_RED     = (0.863, 0.231, 0.294, 1)   # #DC3B4B
C_PURPLE  = (0.486, 0.361, 0.839, 1)   # #7C5CD6

Window.clearcolor = C_BG

# Kayit dosyasi (telefon depolamasinda)
def _store_path():
    try:
        from android.storage import app_storage_path
        base = app_storage_path()
    except Exception:
        base = os.path.expanduser("~")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "ens_saved_printers.json")


# ══════════════════════════════════════════════════════════════
#  AG ISLEVLERI (arka planda calisir)
# ══════════════════════════════════════════════════════════════
def do_ping(ip):
    """Android'de ping komutu genelde /system/bin/ping."""
    try:
        r = subprocess.run(["ping", "-c", "3", "-W", "2", ip],
                           capture_output=True, text=True, timeout=15)
        return r.returncode == 0, r.stdout or r.stderr
    except Exception as e:
        return False, str(e)

def do_port_test(ip, port, timeout=4):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            code = s.connect_ex((ip, int(port)))
            return code == 0, code
    except Exception as e:
        return False, str(e)

def get_local_subnet():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3]) + ".", ip
    except Exception:
        return None, None

def port_open(ip, port=9100, timeout=0.4):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((ip, port)) == 0
    except Exception:
        return False

def send_test_receipt(ip):
    ESC = b"\x1b"; GS = b"\x1d"
    import datetime
    data = b""
    data += ESC + b"@"
    data += ESC + b"a" + b"\x01"
    data += ESC + b"!" + b"\x38"
    data += b"ENS TEST\n"
    data += ESC + b"!" + b"\x00"
    data += b"--------------------------------\n"
    data += ESC + b"a" + b"\x00"
    data += f"IP    : {ip}\n".encode("ascii", "replace")
    data += f"Tarih : {datetime.datetime.now():%Y-%m-%d %H:%M}\n".encode("ascii", "replace")
    data += b"Durum : Baglanti basarili\n"
    data += b"--------------------------------\n"
    data += ESC + b"a" + b"\x01"
    data += b"Yazici calisiyor :)\n\n\n\n"
    data += GS + b"V" + b"\x00"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((ip, 9100))
            s.sendall(data)
        return True, "Test fisi gonderildi."
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════
#  ORTAK WIDGET'LAR
# ══════════════════════════════════════════════════════════════
def make_btn(text, color, cb):
    b = Button(text=text, size_hint_y=None, height=dp(48),
               background_normal="", background_color=color,
               color=(1, 1, 1, 1), font_size="15sp", bold=True)
    b.bind(on_release=cb)
    return b

def make_input(hint, text=""):
    ti = TextInput(hint_text=hint, text=text, multiline=False,
                   size_hint_y=None, height=dp(46), font_size="16sp",
                   padding=[dp(10), dp(12)])
    return ti


class LogBox(ScrollView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.lbl = Label(text="", size_hint_y=None, halign="left", valign="top",
                         color=C_TEXT, font_size="13sp", markup=True,
                         padding=[dp(8), dp(8)])
        self.lbl.bind(texture_size=self._upd)
        self.add_widget(self.lbl)

    def _upd(self, *a):
        self.lbl.height = self.lbl.texture_size[1]
        self.lbl.text_size = (self.width - dp(16), None)
        self.scroll_y = 0

    def log(self, msg):
        def _a(*a):
            self.lbl.text += msg + "\n"
        Clock.schedule_once(_a, 0)

    def clear(self):
        self.lbl.text = ""


# ══════════════════════════════════════════════════════════════
#  SEKME 1: PING + PORT TESTI
# ══════════════════════════════════════════════════════════════
class PingTab(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kw)

        self.ip = make_input("IP adresi (orn. 192.168.1.100)", "192.168.1.100")
        self.port = make_input("Port (orn. 9100)", "9100")
        self.add_widget(self.ip)
        self.add_widget(self.port)

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(make_btn("Ping At", C_BLUE, self.ping))
        row.add_widget(make_btn("Port Test", C_ORANGE, self.porttest))
        self.add_widget(row)

        self.add_widget(make_btn("Temizle", C_SUB, lambda *a: self.log.clear()))

        self.log = LogBox()
        self.add_widget(self.log)

    def ping(self, *a):
        ip = self.ip.text.strip()
        if not ip:
            self.log.log("[b]IP girin.[/b]"); return
        self.log.log(f"Ping atiliyor: {ip} ...")
        def run():
            ok, out = do_ping(ip)
            self.log.log(out.strip())
            self.log.log(f"[b]{'CEVAP VAR' if ok else 'CEVAP YOK'}[/b]\n")
        threading.Thread(target=run, daemon=True).start()

    def porttest(self, *a):
        ip = self.ip.text.strip(); port = self.port.text.strip()
        if not ip or not port.isdigit():
            self.log.log("[b]Gecerli IP ve port girin.[/b]"); return
        self.log.log(f"Port test: {ip}:{port} ...")
        def run():
            ok, code = do_port_test(ip, port)
            self.log.log(f"[b]{ip}:{port} {'ACIK' if ok else 'KAPALI'}[/b]  (kod: {code})\n")
        threading.Thread(target=run, daemon=True).start()


# ══════════════════════════════════════════════════════════════
#  SEKME 2: AG TARAMA (yazici bulma, port 9100)
# ══════════════════════════════════════════════════════════════
class ScanTab(BoxLayout):
    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kw)
        self.app = app
        self.add_widget(make_btn("Agi Tara (yazicilari bul - port 9100)", C_PURPLE, self.scan))

        self.results = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        self.results.bind(minimum_height=self.results.setter("height"))
        sc = ScrollView(); sc.add_widget(self.results)
        self.add_widget(sc)

        self.log = LogBox(size_hint_y=0.4)
        self.add_widget(self.log)

    def scan(self, *a):
        self.results.clear_widgets()
        subnet, myip = get_local_subnet()
        if not subnet:
            self.log.log("[b]Ag bilgisi alinamadi. WiFi'a bagli misiniz?[/b]"); return
        self.log.log(f"Taraniyor: {subnet}1-254  (PC: {myip})")
        self.log.log("Lutfen bekleyin...")

        def run():
            found = []
            def chk(i):
                ip = f"{subnet}{i}"
                if port_open(ip, 9100, 0.4):
                    found.append(ip)
                    Clock.schedule_once(lambda dt, x=ip: self.add_result(x), 0)
            with ThreadPoolExecutor(max_workers=60) as pool:
                pool.map(chk, range(1, 255))
            self.log.log(f"[b]Tarama bitti. {len(found)} yazici bulundu.[/b]\n")
        threading.Thread(target=run, daemon=True).start()

    def add_result(self, ip):
        b = Button(text=f"{ip}  (port 9100 acik)", size_hint_y=None, height=dp(44),
                   background_normal="", background_color=C_CARD, color=C_TEXT,
                   font_size="14sp")
        b.bind(on_release=lambda *a: self.app.use_ip(ip))
        self.results.add_widget(b)


# ══════════════════════════════════════════════════════════════
#  SEKME 3: TEST FISI
# ══════════════════════════════════════════════════════════════
class ReceiptTab(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kw)
        self.ip = make_input("Yazici IP (test fisi gonderilecek)", "192.168.1.100")
        self.add_widget(self.ip)
        self.add_widget(make_btn("Test Fisi Yazdir", C_TEAL, self.send))
        info = Label(text="Yaziciya port 9100 uzerinden ESC/POS test fisi gonderir.\n"
                          "Fis cikiyorsa yazici calisiyor demektir.",
                     color=C_SUB, font_size="13sp", size_hint_y=None, height=dp(60))
        self.add_widget(info)
        self.log = LogBox()
        self.add_widget(self.log)

    def send(self, *a):
        ip = self.ip.text.strip()
        if not ip:
            self.log.log("[b]IP girin.[/b]"); return
        self.log.log(f"Test fisi gonderiliyor -> {ip}:9100 ...")
        def run():
            ok, msg = send_test_receipt(ip)
            self.log.log(f"[b]{'BASARILI' if ok else 'HATA'}[/b]: {msg}\n")
        threading.Thread(target=run, daemon=True).start()


# ══════════════════════════════════════════════════════════════
#  SEKME 4: KAYITLI YAZICILAR
# ══════════════════════════════════════════════════════════════
class SavedTab(BoxLayout):
    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kw)
        self.app = app
        self.store = JsonStore(_store_path())

        self.ip = make_input("IP", "")
        self.note = make_input("Not (orn. Mutfak yazicisi)", "")
        self.add_widget(self.ip)
        self.add_widget(self.note)
        self.add_widget(make_btn("Kaydet / Guncelle", C_GREEN, self.save))

        self.listbox = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        self.listbox.bind(minimum_height=self.listbox.setter("height"))
        sc = ScrollView(); sc.add_widget(self.listbox)
        self.add_widget(sc)

        self.refresh()

    def save(self, *a):
        ip = self.ip.text.strip()
        if not ip:
            return
        note = self.note.text.strip()
        self.store.put(ip, ip=ip, note=note)
        self.ip.text = ""; self.note.text = ""
        self.refresh()

    def delete(self, ip):
        if self.store.exists(ip):
            self.store.delete(ip)
        self.refresh()

    def refresh(self):
        self.listbox.clear_widgets()
        for key in self.store.keys():
            rec = self.store.get(key)
            note = rec.get("note", "")
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
            txt = f"{rec['ip']}" + (f"  -  {note}" if note else "")
            b = Button(text=txt, background_normal="", background_color=C_CARD,
                       color=C_TEXT, font_size="14sp")
            b.bind(on_release=lambda *a, x=rec['ip']: self.app.use_ip(x))
            d = Button(text="Sil", size_hint_x=None, width=dp(60),
                       background_normal="", background_color=C_RED,
                       color=(1, 1, 1, 1), font_size="13sp")
            d.bind(on_release=lambda *a, x=rec['ip']: self.delete(x))
            row.add_widget(b); row.add_widget(d)
            self.listbox.add_widget(row)


# ══════════════════════════════════════════════════════════════
#  ANA UYGULAMA
# ══════════════════════════════════════════════════════════════
class ENSApp(App):
    def build(self):
        self.title = "ENS Yazici Araci"
        root = BoxLayout(orientation="vertical")

        # Baslik seridi
        header = BoxLayout(size_hint_y=None, height=dp(52), padding=[dp(12), 0])
        header.add_widget(Label(text="[b]ENS[/b]  Yazici Araci", markup=True,
                                color=C_BLUE, font_size="20sp", halign="left"))
        root.add_widget(header)

        self.panel = TabbedPanel(do_default_tab=False, tab_width=dp(110))

        self.ping_tab = PingTab()
        self.scan_tab = ScanTab(self)
        self.receipt_tab = ReceiptTab()
        self.saved_tab = SavedTab(self)

        for title, w in [("Ping/Port", self.ping_tab), ("Ag Tara", self.scan_tab),
                         ("Test Fisi", self.receipt_tab), ("Kayitli", self.saved_tab)]:
            item = TabbedPanelItem(text=title)
            item.add_widget(w)
            self.panel.add_widget(item)

        root.add_widget(self.panel)

        # Android izinleri iste
        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET,
                                     Permission.ACCESS_NETWORK_STATE,
                                     Permission.ACCESS_WIFI_STATE])
            except Exception:
                pass
        return root

    def use_ip(self, ip):
        """Bulunan/kayitli bir IP'yi ilgili sekmelere doldur."""
        self.ping_tab.ip.text = ip
        self.receipt_tab.ip.text = ip
        self.saved_tab.ip.text = ip


if __name__ == "__main__":
    ENSApp().run()

