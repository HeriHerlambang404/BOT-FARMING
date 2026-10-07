"""
Automasi farming Desa Malam (Builder Base) - Clash of Clans di Google Play Games PC

Install:
    pip install pyautogui opencv-python pillow pygetwindow

File gambar (PNG, crop kecil hanya tombolnya) taruh di folder yang sama dengan script ini:
    attack.png, find.png, pasukan.png, surrender.png, okay.png, home.png
    tiles.png  (hanya dibutuhkan kalau pakai mode yang memakai gambar tiles)

Mode deploy pasukan:
    1. Koordinat                     -> klik titik yang kamu simpan (paling stabil)
    2. Gambar tiles                  -> cari tiles.png di layar (bisa macet kalau tema map beda)
    3. Gambar tiles, fallback koord. -> coba tiles.png sebentar, kalau tidak ketemu klik koordinat

Berhenti darurat: gerakkan mouse ke pojok kiri atas layar, atau klik tombol Stop.
"""

import ctypes
import json
import os
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import pyautogui

try:
    import pygetwindow as gw
except Exception:
    gw = None

# Supaya koordinat tidak meleset kalau Windows pakai display scaling
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

pyautogui.FAILSAFE = True

# ---------------- PENGATURAN ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "coc_config.json")

CONFIDENCE = 0.8              # turunkan ke 0.7 kalau gambar sering tidak ketemu
POLL_INTERVAL = 0.3           # jeda singkat antar pengecekan layar (bukan jeda tetap antar langkah)
JUDUL_JENDELA = "Clash of Clans"
JUMLAH_KLIK_MAP = 1           # berapa kali klik deploy setelah pilih pasukan
TIMEOUT_TILES = 3             # detik mencari tiles.png sebelum pindah ke koordinat (mode hybrid saja)
JITTER = 4                    # geser acak klik (piksel) supaya tidak selalu persis di titik yang sama

MODE_KOORDINAT = "Koordinat"
MODE_GAMBAR = "Gambar tiles"
MODE_HYBRID = "Gambar tiles, fallback koordinat"

GAMBAR_WAJIB = ["attack.png", "find.png", "pasukan.png", "surrender.png", "okay.png", "home.png"]
# --------------------------------------------


def path_gambar(nama):
    return os.path.join(BASE_DIR, nama)


def cari(nama):
    """Cari gambar di layar. Return titik tengah atau None."""
    try:
        return pyautogui.locateCenterOnScreen(path_gambar(nama), confidence=CONFIDENCE)
    except FileNotFoundError:
        raise
    except Exception:
        return None  # gambar tidak ketemu


def klik_titik(x, y):
    pyautogui.click(x + random.randint(-JITTER, JITTER), y + random.randint(-JITTER, JITTER))


def jendela_game():
    """Cari jendela game. Return objek window atau None."""
    if not gw:
        return None
    try:
        for w in gw.getWindowsWithTitle(JUDUL_JENDELA):
            if w.width > 100 and w.height > 100 and not w.isMinimized:
                return w
    except Exception:
        pass
    return None


def muat_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "x" in data and "y" in data:
            return data
    except Exception:
        pass
    return None


def simpan_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


