"""
Uji wiring FastAPI mode produksi SAPA.

cv2 / torch / ultralytics distub — yang diuji di sini adalah pendaftaran route,
gerbang 503, dan validasi profil lewat HTTP, bukan inferensi.
"""
import sys, types, tempfile, os

# ── Stub modul berat ──────────────────────────────────────────────────────────
class _Any:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return _Any()
    def __getattr__(self, n): return _Any
    def __iter__(self): return iter(())

def _stub(nama, anak=()):
    m = types.ModuleType(nama)
    m.__getattr__ = lambda n: _Any
    sys.modules[nama] = m
    for c in anak:
        anak_m = _stub(f"{nama}.{c}")
        # Harus jadi atribut NYATA — kalau tidak, `import torch.nn as nn`
        # jatuh ke __getattr__ modul induk dan mengembalikan _Any.
        setattr(m, c, anak_m)
    return m

_stub("cv2")
_stub("torch", ["nn"])
_stub("ultralytics")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from production.api import router, ws_router, pasang_manager
from production.manager import CameraManager

lulus, gagal = 0, 0
def cek(nama, kondisi, info=""):
    global lulus, gagal
    if kondisi: lulus += 1; print(f"  ok   {nama}")
    else: gagal += 1; print(f"  GAGAL {nama}  {info}")

app = FastAPI()
app.include_router(router)
app.include_router(ws_router)
klien = TestClient(app)

print("\n[A] Route terdaftar")
jalur = set(klien.get("/openapi.json").json()["paths"])
for p in ["/api/produksi/kamera", "/api/produksi/kejadian", "/api/produksi/kesehatan",
          "/api/produksi/kamera/{camera_id}/pratinjau",
          "/api/produksi/kejadian/{kejadian_id}/tanggapi"]:
    cek(f"ada {p}", p in jalur, sorted(jalur))
# /ws/produksi/alert tidak muncul di OpenAPI (WebSocket) — dibuktikan di blok [F].

print("\n[B] Gerbang: mode produksi belum aktif → 503, bukan crash")
r = klien.get("/api/produksi/kamera")
cek("503 saat manager belum dipasang", r.status_code == 503, f"dapat {r.status_code}")
cek("pesan menuntun ke SAPA_PRODUKSI", "SAPA_PRODUKSI" in r.json().get("detail", ""))

print("\n[C] Manager aktif → CRUD kamera lewat HTTP")
d = tempfile.mkdtemp()
m = CameraManager(path_profil=os.path.join(d, "cam.json"),
                  path_log_kejadian=os.path.join(d, "kejadian.jsonl"))
pasang_manager(m)

r = klien.get("/api/produksi/kamera")
cek("daftar kosong di awal", r.status_code == 200 and r.json()["jumlah"] == 0)

# aktif=false supaya tidak benar-benar menyalakan pekerja kamera
r = klien.post("/api/produksi/kamera", json={
    "id": "lorong-1", "nama": "Lorong 1",
    "sumber": "rtsp://admin:rahasia@10.0.0.9:554/s1",
    "jenis": "lorong", "aktif": False})
cek("tambah kamera → 201", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
if r.status_code == 201:
    b = r.json()
    cek("lorong → run_fall true", b["run_fall"] is True)
    cek("lorong → run_interaction false", b["run_interaction"] is False)

r = klien.get("/api/produksi/kamera")
cek("password RTSP tidak bocor di daftar", "rahasia" not in r.text, r.text[:160])

r = klien.post("/api/produksi/kamera", json={
    "id": "x", "nama": "X", "sumber": "0", "jenis": "atap", "aktif": False})
cek("jenis ngawur → 400", r.status_code == 400, f"dapat {r.status_code}")

r = klien.post("/api/produksi/kamera", json={
    "id": "lorong-1", "nama": "Dobel", "sumber": "0", "aktif": False})
cek("id duplikat → 400", r.status_code == 400, f"dapat {r.status_code}")

r = klien.patch("/api/produksi/kamera/lorong-1", json={"jenis": "rak"})
cek("ubah jenis → 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
if r.status_code == 200:
    b = r.json()
    cek("jadi rak → jatuh mati, interaksi hidup",
        b["run_fall"] is False and b["run_interaction"] is True)
    cek("skip_dwell ikut default rak", b["skip_dwell"] is True)

r = klien.get("/api/produksi/kamera/tidak-ada")
cek("kamera tak dikenal → 404", r.status_code == 404, f"dapat {r.status_code}")

r = klien.post("/api/produksi/kamera/lorong-1/berhenti")
cek("berhenti pada kamera mati tetap 200", r.status_code == 200, f"dapat {r.status_code}")

print("\n[D] Kejadian & kesehatan")
r = klien.get("/api/produksi/kejadian")
cek("log kejadian 200", r.status_code == 200)
cek("ada ringkasan retensi", "retensi_jam" in r.json()["ringkasan"])

r = klien.post("/api/produksi/kejadian/tidakada/tanggapi", json={"status": "diabaikan"})
cek("tanggapi kejadian hantu → 404", r.status_code == 404, f"dapat {r.status_code}")

r = klien.post("/api/produksi/kejadian/apa/tanggapi", json={"status": "ngawur"})
cek("status tanggapan ngawur → 400", r.status_code == 400, f"dapat {r.status_code}")

r = klien.get("/api/produksi/kesehatan")
cek("kesehatan 200", r.status_code == 200, r.text[:120])
if r.status_code == 200:
    h = r.json()
    cek("melaporkan jumlah kamera", h["jumlah_kamera"] == 1, f"{h.get('jumlah_kamera')}")
    cek("melaporkan status model", "model" in h)

print("\n[E] Pratinjau saat kamera tidak berjalan")
r = klien.get("/api/produksi/kamera/lorong-1/pratinjau")
cek("pratinjau kamera mati → 409", r.status_code == 409, f"dapat {r.status_code}")

print("\n[F] WebSocket alert mengirim snapshot awal")
try:
    with klien.websocket_connect("/ws/produksi/alert") as ws:
        pesan = ws.receive_json()
        cek("pesan pertama bertipe 'awal'", pesan.get("type") == "awal", str(pesan)[:120])
        cek("membawa daftar kejadian", "kejadian" in pesan)
except Exception as e:
    cek("websocket tersambung", False, repr(e))

m.berhenti()
print(f"\n{'='*52}\nLULUS {lulus} / {lulus+gagal}" + (f"  — GAGAL {gagal}" if gagal else "  — semua lulus"))
sys.exit(1 if gagal else 0)
