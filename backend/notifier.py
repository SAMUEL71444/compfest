"""
notifier.py — SAPA
Notifikasi Telegram untuk mode Live (webcam). OPT-IN penuh.

Tujuan: saat webcam mendeteksi JATUH atau BUTUH BANTUAN, HP staf menerima
notifikasi Telegram (foto situasi dengan wajah diblur + keterangan) walau layar
mati. Staf buka notif → lihat foto → tahu siapa & di mana → menuju lokasi.

Prinsip desain:
- OPT-IN: aktif HANYA bila SAPA_TELEGRAM_TOKEN + SAPA_TELEGRAM_CHAT_ID terisi.
  Tanpa itu → no-op total. Aplikasi tetap jalan normal tanpa konfigurasi apa pun.
- TANPA DEPENDENSI BARU: pakai stdlib `urllib` saja (bukan requests).
- ANTI-SPAM: cooldown per (track_id, tipe) — default 20 dtk.
- NON-BLOCKING: kirim di thread terpisah dengan timeout pendek, tidak memblokir
  loop WebSocket.
- DUAL-BOT opsional: event JATUH bisa diarahkan ke bot/chat "darurat" terpisah
  agar staf bisa menyetel nada/getar berbeda di HP.

Semua env var bersifat opsional — lihat kirim_kejadian().
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
import urllib.request
import uuid

logger = logging.getLogger(__name__)

# ── Konfigurasi via env (semua opsional) ──────────────────────────────────────
TOKEN            = os.getenv("SAPA_TELEGRAM_TOKEN", "").strip()
CHAT_ID          = os.getenv("SAPA_TELEGRAM_CHAT_ID", "").strip()
TOKEN_DARURAT    = os.getenv("SAPA_TELEGRAM_TOKEN_DARURAT", "").strip()
CHAT_ID_DARURAT  = os.getenv("SAPA_TELEGRAM_CHAT_ID_DARURAT", "").strip()
COOLDOWN_DETIK   = float(os.getenv("SAPA_NOTIF_COOLDOWN", "20"))
TIMEOUT_KIRIM    = float(os.getenv("SAPA_NOTIF_TIMEOUT", "8"))

# Label + emoji per tipe kejadian untuk caption.
_LABEL = {
    "jatuh":         "🚨 JATUH TERDETEKSI",
    "butuh_bantuan": "🙋 BUTUH BANTUAN",
}
_LABEL_AKTIF = "🙋‍♂️ ANGKAT TANGAN — MEMINTA BANTUAN"

# ── State cooldown per (track_id, tipe) ───────────────────────────────────────
_cooldown: dict[tuple, float] = {}
_cooldown_lock = threading.Lock()

# Mapping kejadian → pesan Telegram terkirim, agar bisa dihapus saat pengawas
# menandai alarm palsu (human-in-the-loop). Kunci = kunci_kejadian(event),
# nilai = daftar (token, chat_id, message_id) — daftar karena satu kejadian bisa
# dikirim ke >1 chat (bot utama + bot darurat).
_pesan_terkirim: dict[str, list[dict]] = {}
_pesan_lock = threading.Lock()

# Kejadian yang sudah ditangani lewat tombol Telegram (agar tidak dihitung ganda).
_sudah_ditangani: set[str] = set()

# Thread polling getUpdates (feedback tombol dari Telegram).
_poll_thread = None
_poll_offset = 0
_poll_lock = threading.Lock()


def kunci_kejadian(event: dict) -> str:
    """
    ID kejadian yang STABIL & KONSISTEN dengan eventId() di frontend
    (dedupeEvents.js): `track_id__tipe__round(t0,2)`. Dipakai untuk memasangkan
    permintaan "batalkan" dari UI dengan pesan Telegram yang sudah dikirim.
    """
    t0 = event.get("t0", 0) or 0
    return f"{event.get('track_id')}__{event.get('tipe')}__{round(float(t0), 2)}"


def aktif() -> bool:
    """True bila notifikasi utama terkonfigurasi (token + chat_id terisi)."""
    return bool(TOKEN and CHAT_ID)


def _target(tipe: str) -> tuple[str, str]:
    """
    Pilih (token, chat_id) tujuan. Event 'jatuh' diarahkan ke bot darurat bila
    dikonfigurasi; selain itu memakai bot utama.
    """
    if tipe == "jatuh" and TOKEN_DARURAT and CHAT_ID_DARURAT:
        return TOKEN_DARURAT, CHAT_ID_DARURAT
    return TOKEN, CHAT_ID


def _lolos_cooldown(track_id, tipe: str) -> bool:
    """True bila kejadian ini boleh dikirim (belum dalam masa cooldown)."""
    key = (track_id, tipe)
    now = time.monotonic()
    with _cooldown_lock:
        terakhir = _cooldown.get(key, 0.0)
        if now - terakhir < COOLDOWN_DETIK:
            return False
        _cooldown[key] = now
    return True


def _bangun_caption(event: dict) -> str:
    tipe = event.get("tipe", "")
    aktif_sinyal = event.get("sinyal") == "aktif"
    if tipe == "butuh_bantuan" and aktif_sinyal:
        judul = _LABEL_AKTIF
    else:
        judul = _LABEL.get(tipe, tipe.upper())

    baris = [judul, f"Orang #{event.get('track_id', '?')}"]

    t0 = event.get("t0")
    if t0 is not None:
        m, s = divmod(int(t0), 60)
        baris.append(f"Waktu: {m}:{s:02d} (sejak sesi live dimulai)")

    skor = event.get("skor")
    if skor is not None:
        baris.append(f"Keyakinan: {round(float(skor) * 100)}%")

    baris.append("")
    baris.append("AI menandai, manusia memutuskan — mohon verifikasi langsung.")
    return "\n".join(baris)


# ── HTTP multipart (stdlib) ───────────────────────────────────────────────────
def _post_multipart(url: str, fields: dict, file_field: str | None = None,
                    file_bytes: bytes | None = None, file_name: str = "foto.jpg") -> bool:
    """
    POST multipart/form-data memakai urllib. Kembalikan True bila HTTP 200.
    Dipakai untuk sendPhoto (dengan file) maupun sendMessage (tanpa file).
    """
    boundary = uuid.uuid4().hex
    crlf = b"\r\n"
    body = io.BytesIO()

    for nama, nilai in fields.items():
        body.write(b"--" + boundary.encode() + crlf)
        body.write(f'Content-Disposition: form-data; name="{nama}"'.encode() + crlf + crlf)
        body.write(str(nilai).encode("utf-8") + crlf)

    if file_field and file_bytes is not None:
        body.write(b"--" + boundary.encode() + crlf)
        body.write(
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"'.encode()
            + crlf
        )
        body.write(b"Content-Type: image/jpeg" + crlf + crlf)
        body.write(file_bytes + crlf)

    body.write(b"--" + boundary.encode() + b"--" + crlf)
    data = body.getvalue()

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_KIRIM) as resp:
            if resp.status != 200:
                return None
            import json as _json
            body_resp = _json.loads(resp.read().decode("utf-8", "replace"))
            # message_id ada di result.message_id untuk sendPhoto/sendMessage.
            return body_resp.get("result", {}).get("message_id")
    except Exception as e:
        logger.warning(f"[notifier] Gagal kirim ke Telegram: {e}")
        return None


def _keyboard_ditangani(kunci: str) -> str:
    """Inline keyboard JSON dengan satu tombol 'Ditangani' membawa kunci kejadian."""
    import json as _json
    return _json.dumps({
        "inline_keyboard": [[
            {"text": "✓ Saya Tangani", "callback_data": f"tangani::{kunci}"}
        ]]
    })


def _kirim_sync(event: dict, foto: bytes | None):
    """Pengiriman sinkron — dipanggil di thread terpisah oleh kirim_kejadian()."""
    token, chat_id = _target(event.get("tipe", ""))
    if not (token and chat_id):
        return

    caption = _bangun_caption(event)
    kunci = kunci_kejadian(event)
    keyboard = _keyboard_ditangani(kunci)

    message_id = None
    if foto:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        message_id = _post_multipart(
            url,
            fields={"chat_id": chat_id, "caption": caption, "reply_markup": keyboard},
            file_field="photo", file_bytes=foto, file_name="kejadian.jpg",
        )

    # Fallback ke pesan teks bila foto tidak ada / gagal terkirim.
    if message_id is None:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        message_id = _post_multipart(
            url, fields={"chat_id": chat_id, "text": caption, "reply_markup": keyboard}
        )

    # Catat pesan terkirim agar bisa dihapus (alarm palsu) atau di-edit (ditangani).
    if message_id is not None:
        with _pesan_lock:
            _pesan_terkirim.setdefault(kunci, []).append({
                "token": token, "chat_id": chat_id,
                "message_id": message_id, "caption": caption,
                "punya_foto": bool(foto),
            })
        # Pastikan polling feedback tombol berjalan.
        _mulai_polling()


def _hapus_sync(kunci: str):
    """Hapus semua pesan Telegram yang terkait satu kejadian. Sinkron."""
    with _pesan_lock:
        entri = _pesan_terkirim.pop(kunci, [])
    for e in entri:
        url = f"https://api.telegram.org/bot{e['token']}/deleteMessage"
        # deleteMessage dibatasi 48 jam oleh Telegram; alarm palsu selalu jauh
        # di bawah itu, jadi aman.
        ok = _post_multipart(url, fields={"chat_id": e["chat_id"], "message_id": e["message_id"]})
        if ok is None:
            logger.debug(f"[notifier] Gagal hapus pesan {e['message_id']} (mungkin sudah dihapus).")


def kirim_kejadian(event: dict, foto: bytes | None = None):
    """
    Kirim notifikasi untuk sebuah kejadian. NON-BLOCKING & aman dipanggil dari
    konteks async (menjalankan I/O di thread daemon terpisah).

    - No-op bila notifikasi tidak terkonfigurasi.
    - Menerapkan cooldown per (track_id, tipe).
    - `foto`: JPEG bytes (wajah sudah diblur) atau None (kirim teks saja).
    """
    if not aktif():
        return
    if not _lolos_cooldown(event.get("track_id"), event.get("tipe", "")):
        return

    t = threading.Thread(target=_kirim_sync, args=(event, foto), daemon=True)
    t.start()


def batalkan_kejadian(event: dict):
    """
    Hapus notifikasi Telegram untuk sebuah kejadian — dipanggil saat pengawas
    menandainya "alarm palsu" di UI (human-in-the-loop). NON-BLOCKING & aman
    dipanggil dari konteks async.

    No-op bila notifikasi tidak terkonfigurasi atau kejadian tidak punya pesan
    tercatat (mis. sudah lewat cooldown / tidak pernah terkirim).
    """
    if not aktif():
        return
    kunci = kunci_kejadian(event)
    with _pesan_lock:
        ada = kunci in _pesan_terkirim
    if not ada:
        return

    t = threading.Thread(target=_hapus_sync, args=(kunci,), daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK TOMBOL DARI TELEGRAM (polling getUpdates)
#
# Staf lapangan menekan "✓ Saya Tangani" di chat → Telegram kirim callback_query.
# Kita polling getUpdates (tidak perlu domain publik / webhook, jalan di lokal),
# lalu: answerCallbackQuery + editMessageCaption jadi "Ditangani oleh [Nama]" +
# catat ke statistik (siapa + waktu respons).
#
# Callback pencatatan diinjeksikan dari luar via set_pencatat_ditangani() agar
# notifier tetap tidak bergantung langsung ke modul statistik (loose coupling).
# ══════════════════════════════════════════════════════════════════════════════

_pencatat_ditangani = None  # fungsi(kunci, nama_staf) → dipanggil saat tombol ditekan


def set_pencatat_ditangani(fn):
    """Daftarkan callback yang dipanggil saat kejadian ditangani via Telegram."""
    global _pencatat_ditangani
    _pencatat_ditangani = fn


def _api_get(token: str, method: str, params: dict) -> dict | None:
    """GET sederhana ke Telegram API (untuk getUpdates)."""
    import json as _json
    import urllib.parse
    url = f"https://api.telegram.org/bot{token}/{method}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=35) as resp:
            if resp.status != 200:
                return None
            return _json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:
        logger.debug(f"[notifier] getUpdates gagal: {e}")
        return None


def _cari_entri(kunci: str, message_id: int):
    """Cari entri pesan terkirim yang cocok dengan kunci + message_id."""
    with _pesan_lock:
        for e in _pesan_terkirim.get(kunci, []):
            if e["message_id"] == message_id:
                return e
    return None


def _proses_callback(cb: dict):
    """Tangani satu callback_query dari staf menekan tombol Ditangani."""
    data = cb.get("data", "")
    if not data.startswith("tangani::"):
        return
    kunci = data.split("::", 1)[1]

    dari = cb.get("from", {})
    nama = (dari.get("first_name", "") + " " + dari.get("last_name", "")).strip() \
        or dari.get("username") or "Staf"

    msg = cb.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")
    cb_id = cb.get("id")

    # Bot utama dipakai untuk menjawab (token utama). Untuk bot darurat, callback
    # datang lewat update bot darurat sendiri — ditangani di loop token terkait.
    entri = _cari_entri(kunci, message_id)
    token = entri["token"] if entri else TOKEN

    # 1. Akui penekanan (hilangkan loading di HP staf).
    if cb_id:
        _post_multipart(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            fields={"callback_query_id": cb_id, "text": "Terima kasih, tercatat."},
        )

    # 2. Catat ke statistik (idempoten — penekanan berulang tidak dihitung ganda).
    with _pesan_lock:
        sudah = kunci in _sudah_ditangani
        _sudah_ditangani.add(kunci)
    if not sudah and _pencatat_ditangani:
        try:
            _pencatat_ditangani(kunci, nama)
        except Exception as e:
            logger.debug(f"[notifier] pencatat_ditangani gagal: {e}")

    # 3. Edit caption jadi status final + hilangkan tombol.
    caption_baru = None
    if entri:
        caption_baru = entri["caption"] + f"\n\n✅ Ditangani oleh {nama}"
    else:
        caption_baru = f"✅ Ditangani oleh {nama}"

    if chat_id is not None and message_id is not None:
        metode = "editMessageCaption" if (entri and entri.get("punya_foto")) else "editMessageText"
        field_teks = "caption" if metode == "editMessageCaption" else "text"
        _post_multipart(
            f"https://api.telegram.org/bot{token}/{metode}",
            fields={
                "chat_id": chat_id, "message_id": message_id,
                field_teks: caption_baru,
                "reply_markup": '{"inline_keyboard":[]}',  # buang tombol
            },
        )


def _loop_polling():
    """Loop long-polling getUpdates untuk bot utama (+ darurat bila beda token)."""
    global _poll_offset
    # Kumpulkan token unik yang perlu di-poll.
    tokens = [TOKEN]
    if TOKEN_DARURAT and TOKEN_DARURAT != TOKEN:
        tokens.append(TOKEN_DARURAT)

    logger.info("[notifier] Polling feedback tombol Telegram dimulai.")
    offsets = {t: 0 for t in tokens}

    while True:
        for token in tokens:
            hasil = _api_get(token, "getUpdates", {
                "offset": offsets[token], "timeout": 25,
                "allowed_updates": '["callback_query"]',
            })
            if not hasil or not hasil.get("ok"):
                continue
            for upd in hasil.get("result", []):
                offsets[token] = upd["update_id"] + 1
                cb = upd.get("callback_query")
                if cb:
                    try:
                        _proses_callback(cb)
                    except Exception as e:
                        logger.debug(f"[notifier] proses callback gagal: {e}")
        time.sleep(1)


def _mulai_polling():
    """Mulai thread polling sekali saja (idempoten)."""
    global _poll_thread
    if not aktif():
        return
    with _poll_lock:
        if _poll_thread is not None and _poll_thread.is_alive():
            return
        _poll_thread = threading.Thread(target=_loop_polling, daemon=True)
        _poll_thread.start()
