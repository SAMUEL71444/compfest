"""Uji logika inti lapisan produksi SAPA — tanpa butuh kamera, torch, atau YOLO."""
import sys, time, tempfile, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from production.buffer import TrackWindowBuffer
from production.profiles import CameraProfile, ProfileStore, JENIS_LORONG, JENIS_RAK
from production.alerts import AlertEngine, EventLog, STATUS_DIABAIKAN

lulus, gagal = 0, 0
def cek(nama, kondisi, info=""):
    global lulus, gagal
    if kondisi:
        lulus += 1; print(f"  ok   {nama}")
    else:
        gagal += 1; print(f"  GAGAL {nama}  {info}")

def kps(x=100.0, y=100.0):
    a = np.zeros((17, 3), dtype=np.float32)
    a[:, 0] = x; a[:, 1] = y; a[:, 2] = 0.9
    a[5] = [x - 10, y - 20, 0.9]; a[6] = [x + 10, y - 20, 0.9]   # bahu
    a[11] = [x - 8, y + 20, 0.9]; a[12] = [x + 8, y + 20, 0.9]   # pinggul
    return a

print("\n[1] Buffer — jendela berbasis waktu")
buf = TrackWindowBuffer(window_seconds=3.0, stride_seconds=1.0, min_frames=10)
t = 1000.0
# 24 sampel @8fps hanya membentang 2,875 dtk — belum boleh dipancarkan.
for i in range(24):
    buf.push(1, kps(), t + i / 8.0)
cek("belum siap saat rentang < window_seconds", len(buf.jendela_siap()) == 0)
buf.push(1, kps(), t + 24 / 8.0)          # sampel ke-25 → rentang tepat 3,0 dtk
w = buf.jendela_siap()
cek("satu jendela dipancarkan", len(w) == 1, f"dapat {len(w)}")
if w:
    j = w[0]
    cek("src_fps mendekati 8 fps", abs(j.src_fps - 8.0) < 0.6, f"src_fps={j.src_fps:.2f}")
    cek("durasi mendekati 3 detik", abs(j.durasi - 3.0) < 0.3, f"durasi={j.durasi:.2f}")
    cek("bentuk frames [T,17,3]", j.frames.ndim == 3 and j.frames.shape[1:] == (17, 3))

print("\n[2] Buffer — stride ditegakkan")
for i in range(1, 8):          # +0,875 dtk — masih di bawah stride 1,0
    buf.push(1, kps(), t + 3.0 + i / 8.0)
cek("masih ditahan sebelum stride terlewati", len(buf.jendela_siap()) == 0)
buf.push(1, kps(), t + 4.0)    # tepat 1,0 dtk sejak jendela terakhir
cek("siap lagi setelah 1 detik", len(buf.jendela_siap()) == 1)

print("\n[3] Buffer — gap mengosongkan track (anti gerak palsu)")
b2 = TrackWindowBuffer(window_seconds=3.0, stride_seconds=1.0, max_gap_seconds=1.0, min_frames=10)
for i in range(24):
    b2.push(7, kps(), 500.0 + i / 8.0)
b2.push(7, kps(x=900), 500.0 + 3.0 + 4.0)      # jeda 4 detik → occlusion
cek("buffer direset setelah gap", b2.statistik()["reset_karena_gap"] == 1)
cek("tidak memancarkan jendela lintas-gap", len(b2.jendela_siap()) == 0)

print("\n[4] Buffer — track mati dibersihkan (anti bocor memori)")
b3 = TrackWindowBuffer(track_ttl_seconds=2.0)
b3.push(1, kps(), 100.0); b3.push(2, kps(), 100.0)
cek("2 track aktif", b3.jumlah_track == 2)
cek("keduanya dibuang setelah TTL", b3.bersihkan(200.0) == 2 and b3.jumlah_track == 0)

print("\n[5] Profil — pemetaan fitur ke sudut kamera DITEGAKKAN")
pl = CameraProfile.from_dict({"id": "l1", "nama": "Lorong", "sumber": "0", "jenis": JENIS_LORONG})
pr = CameraProfile.from_dict({"id": "r1", "nama": "Rak", "sumber": "0", "jenis": JENIS_RAK})
cek("lorong → jatuh ON, interaksi OFF", pl.run_fall and not pl.run_interaction)
cek("rak → interaksi ON, jatuh OFF", pr.run_interaction and not pr.run_fall)
cek("rak melewati dwell (top-down)", pr.skip_dwell is True)
cek("lorong memakai dwell", pl.skip_dwell is False)
cek("rak minta 2 jendela konfirmasi", pr.confirm_windows == 2)
cek("lorong minta 1 (jatuh = darurat)", pl.confirm_windows == 1)

