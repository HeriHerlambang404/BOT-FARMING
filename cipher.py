#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Heri Cipher Tool - Aplikasi Enkripsi & Dekripsi berbasis CLI
=============================================================

Author      : Heri Herlambang
Versi       : 1.0.0
Deskripsi   : Aplikasi cipher interaktif dengan tiga algoritma:
              1. Caesar Cipher            (klasik, hanya untuk belajar)
              2. Heri Cipher              (Substitution-XOR, kunci berbasis
                                           nama "Heri Herlambang")
              3. AES-256-GCM              (modern, pustaka `cryptography`)

Cara pakai  : python heri_cipher.py
Dependensi  : pip install cryptography        (wajib untuk AES-256)
              pip install pyperclip           (opsional, untuk clipboard)

Catatan     : Caesar Cipher dan Heri Cipher dibuat untuk PEMBELAJARAN dan
              TIDAK aman untuk data rahasia sungguhan. Gunakan AES-256
              untuk kebutuhan enkripsi yang serius.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import platform
import shutil
import subprocess
from abc import ABC, abstractmethod
from getpass import getpass
from typing import Iterator, Optional

# ---------------------------------------------------------------------------
# Metadata modul
# ---------------------------------------------------------------------------
__author__ = "Heri Herlambang"
__version__ = "1.0.0"
__app_name__ = "Heri Cipher Tool"

# Impor pustaka `cryptography` bersifat opsional agar program tetap bisa
# berjalan (Caesar & Heri Cipher) walaupun pustaka belum terpasang.
try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    CRYPTO_AVAILABLE = False


# ---------------------------------------------------------------------------
# Exception khusus
# ---------------------------------------------------------------------------
class CipherError(Exception):
    """Error yang dilempar saat proses enkripsi/dekripsi gagal."""


# ---------------------------------------------------------------------------
# Kelas dasar (abstract) untuk semua cipher
# ---------------------------------------------------------------------------
class BaseCipher(ABC):
    """Antarmuka umum: setiap cipher wajib punya encrypt() dan decrypt()."""

    name: str = "Base"
    key_prompt: str = "Masukkan kunci"
    secret_key: bool = False  # True -> input kunci disembunyikan (getpass)

    @abstractmethod
    def encrypt(self, plaintext: str, key: str) -> str:
        """Mengubah teks asli menjadi ciphertext."""

    @abstractmethod
    def decrypt(self, ciphertext: str, key: str) -> str:
        """Mengembalikan ciphertext menjadi teks asli."""


# ---------------------------------------------------------------------------
# 1. Caesar Cipher
# ---------------------------------------------------------------------------
class CaesarCipher(BaseCipher):
    """Caesar Cipher: menggeser setiap huruf sejauh N posisi alfabet."""

    name = "Caesar Cipher"
    key_prompt = "Masukkan kunci geser (angka bulat, contoh: 3)"

    @staticmethod
    def _parse_key(key: str) -> int:
        """Validasi kunci: harus berupa bilangan bulat."""
        try:
            return int(key.strip())
        except ValueError:
            raise CipherError("Kunci Caesar harus berupa angka bulat.")

    @staticmethod
    def _shift(text: str, shift: int) -> str:
        """Geser huruf a-z / A-Z; karakter lain dibiarkan apa adanya."""
        hasil = []
        for ch in text:
            if "a" <= ch <= "z":
                hasil.append(chr((ord(ch) - ord("a") + shift) % 26 + ord("a")))
            elif "A" <= ch <= "Z":
                hasil.append(chr((ord(ch) - ord("A") + shift) % 26 + ord("A")))
            else:
                hasil.append(ch)  # angka, spasi, simbol tidak diubah
        return "".join(hasil)

    def encrypt(self, plaintext: str, key: str) -> str:
        return self._shift(plaintext, self._parse_key(key))

    def decrypt(self, ciphertext: str, key: str) -> str:
        # Dekripsi = geser ke arah sebaliknya
        return self._shift(ciphertext, -self._parse_key(key))


