import os
import re
import time
import logging
import requests
from twikit import Client

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config dari environment variable ──────────────────────────────────────────
# Ambil dari browser: F12 → Application → Cookies → https://x.com
X_AUTH_TOKEN      = os.environ["X_AUTH_TOKEN"]   # nilai cookie auth_token
X_CT0             = os.environ["X_CT0"]           # nilai cookie ct0
TARGET_X_USERNAME = os.environ.get("TARGET_X_USERNAME", "GuarEmperor")
CHECK_INTERVAL    = int(os.environ.get("CHECK_INTERVAL", "60"))

# ── 4 Discord user token ───────────────────────────────────────────────────────
# Ambil semua token yang di-set, skip yang kosong
DISCORD_TOKENS: list[str] = [
    t.strip()
    for key in ["DISCORD_TOKEN_1", "DISCORD_TOKEN_2", "DISCORD_TOKEN_3", "DISCORD_TOKEN_4"]
    if (t := os.environ.get(key, ""))
]
if not DISCORD_TOKENS:
    raise RuntimeError("Minimal 1 DISCORD_TOKEN_1 harus di-set di environment variables!")

# ── Regex: Discord invite URL ─────────────────────────────────────────────────
DISCORD_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.gg)/([a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)

# ── Keyword trigger (GE selalu kasih konteks sebelum share code) ──────────────
DISCORD_KEYWORDS = re.compile(
    r"(code\s*discord|discord\s*code|invite\s*code|invited\s*code|"
    r"join\s*discord|discord\s*server|put\s*the\s*code|go\s*to\s*discord|"
    r"share\s*code|code\s*:)",
    re.IGNORECASE,
)

# ── Raw code standalone per baris ─────────────────────────────────────────────
RAW_CODE_RE = re.compile(r"(?:^|\n)\s*([a-zA-Z0-9]{6,12})\s*(?:\n|$)", re.MULTILINE)

# ── Split code per baris: "T ftUTdnRZ" atau "9 Zfw6unFm" ─────────────────────
SPLIT_CODE_RE = re.compile(
    r"(?:^|\n)\s*([a-zA-Z0-9]{1,3})\s+([a-zA-Z0-9]{5,10})\s*(?:\n|$)",
    re.MULTILINE,
)

# ── Kata umum yang bukan code ─────────────────────────────────────────────────
COMMON_WORDS = {
    "discord", "server", "join", "code", "free", "tools", "real", "time",
    "paid", "come", "dont", "forget", "active", "slots", "member", "opening",
    "invited", "invite", "and", "not", "you", "can", "get", "put", "the",
    "go", "to", "ok", "for", "soon", "cook", "alpha", "incoming", "just",
    "letsgoooo", "check", "expired", "interact", "post", "gonna", "share",
    "alright", "juga", "biar", "kalo", "yang", "atau", "dari", "dengan",
    "this", "that", "will", "have", "been", "your", "our", "their",
    "frens", "gm", "lfg", "ngmi", "wagmi", "dyor", "nfa", "fomo", "rekt",
}

# ── Set untuk track tweet yang sudah diproses ─────────────────────────────────
processed_tweet_ids: set[str] = set()


def _is_likely_code(token: str) -> bool:
    """
    Discord invite code ciri-cirinya:
    - Mixed case (huruf besar + kecil) ATAU alphanumeric mix
    - Bukan kata umum bahasa Inggris/Indo
    - Bukan murni angka atau murni huruf kecil/besar semua
    """
    if token.lower() in COMMON_WORDS:
        return False
    if token.isdigit():
        return False
    if token.isalpha() and token.islower():
        return False
    if token.isalpha() and token.isupper():
        return False
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    has_digit = any(c.isdigit() for c in token)
    return (has_upper and has_lower) or ((has_upper or has_lower) and has_digit)


def extract_invite_codes(text: str) -> list[str]:
    """
    Ambil semua Discord invite code dari tweet GE.

    Handle 3 pola:
    1. URL   : discord.gg/AbCdEf  atau discord.com/invite/AbCdEf
    2. Raw   : QJajym8b  (standalone per baris, setelah keyword discord)
    3. Split : "T ftUTdnRZ" → "TftUTdnRZ"  (GE sengaja kasih spasi di tengah)
    """
    found: list[str] = []
    seen:  set[str]  = set()

    def add(code: str) -> None:
        code = code.strip()
        if code and code not in seen and len(code) >= 6:
            seen.add(code)
            found.append(code)

    # 1. URL Discord (paling reliable)
    for m in DISCORD_URL_RE.finditer(text):
        add(m.group(1))

    # 2 & 3. Raw + Split (hanya kalau ada keyword discord di tweet)
    if DISCORD_KEYWORDS.search(text):

        # 2a. Split code per baris: "T ftUTdnRZ" → "TftUTdnRZ", "9 Zfw6unFm" → "9Zfw6unFm"
        # Prefix (huruf atau angka) selalu bagian dari code, tinggal buang spasinya
        for m in SPLIT_CODE_RE.finditer(text):
            prefix, suffix = m.group(1), m.group(2)
            candidate = prefix + suffix   # selalu gabung, spasi = sengaja dipisah GE
            if _is_likely_code(candidate) and candidate not in seen:
                add(candidate)

        # 2b. Raw code standalone per baris
        for m in RAW_CODE_RE.finditer(text):
            token = m.group(1)
            if token not in seen and _is_likely_code(token):
                add(token)

    if found:
        log.info(f"   🔍 Code ditemukan: {found}")
    return found


def join_discord_server(invite_code: str, token: str, account_num: int) -> bool:
    """Auto-join Discord server via invite code pakai 1 user token."""
    url = f"https://discord.com/api/v9/invites/{invite_code}"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "X-Context-Properties": "eyJsb2NhdGlvbiI6IkpvaW4gR3VpbGQifQ==",
    }
    tag = f"[Akun {account_num}]"
    try:
        resp = requests.post(url, headers=headers, json={}, timeout=10)
        if resp.status_code in (200, 201):
            data = resp.json()
            guild_name = data.get("guild", {}).get("name", "Unknown Server")
            log.info(f"   ✅ {tag} Berhasil join: {guild_name} (code: {invite_code})")
            return True
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 5)
            log.warning(f"   ⏳ {tag} Rate limited, retry after {retry_after}s")
            time.sleep(retry_after)
            return join_discord_server(invite_code, token, account_num)
        elif resp.status_code == 404:
            log.warning(f"   ⚠️  {tag} Code tidak valid atau expired: {invite_code}")
            return False
        else:
            log.error(f"   ❌ {tag} Gagal join — HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        log.error(f"   ❌ {tag} Error: {e}")
        return False


def join_all_accounts(invite_code: str) -> None:
    """Loop semua 4 akun Discord, join satu per satu dengan code yang sama."""
    log.info(f"   🎯 Menjalankan join untuk {len(DISCORD_TOKENS)} akun Discord...")
    for i, token in enumerate(DISCORD_TOKENS, start=1):
        join_discord_server(invite_code, token, i)
        time.sleep(2)  # jeda antar akun biar gak kena rate limit


def process_tweet(tweet) -> None:
    """Proses satu tweet: cek invite code lalu auto-join semua akun."""
    tweet_id   = tweet.id
    tweet_text = tweet.text or ""

    if tweet_id in processed_tweet_ids:
        return

    processed_tweet_ids.add(tweet_id)
    log.info(f"📢 Tweet baru [{tweet_id}]: {tweet_text[:120]}")

    codes = extract_invite_codes(tweet_text)
    if not codes:
        log.info("   → Tidak ada Discord invite code di tweet ini.")
        return

    for code in codes:
        join_all_accounts(code)
        time.sleep(3)  # jeda antar code


async def monitor_loop(client: Client) -> None:
    """Loop utama: poll tweets @GuarEmperor setiap CHECK_INTERVAL detik."""
    log.info(f"🚀 Mulai monitoring @{TARGET_X_USERNAME} setiap {CHECK_INTERVAL}s...")

    # Cache user ID biar gak fetch ulang tiap loop
    user = await client.get_user_by_screen_name(TARGET_X_USERNAME)
    log.info(f"👤 Target: @{TARGET_X_USERNAME} (ID: {user.id})")

    while True:
        try:
            tweets = await client.get_user_tweets(user.id, "Tweets", count=5)
            for tweet in tweets:
                process_tweet(tweet)
        except Exception as e:
            log.error(f"⚠️  Error saat fetch tweets: {e}")

        time.sleep(CHECK_INTERVAL)


async def main() -> None:
    client = Client(language="en-US")

    log.info("🔐 Set cookies X...")
    client.set_cookies({
        "auth_token": X_AUTH_TOKEN,
        "ct0":        X_CT0,
    })
    log.info("✅ Cookies set, siap monitoring!")

    await monitor_loop(client)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