class BotApp:
    def __init__(self, root):
        self.root = root
        root.title("CoC Desa Malam Farming Bot")
        root.geometry("460x470")
        root.resizable(False, False)

        self.stop_event = threading.Event()
        self.thread = None
        self.log_queue = queue.Queue()
        self.config = muat_config()
        self.mode_aktif = MODE_KOORDINAT

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        # jumlah serangan
        baris = ttk.Frame(frame)
        baris.pack(fill="x")
        ttk.Label(baris, text="Jumlah serangan:").pack(side="left")
        self.jumlah = tk.IntVar(value=10)
        ttk.Spinbox(baris, from_=1, to=9999, textvariable=self.jumlah, width=8).pack(side="left", padx=8)

        # mode deploy
        baris2 = ttk.Frame(frame)
        baris2.pack(fill="x", pady=(8, 0))
        ttk.Label(baris2, text="Mode deploy:").pack(side="left")
        self.mode = tk.StringVar(value=MODE_KOORDINAT)
        ttk.Combobox(baris2, textvariable=self.mode, state="readonly", width=34,
                     values=[MODE_KOORDINAT, MODE_GAMBAR, MODE_HYBRID]).pack(side="left", padx=8)

        # koordinat
        baris3 = ttk.Frame(frame)
        baris3.pack(fill="x", pady=(8, 0))
        self.lbl_koord = tk.StringVar()
        ttk.Label(baris3, textvariable=self.lbl_koord).pack(side="left")
        self.btn_koord = ttk.Button(baris3, text="Ambil Koordinat", command=self.ambil_koordinat)
        self.btn_koord.pack(side="right")
        self.update_label_koord()

        # start / stop
        tombol = ttk.Frame(frame)
        tombol.pack(fill="x", pady=10)
        self.btn_start = ttk.Button(tombol, text="Start", command=self.start)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_stop = ttk.Button(tombol, text="Stop", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.status = tk.StringVar(value="Siap.")
        ttk.Label(frame, textvariable=self.status, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.log = tk.Text(frame, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=(8, 0))

        self.root.after(100, self.proses_log)
        self.root.protocol("WM_DELETE_WINDOW", self.tutup)

    # ---------- UI helper ----------
    def tulis(self, teks):
        self.log_queue.put(("log", teks))

    def set_status(self, teks):
        self.log_queue.put(("status", teks))

    def selesai_ui(self):
        self.log_queue.put(("done", ""))

    def proses_log(self):
        try:
            while True:
                jenis, teks = self.log_queue.get_nowait()
                if jenis == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", teks + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif jenis == "status":
                    self.status.set(teks)
                elif jenis == "done":
                    self.btn_start.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    self.btn_koord.configure(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self.proses_log)

    def update_label_koord(self):
        if self.config:
            jenis = "relatif jendela" if self.config.get("relatif") else "layar"
            self.lbl_koord.set(f"Titik deploy: ({self.config['x']}, {self.config['y']}) - {jenis}")
        else:
            self.lbl_koord.set("Titik deploy: belum diatur")

    # ---------- ambil koordinat ----------
    def ambil_koordinat(self):
        self.btn_koord.configure(state="disabled")
        self.tulis("Arahkan mouse ke titik deploy di dalam game...")
        self.hitung_mundur(4)

    def hitung_mundur(self, sisa):
        if sisa > 0:
            self.status.set(f"Arahkan mouse ke titik deploy... {sisa}")
            self.root.after(1000, self.hitung_mundur, sisa - 1)
            return

        pos = pyautogui.position()
        w = jendela_game()
        if w:
            self.config = {"x": pos.x - w.left, "y": pos.y - w.top, "relatif": True}
            self.tulis(f"Koordinat disimpan (relatif jendela): ({self.config['x']}, {self.config['y']})")
        else:
            self.config = {"x": pos.x, "y": pos.y, "relatif": False}
            self.tulis(f"Jendela game tidak terdeteksi. Koordinat layar disimpan: ({pos.x}, {pos.y})")
        simpan_config(self.config)
        self.update_label_koord()
        self.status.set("Siap.")
        self.btn_koord.configure(state="normal")

    # ---------- kontrol ----------
    def start(self):
        try:
            total = int(self.jumlah.get())
            if total < 1:
                raise ValueError
        except Exception:
            messagebox.showerror("Error", "Jumlah serangan harus angka minimal 1.")
            return

        mode = self.mode.get()
        wajib = list(GAMBAR_WAJIB)
        if mode in (MODE_GAMBAR, MODE_HYBRID):
            wajib.append("tiles.png")
        hilang = [n for n in wajib if not os.path.exists(path_gambar(n))]
        if hilang:
            messagebox.showerror("File gambar kurang", "Tidak ditemukan:\n" + "\n".join(hilang))
            return

        if mode in (MODE_KOORDINAT, MODE_HYBRID) and not self.config:
            messagebox.showerror("Koordinat belum diatur",
                                 "Klik 'Ambil Koordinat' dulu untuk menyimpan titik deploy.")
            return

        self.mode_aktif = mode
        self.stop_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_koord.configure(state="disabled")
        self.thread = threading.Thread(target=self.jalankan, args=(total,), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.set_status("Menghentikan...")

    def tutup(self):
        self.stop_event.set()
        self.root.destroy()

    # ---------- logika automasi ----------
    def tunggu(self, nama, timeout=None):
        """Tunggu sampai gambar ketemu. Tanpa timeout = menunggu terus sampai ketemu atau di-stop."""
        self.tulis(f"  mencari {nama} ...")
        mulai = time.time()
        while not self.stop_event.is_set():
            pos = cari(nama)
            if pos:
                return pos
            if timeout is not None and time.time() - mulai >= timeout:
                return None
            time.sleep(POLL_INTERVAL)
        return None

    def tunggu_dan_klik(self, nama):
        pos = self.tunggu(nama)
        if pos is None:
            return False
        klik_titik(pos.x, pos.y)
        self.tulis(f"  klik {nama}")
        return True

    def klik_koordinat(self):
        x, y = self.config["x"], self.config["y"]
        if self.config.get("relatif"):
            w = jendela_game()
            if not w:
                self.tulis("  jendela game tidak ketemu, koordinat tidak bisa dipakai")
                return False
            x += w.left
            y += w.top
        klik_titik(x, y)
        self.tulis(f"  klik koordinat ({x}, {y})")
        return True

    def deploy(self):
        mode = self.mode_aktif
        for _ in range(JUMLAH_KLIK_MAP):
            if self.stop_event.is_set():
                return False

            if mode == MODE_KOORDINAT:
                ok = self.klik_koordinat()

            elif mode == MODE_GAMBAR:
                ok = self.tunggu_dan_klik("tiles.png")

            else:  # hybrid
                pos = self.tunggu("tiles.png", timeout=TIMEOUT_TILES)
                if pos:
                    klik_titik(pos.x, pos.y)
                    self.tulis("  klik tiles.png")
                    ok = True
                elif self.stop_event.is_set():
                    ok = False
                else:
                    self.tulis("  tiles.png tidak ketemu, pakai koordinat")
                    ok = self.klik_koordinat()

            if not ok:
                return False
        return True

    def satu_putaran(self):
        if not self.tunggu_dan_klik("attack.png"):
            return False
        if not self.tunggu_dan_klik("find.png"):
            return False
        if not self.tunggu_dan_klik("pasukan.png"):
            return False
        if not self.deploy():
            return False
        if not self.tunggu_dan_klik("surrender.png"):
            return False
        if not self.tunggu_dan_klik("okay.png"):
            return False
        if not self.tunggu_dan_klik("home.png"):
            return False
        return True

    def jalankan(self, total):
        try:
            for i in range(1, total + 1):
                if self.stop_event.is_set():
                    break
                self.set_status(f"Putaran {i} / {total}")
                self.tulis(f"=== Putaran {i} / {total} ===")
                if not self.satu_putaran():
                    break
            else:
                self.set_status("Selesai semua putaran.")
                self.tulis("Selesai.")
                return
            self.set_status("Dihentikan.")
            self.tulis("Dihentikan.")
        except pyautogui.FailSafeException:
            self.set_status("Berhenti (failsafe).")
            self.tulis("Failsafe aktif: mouse di pojok kiri atas.")
        except Exception as e:
            self.set_status("Error.")
            self.tulis(f"Error: {e}")
        finally:
            self.selesai_ui()


if __name__ == "__main__":
    root = tk.Tk()
    BotApp(root)
    root.mainloop()