# ---------------------------------------------------------------------------
# 2. Heri Cipher (Substitution-XOR)
# ---------------------------------------------------------------------------
class HeriCipher(BaseCipher):
    """
    Cipher kustom "Heri Cipher" (Substitution-XOR) - dibuat oleh Heri Herlambang.

    Alur enkripsi (per byte teks UTF-8):
      1. Kunci dasar = "Heri Herlambang" + passphrase tambahan (opsional),
         diturunkan menjadi 32 byte lewat PBKDF2-HMAC-SHA256.
      2. Dari kunci itu dibuat S-Box (tabel substitusi 256 nilai teracak).
      3. Setiap byte: (byte + ciphertext_sebelumnya) -> substitusi lewat
         S-Box -> XOR dengan keystream. Rantai (chaining) membuat satu
         perubahan kecil menyebar ke byte-byte berikutnya.
      4. Hasil akhir dikodekan Base64 agar aman dicetak/disalin.

    PERINGATAN: dibuat untuk edukasi, bukan untuk pengamanan data sensitif.
    """

    name = 'Heri Cipher (Substitution-XOR)'
    key_prompt = "Passphrase tambahan (kosongkan untuk memakai kunci nama saja)"
    secret_key = True

    # Kunci berbasis nama pembuat
    NAME_KEY = "Heri Herlambang"
    _SALT = b"HeriCipher-v1"
    _ITERATIONS = 100_000

    def _derive_seed(self, passphrase: str) -> bytes:
        """Turunkan seed 32 byte dari nama + passphrase."""
        secret = f"{self.NAME_KEY}|{passphrase}".encode("utf-8")
        return hashlib.pbkdf2_hmac("sha256", secret, self._SALT, self._ITERATIONS, dklen=32)

    @staticmethod
    def _keystream(seed: bytes, label: bytes) -> Iterator[int]:
        """Generator keystream tak berhingga: SHA-256(seed | label | counter)."""
        counter = 0
        while True:
            blok = hashlib.sha256(seed + label + counter.to_bytes(8, "big")).digest()
            yield from blok  # iterasi bytes menghasilkan int 0-255
            counter += 1

    def _build_sbox(self, seed: bytes) -> tuple[list[int], list[int]]:
        """Bangun S-Box (permutasi 0-255) dengan Fisher-Yates + inversnya."""
        sbox = list(range(256))
        stream = self._keystream(seed, b"sbox")
        for i in range(255, 0, -1):
            # Ambil 2 byte -> angka acak 16-bit untuk memilih posisi tukar
            r = (next(stream) << 8) | next(stream)
            j = r % (i + 1)
            sbox[i], sbox[j] = sbox[j], sbox[i]
        inv = [0] * 256
        for idx, val in enumerate(sbox):
            inv[val] = idx  # tabel invers dipakai saat dekripsi
        return sbox, inv

    def encrypt(self, plaintext: str, key: str) -> str:
        seed = self._derive_seed(key)
        sbox, _ = self._build_sbox(seed)
        ks = self._keystream(seed, b"xor")

        out = bytearray()
        prev = 0  # ciphertext byte sebelumnya (untuk chaining)
        for b in plaintext.encode("utf-8"):
            c = sbox[(b + prev) & 0xFF] ^ next(ks)  # substitusi lalu XOR
            out.append(c)
            prev = c
        return base64.b64encode(bytes(out)).decode("ascii")

    def decrypt(self, ciphertext: str, key: str) -> str:
        try:
            data = base64.b64decode(ciphertext.strip(), validate=True)
        except (binascii.Error, ValueError):
            raise CipherError("Ciphertext bukan Base64 yang valid.")

        seed = self._derive_seed(key)
        _, inv = self._build_sbox(seed)
        ks = self._keystream(seed, b"xor")

        out = bytearray()
        prev = 0
        for c in data:
            # Balikkan urutan: XOR -> S-Box invers -> kurangi chaining
            b = (inv[c ^ next(ks)] - prev) & 0xFF
            out.append(b)
            prev = c
        try:
            return out.decode("utf-8")
        except UnicodeDecodeError:
            raise CipherError("Dekripsi gagal: passphrase salah atau data rusak.")


