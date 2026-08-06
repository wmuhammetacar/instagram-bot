#!/usr/bin/env bash
# ============================================================
#  Instagram Bot - Tek komut kurulum
#  Kullanim: ./install.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Python 3.9+ kontrol ediliyor"
if ! command -v python3 >/dev/null 2>&1; then
    echo "HATA: python3 bulunamadi. once Python 3.9+ kurun." >&2
    exit 1
fi

echo "==> Sanal ortam olusturuluyor"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Bagimliliklar yukleniyor"
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "==> Paket kuruluyor (igbot komutu)"
pip install -e . -q

if [ ! -f .env ]; then
    echo "==> .env ornegi kopyalandi (sifrenizi buraya yazin)"
    cp .env.example .env
fi

chmod +x install.sh

echo ""
echo "Kurulum tamamlandi."
echo "  1) .env dosyasini duzenleyin: nano .env"
echo "  2) dogrulama:                igbot --version   (veya python bot.py --version)"
echo "  3) girisi yapin:             igbot login"
echo ""
