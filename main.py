import os
import re
import time
import logging
import requests

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config dari environment variable ──────────────────────────────────────────
X_AUTH_TOKEN      = os.environ["X_AUTH_TOKEN"]
X_CT0             = os.environ["X_CT0"]
TARGET_X_USERNAME = os.environ.get("TARGET_X_USERNAME", "GuarEmperor")
CHECK_INTERVAL    = int(os.environ.get("CHECK_INTERVAL", "60"))

# ── 4 Discord user token ───────────────────────────────────────────────────────
DISCORD_TOKENS: list[str] = [
    t.strip()
    for key in ["DISCORD_TOKEN_1", "DISCORD_TOKEN_2", "DISCORD_TOKEN_3", "DISCORD_TOKEN_4"]
    if (t := os.environ.get(key, ""))
]
if not DISCORD_TOKENS:
    raise RuntimeError("Minimal 1 DISCORD_TOKEN_1 harus di-set!")

log.info(f"✅ {len(DISCORD_TOKENS)} Discord token loaded")

# ── X API headers ─────────────────────────────────────────────────────────────
X_HEADERS = {
    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
    "cookie": f"auth_token={X_AUTH_TOKEN}; ct0={X_CT0}",
    "x-csrf-token": X_CT0,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "content-type": "application/json",
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session",
    "x-twitter-client-language": "en",
}

