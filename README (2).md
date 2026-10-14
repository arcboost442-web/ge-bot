# GE Discord Auto-Join Bot

Monitor tweets @GuarEmperor dan auto-join Discord server kalau ada invite code.

---

## Deploy ke Railway (Step by Step)

### 1. Upload ke GitHub

1. Buka **github.com** → login
2. Klik **"New repository"**
3. Nama repo: `ge-bot` → klik **Create repository**
4. Upload semua file ini ke repo tersebut

### 2. Connect Railway ke GitHub

1. Buka **railway.app** → login pakai GitHub
2. Klik **"New Project"**
3. Pilih **"Deploy from GitHub repo"**
4. Pilih repo `ge-bot` yang tadi dibuat
5. Railway akan otomatis detect Python dan mulai build

### 3. Set Environment Variables di Railway

1. Di project Railway, klik tab **"Variables"**
2. Tambahkan satu per satu:

| Key | Value |
|-----|-------|
| `X_USERNAME` | username X kamu |
| `X_EMAIL` | email X kamu |
| `X_PASSWORD` | password X kamu |
| `DISCORD_TOKEN` | Discord user token kamu |
| `TARGET_X_USERNAME` | `GuarEmperor` |
| `CHECK_INTERVAL` | `60` |

3. Klik **Deploy** → bot langsung jalan 24/7!

---

## Cara Kerja Bot

```
Setiap 60 detik
      ↓
Fetch 5 tweet terbaru @GuarEmperor
      ↓
Cek apakah ada discord.gg/xxxxx
      ↓
Kalau ada → auto join server Discord
      ↓
Log hasilnya (berhasil / gagal)
```

---

## Lihat Log Bot

Di Railway → tab **"Deployments"** → klik deployment aktif → lihat **Logs**

Contoh log sukses:
```
2024-01-15 10:30:00 [INFO] 📢 Tweet baru [123456]: Join server kita discord.gg/abcdef
2024-01-15 10:30:01 [INFO]    🎯 Invite code ditemukan: abcdef — mencoba join...
2024-01-15 10:30:02 [INFO]    ✅ Berhasil join server: Emperor Journal (code: abcdef)
```

---

## ⚠️ Disclaimer

- Self-bot melanggar ToS Discord — gunakan akun alt
- Jangan share token kamu ke siapapun