# ---------------------------------------------------------------------------
# 3. AES-256 (mode GCM)
# ---------------------------------------------------------------------------
class AES256Cipher(BaseCipher):
    """
    AES-256-GCM memakai pustaka `cryptography`.

    - Kunci 256-bit diturunkan dari password lewat Scrypt (KDF yang tahan
      brute-force) dengan salt acak.
    - GCM memberi kerahasiaan sekaligus autentikasi (deteksi data diubah).
    - Format keluaran: Base64( salt[16] + nonce[12] + ciphertext+tag ).
    """

    name = "AES-256 (GCM)"
    key_prompt = "Masukkan password"
    secret_key = True

    _SALT_LEN = 16
    _NONCE_LEN = 12
    _TAG_LEN = 16

    @staticmethod
    def _require_crypto() -> None:
        if not CRYPTO_AVAILABLE:
            raise CipherError(
                "Pustaka 'cryptography' belum terpasang.\n"
                "  Jalankan: pip install cryptography"
            )

    @staticmethod
    def _derive_key(password: str, salt: bytes) -> bytes:
        """Turunkan kunci 32 byte (=256 bit) dari password memakai Scrypt."""
        kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
        return kdf.derive(password.encode("utf-8"))

    def encrypt(self, plaintext: str, key: str) -> str:
        self._require_crypto()
        if not key:
            raise CipherError("Password AES tidak boleh kosong.")

        salt = os.urandom(self._SALT_LEN)    # salt acak baru tiap enkripsi
        nonce = os.urandom(self._NONCE_LEN)  # nonce acak, tidak boleh dipakai ulang
        aes_key = self._derive_key(key, salt)
        ct = AESGCM(aes_key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(salt + nonce + ct).decode("ascii")

    def decrypt(self, ciphertext: str, key: str) -> str:
        self._require_crypto()
        if not key:
            raise CipherError("Password AES tidak boleh kosong.")

        try:
            raw = base64.b64decode(ciphertext.strip(), validate=True)
        except (binascii.Error, ValueError):
            raise CipherError("Ciphertext bukan Base64 yang valid.")

        minimal = self._SALT_LEN + self._NONCE_LEN + self._TAG_LEN
        if len(raw) < minimal:
            raise CipherError("Ciphertext terlalu pendek / format tidak dikenali.")

        # Pisahkan kembali komponen: salt | nonce | ciphertext+tag
        salt = raw[: self._SALT_LEN]
        nonce = raw[self._SALT_LEN : self._SALT_LEN + self._NONCE_LEN]
        ct = raw[self._SALT_LEN + self._NONCE_LEN :]

        aes_key = self._derive_key(key, salt)
        try:
            return AESGCM(aes_key).decrypt(nonce, ct, None).decode("utf-8")
        except InvalidTag:
            raise CipherError("Dekripsi gagal: password salah atau data telah diubah.")
        except UnicodeDecodeError:
            raise CipherError("Hasil dekripsi bukan teks UTF-8 yang valid.")


# ---------------------------------------------------------------------------
# Utilitas output: clipboard & file
# ---------------------------------------------------------------------------
def copy_to_clipboard(text: str) -> bool:
    """Salin teks ke clipboard. Mengembalikan True bila berhasil."""
    # Cara 1: pyperclip (bila terpasang)
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return True
    except Exception:
        pass

    # Cara 2: tkinter (bawaan Python di banyak sistem desktop)
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()  # perlu agar isi clipboard tersimpan
        root.destroy()
        return True
    except Exception:
        pass

    # Cara 3: perintah bawaan OS (macOS / Linux / Termux)
    sistem = platform.system()
    if sistem == "Darwin":
        kandidat = [["pbcopy"]]
    elif sistem == "Windows":
        kandidat = []  # sudah ditangani cara 1 & 2
    else:
        kandidat = [
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["termux-clipboard-set"],
        ]
    for cmd in kandidat:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)
                return True
            except (subprocess.SubprocessError, OSError):
                continue
    return False


def save_to_file(text: str, path: str) -> None:
    """Simpan teks ke file (UTF-8). Melempar OSError bila gagal."""
    path = os.path.expanduser(path.strip())
    if not path:
        raise ValueError("Nama file tidak boleh kosong.")
    if os.path.exists(path):
        jawab = input(f"File '{path}' sudah ada. Timpa? (y/n): ").strip().lower()
        if jawab != "y":
            raise ValueError("Penyimpanan dibatalkan.")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Tampilan CLI
# ---------------------------------------------------------------------------
def print_banner() -> None:
    """Cetak banner program beserta identitas author."""
    lebar = 56
    garis = "=" * lebar
    print(garis)
    print(f"{__app_name__.upper():^{lebar}}")
    print(f"{'Enkripsi & Dekripsi Teks':^{lebar}}")
    print(garis)
    print(f"{'Author  : ' + __author__:^{lebar}}")
    print(f"{'Versi   : ' + __version__:^{lebar}}")
    print(garis)


def ask_choice(prompt: str, valid: set[str]) -> str:
    """Minta input pilihan menu sampai valid."""
    while True:
        pilihan = input(prompt).strip()
        if pilihan in valid:
            return pilihan
        print("  [!] Pilihan tidak valid, coba lagi.")


def ask_text(mode: str) -> str:
    """Minta teks dari pengguna (tidak boleh kosong)."""
    label = "teks asli" if mode == "encrypt" else "ciphertext"
    while True:
        teks = input(f"\nMasukkan {label}: ")
        if teks.strip():
            return teks
        print("  [!] Teks tidak boleh kosong.")