# ── Regex patterns ────────────────────────────────────────────────────────────
DISCORD_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.gg)/([a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)
DISCORD_KEYWORDS = re.compile(
    r"(code\s*discord|discord\s*code|invite\s*code|invited\s*code|"
    r"join\s*discord|discord\s*server|put\s*the\s*code|go\s*to\s*discord|"
    r"share\s*code|code\s*:)",
    re.IGNORECASE,
)
RAW_CODE_RE   = re.compile(r"(?:^|\n)\s*([a-zA-Z0-9]{6,12})\s*(?:\n|$)", re.MULTILINE)
SPLIT_CODE_RE = re.compile(
    r"(?:^|\n)\s*([a-zA-Z0-9]{1,3})\s+([a-zA-Z0-9]{5,10})\s*(?:\n|$)",
    re.MULTILINE,
)
COMMON_WORDS = {
    "discord","server","join","code","free","tools","real","time","paid",
    "come","dont","forget","active","slots","member","opening","invited",
    "invite","and","not","you","can","get","put","the","go","to","ok",
    "for","soon","cook","alpha","incoming","just","letsgoooo","check",
    "expired","interact","post","gonna","share","alright","juga",
    "this","that","will","have","been","your","our","their",
    "frens","gm","lfg","ngmi","wagmi","dyor","nfa","fomo","rekt",
}

# ── State ─────────────────────────────────────────────────────────────────────
processed_tweet_ids: set[str] = set()
TARGET_USER_ID: str | None = None


# ── X API functions ───────────────────────────────────────────────────────────
def get_user_id(username: str) -> str | None:
    """Ambil user ID dari username."""
    url = "https://api.twitter.com/2/users/by/username/" + username
    params = {"user.fields": "id,name"}
    try:
        resp = requests.get(url, headers=X_HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            user_id = data["data"]["id"]
            log.info(f"👤 @{username} → ID: {user_id}")
            return user_id
        else:
            log.error(f"❌ Gagal get user ID: {resp.status_code} {resp.text[:200]}")
            return None
    except Exception as e:
        log.error(f"❌ Error get user ID: {e}")
        return None


def get_latest_tweets(user_id: str, count: int = 5) -> list[dict]:
    """Ambil tweet terbaru dari user."""
    url = f"https://api.twitter.com/2/users/{user_id}/tweets"
    params = {
        "max_results": count,
        "tweet.fields": "id,text,created_at",
        "expansions": "author_id",
    }
    try:
        resp = requests.get(url, headers=X_HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", [])
        else:
            log.error(f"❌ Gagal fetch tweets: {resp.status_code} {resp.text[:200]}")
            return []
    except Exception as e:
        log.error(f"❌ Error fetch tweets: {e}")
        return []


# ── Code extraction ───────────────────────────────────────────────────────────
def _is_likely_code(token: str) -> bool:
    if token.lower() in COMMON_WORDS: return False
    if token.isdigit(): return False
    if token.isalpha() and token.islower(): return False
    if token.isalpha() and token.isupper(): return False
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    has_digit = any(c.isdigit() for c in token)
    return (has_upper and has_lower) or ((has_upper or has_lower) and has_digit)


def extract_invite_codes(text: str) -> list[str]:
    found, seen = [], set()

    def add(code: str) -> None:
        code = code.strip()
        if code and code not in seen and len(code) >= 6:
            seen.add(code); found.append(code)

    for m in DISCORD_URL_RE.finditer(text):
        add(m.group(1))

    if DISCORD_KEYWORDS.search(text):
        for m in SPLIT_CODE_RE.finditer(text):
            prefix, suffix = m.group(1), m.group(2)
            candidate = prefix + suffix
            if _is_likely_code(candidate) and candidate not in seen:
                add(candidate)
        for m in RAW_CODE_RE.finditer(text):
            token = m.group(1)
            if token not in seen and _is_likely_code(token):
                add(token)

    if found:
        log.info(f"   🔍 Code ditemukan: {found}")
    return found


# ── Discord join ──────────────────────────────────────────────────────────────
def join_discord_server(invite_code: str, token: str, account_num: int) -> bool:
    url = f"https://discord.com/api/v9/invites/{invite_code}"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "X-Context-Properties": "eyJsb2NhdGlvbiI6IkpvaW4gR3VpbGQifQ==",
    }
    tag = f"[Akun {account_num}]"
    try:
        resp = requests.post(url, headers=headers, json={}, timeout=10)
        if resp.status_code in (200, 201):
            guild_name = resp.json().get("guild", {}).get("name", "Unknown")
            log.info(f"   ✅ {tag} Berhasil join: {guild_name}")
            return True
        elif resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 5)
            log.warning(f"   ⏳ {tag} Rate limited {retry_after}s")
            time.sleep(retry_after)
            return join_discord_server(invite_code, token, account_num)
        elif resp.status_code == 404:
            log.warning(f"   ⚠️  {tag} Code expired/invalid: {invite_code}")
            return False
        else:
            log.error(f"   ❌ {tag} HTTP {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        log.error(f"   ❌ {tag} Error: {e}")
        return False


def join_all_accounts(invite_code: str) -> None:
    log.info(f"   🎯 Join dengan code '{invite_code}' untuk {len(DISCORD_TOKENS)} akun...")
    for i, token in enumerate(DISCORD_TOKENS, start=1):
        join_discord_server(invite_code, token, i)
        time.sleep(2)


# ── Tweet processing ──────────────────────────────────────────────────────────
def process_tweet(tweet: dict) -> None:
    tweet_id   = tweet.get("id", "")
    tweet_text = tweet.get("text", "")

    if tweet_id in processed_tweet_ids:
        return

    processed_tweet_ids.add(tweet_id)
    log.info(f"📢 Tweet [{tweet_id}]: {tweet_text[:100]}")

    codes = extract_invite_codes(tweet_text)
    if not codes:
        log.info("   → Tidak ada Discord invite code.")
        return

    for code in codes:
        join_all_accounts(code)
        time.sleep(3)


# ── Main loop ─────────────────────────────────────────────────────────────────
def main() -> None:
    global TARGET_USER_ID

    log.info(f"🚀 GE Discord Bot starting...")
    log.info(f"🎯 Target: @{TARGET_X_USERNAME}")
    log.info(f"⏱️  Interval: {CHECK_INTERVAL}s")

    # Ambil user ID sekali di awal
    while TARGET_USER_ID is None:
        TARGET_USER_ID = get_user_id(TARGET_X_USERNAME)
        if TARGET_USER_ID is None:
            log.warning("⚠️  Retry get user ID dalam 30s...")
            time.sleep(30)

    log.info(f"✅ Siap monitoring @{TARGET_X_USERNAME}!")

    while True:
        try:
            tweets = get_latest_tweets(TARGET_USER_ID, count=5)
            for tweet in tweets:
                process_tweet(tweet)
        except Exception as e:
            log.error(f"⚠️  Error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