print("\n[6] Profil — kredensial RTSP disamarkan di log & API")
p = CameraProfile.from_dict({"id": "c", "nama": "C", "sumber": "rtsp://admin:rahasia123@10.0.0.5:554/s1"})
cek("password tidak bocor", "rahasia123" not in p.sumber_aman(), p.sumber_aman())
cek("host masih terbaca", "10.0.0.5" in p.sumber_aman(), p.sumber_aman())

print("\n[7] Profil — ubah jenis mengembalikan default jenis baru")
d = tempfile.mkdtemp()
store = ProfileStore(os.path.join(d, "cam.json"))
store.tambah(CameraProfile.from_dict({"id": "x", "nama": "X", "sumber": "0", "jenis": JENIS_LORONG}))
cek("awalnya skip_dwell=False", store.ambil("x").skip_dwell is False)
baru = store.perbarui("x", {"jenis": JENIS_RAK})
cek("setelah jadi rak → skip_dwell=True", baru.skip_dwell is True)
cek("dwell_ratio ikut default rak", baru.dwell_ratio == 3.0, f"dwell={baru.dwell_ratio}")
cek("jatuh otomatis mati", not baru.run_fall)
store2 = ProfileStore(os.path.join(d, "cam.json"))
cek("bertahan setelah dibaca ulang", store2.ambil("x").jenis == JENIS_RAK)

print("\n[8] Profil — jenis ngawur ditolak")
try:
    CameraProfile.from_dict({"id": "z", "nama": "Z", "sumber": "0", "jenis": "atap"})
    cek("jenis tidak valid ditolak", False)
except ValueError:
    cek("jenis tidak valid ditolak", True)

print("\n[9] Alert — debounce konfirmasi + cooldown")
log = EventLog(retensi_jam=1.0, path_jsonl=os.path.join(d, "kejadian.jsonl"))
eng = AlertEngine(log)
def ajukan(tipe="butuh_bantuan", confirm=2, cooldown=60.0, tid=1):
    return eng.ajukan("cam1", "Cam 1", tipe, tid, 0.9, confirm, cooldown)
cek("jendela ke-1 ditekan (butuh 2)", ajukan() is None)
cek("jendela ke-2 memicu alert", ajukan() is not None)
cek("jendela ke-3 ditekan (cooldown)", ajukan() is None)
cek("jendela ke-4 ditekan (cooldown)", ajukan() is None)

print("\n[10] Alert — jatuh lolos di jendela pertama (kecepatan = nyawa)")
cek("confirm=1 langsung memicu", ajukan(tipe="jatuh", confirm=1, tid=2) is not None)

print("\n[11] Alert — cooldown habis → kejadian baru boleh muncul")
k = eng.ajukan("cam2", "Cam 2", "jatuh", 9, 0.9, 1, 0.05)
time.sleep(0.1)
k2 = eng.ajukan("cam2", "Cam 2", "jatuh", 9, 0.9, 1, 0.05)
cek("alert baru setelah cooldown lewat", k is not None and k2 is not None and k.id != k2.id)

print("\n[12] Alert — orang berbeda tidak saling membungkam")
a = eng.ajukan("cam3", "C3", "jatuh", 100, 0.9, 1, 999.0)
b = eng.ajukan("cam3", "C3", "jatuh", 101, 0.9, 1, 999.0)
cek("track berbeda → dua alert", a is not None and b is not None)

print("\n[13] Log — human-in-the-loop & privasi")
kj = log.daftar(batas=1)[0]
log.tanggapi(kj.id, STATUS_DIABAIKAN, oleh="andreas")
cek("status tersimpan", log.ambil(kj.id).status == STATUS_DIABAIKAN)
cek("ada pencatat tanggapan", log.ambil(kj.id).ditanggapi_oleh == "andreas")
isi = kj.to_dict()
terlarang = {"image", "frame", "keypoints", "gambar", "wajah", "pose"}
cek("tidak menyimpan gambar/pose", not (terlarang & set(isi.keys())), f"kunci={list(isi)}")

print("\n[14] Log — pulih setelah restart (JSONL)")
log2 = EventLog(retensi_jam=1.0, path_jsonl=os.path.join(d, "kejadian.jsonl"))
cek("kejadian dipulihkan dari berkas", len(log2.daftar(batas=100)) > 0,
    f"jumlah={len(log2.daftar(batas=100))}")

print("\n[15] Log — retensi menghapus yang kedaluwarsa")
log3 = EventLog(retensi_jam=0.0)     # semua langsung kedaluwarsa
eng3 = AlertEngine(log3)
eng3.ajukan("c", "C", "jatuh", 1, 0.9, 1, 0.0)
time.sleep(0.02)
dibuang = log3.buang_kedaluwarsa()
cek("kejadian kedaluwarsa dihapus", dibuang >= 1 and len(log3.daftar()) == 0)

print(f"\n{'='*52}\nLULUS {lulus} / {lulus+gagal}" + (f"  — GAGAL {gagal}" if gagal else "  — semua lulus"))
sys.exit(1 if gagal else 0)