def ask_key(cipher: BaseCipher) -> str:
    """Minta kunci; disembunyikan bila cipher menandainya rahasia."""
    if cipher.secret_key:
        try:
            return getpass(f"{cipher.key_prompt}: ")
        except Exception:
            # Fallback bila terminal tidak mendukung getpass
            return input(f"{cipher.key_prompt}: ")
    return input(f"{cipher.key_prompt}: ")


def output_menu(result: str) -> None:
    """Menu setelah proses: salin ke clipboard / simpan ke file / kembali."""
    while True:
        print("\nOpsi hasil:")
        print("  1. Salin ke clipboard")
        print("  2. Simpan ke file")
        print("  0. Kembali ke menu utama")
        pilihan = ask_choice("Pilih [0-2]: ", {"0", "1", "2"})

        if pilihan == "1":
            if copy_to_clipboard(result):
                print("  [OK] Hasil disalin ke clipboard.")
            else:
                print("  [!] Clipboard tidak tersedia. Coba: pip install pyperclip")
        elif pilihan == "2":
            path = input("  Nama file tujuan (contoh: hasil.txt): ")
            try:
                save_to_file(result, path)
                print(f"  [OK] Hasil disimpan ke: {os.path.abspath(os.path.expanduser(path.strip()))}")
            except (OSError, ValueError) as e:
                print(f"  [!] Gagal menyimpan: {e}")
        else:
            return


# ---------------------------------------------------------------------------
# Alur utama
# ---------------------------------------------------------------------------
# Daftar algoritma yang tersedia (nomor menu -> objek cipher)
CIPHERS: dict[str, BaseCipher] = {
    "1": CaesarCipher(),
    "2": HeriCipher(),
    "3": AES256Cipher(),
}


def choose_cipher() -> Optional[BaseCipher]:
    """Tampilkan menu algoritma dan kembalikan cipher yang dipilih."""
    print("\nPilih algoritma:")
    for nomor, cipher in CIPHERS.items():
        print(f"  {nomor}. {cipher.name}")
    print("  0. Kembali")
    pilihan = ask_choice("Pilih [0-3]: ", {"0", *CIPHERS.keys()})
    return None if pilihan == "0" else CIPHERS[pilihan]


def run_process(mode: str) -> None:
    """Jalankan satu siklus enkripsi ('encrypt') atau dekripsi ('decrypt')."""
    cipher = choose_cipher()
    if cipher is None:
        return

    teks = ask_text(mode)
    kunci = ask_key(cipher)

    try:
        if mode == "encrypt":
            hasil = cipher.encrypt(teks, kunci)
        else:
            hasil = cipher.decrypt(teks, kunci)
    except CipherError as e:
        print(f"\n  [!] {e}")
        return
    except Exception as e:  # jaring pengaman untuk error tak terduga
        print(f"\n  [!] Terjadi kesalahan tak terduga: {e}")
        return

    judul = "HASIL ENKRIPSI" if mode == "encrypt" else "HASIL DEKRIPSI"
    print(f"\n--- {judul} ({cipher.name}) ---")
    print(hasil)
    print("-" * 40)
    output_menu(hasil)


def show_info() -> None:
    """Tampilkan informasi program."""
    print(f"\n{__app_name__} v{__version__}")
    print(f"Author: {__author__}")
    print("- Caesar Cipher : klasik, hanya untuk belajar.")
    print("- Heri Cipher   : Substitution-XOR berbasis nama 'Heri Herlambang'.")
    print("- AES-256 (GCM) : enkripsi modern, aman untuk penggunaan nyata.")
    if not CRYPTO_AVAILABLE:
        print("\n[!] Pustaka 'cryptography' belum terpasang -> AES-256 nonaktif.")
        print("    Jalankan: pip install cryptography")


def main() -> None:
    """Loop menu utama."""
    print_banner()
    while True:
        print("\nMENU UTAMA")
        print("  1. Enkripsi teks")
        print("  2. Dekripsi teks")
        print("  3. Tentang program")
        print("  0. Keluar")
        pilihan = ask_choice("Pilih [0-3]: ", {"0", "1", "2", "3"})

        if pilihan == "1":
            run_process("encrypt")
        elif pilihan == "2":
            run_process("decrypt")
        elif pilihan == "3":
            show_info()
        else:
            print(f"\nTerima kasih telah memakai {__app_name__} - {__author__}.")
            break


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        # Ctrl+C / Ctrl+D: keluar dengan rapi tanpa traceback
        print(f"\n\nProgram dihentikan. Sampai jumpa! - {__author__}")