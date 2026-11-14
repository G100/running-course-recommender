#!/usr/bin/env bash
# 런메이트 서버를 우분투 VM(Ubuntu 24.04, x86_64·ARM 모두)에 올린다. Azure for Students의 B1s(1GB)에서도 돈다.
#
#   ssh 로 VM에 들어가서:
#     curl -fsSL https://raw.githubusercontent.com/G100/running-course-recommender/master/deploy/server_setup.sh | bash
#   또는 저장소를 받은 뒤:  bash deploy/server_setup.sh
#
# 하는 일 (다시 실행해도 된다 — 이미 된 단계는 건너뛰거나 최신으로 맞춘다):
#   0. 메모리가 2GB보다 작으면 스왑 2GB를 만들고 동네 도로망을 한 곳만 들고 있게 한다
#   1. 필요한 프로그램: python3·venv·git, HTTPS를 맡을 Caddy
#   2. 저장소 받기(있으면 최신으로)
#   3. 가상환경에 패키지 설치 + src.setup_local (지도 파일 받기·MD5 확인·전국 지형 DB 만들기 약 8분·테스트)
#   4. 서버 자동 실행(systemd): 켜면 뜨고, 죽으면 다시 뜬다. 127.0.0.1:8000 에서만 듣는다
#   5. HTTPS(Caddy): <공인 IP를 - 로 이은 것>.sslip.io 주소로 인증서를 자동으로 받는다 (도메인을 사지 않아도 된다)
#   6. 방화벽: 이미지가 80·443을 막아 두었으면 연다 (클라우드 쪽 방화벽/보안 그룹에서도 열어야 한다)
#
# 비밀값(.env: TMAP_APP_KEY·DATABASE_URL 등)은 이 스크립트가 만들지 않는다. 처음 한 번 ~/runmate/.env 에 직접 넣는다.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive   # 설치 중 묻는 화면(방화벽 규칙 저장 여부 등) 없이 진행한다

REPO=https://github.com/G100/running-course-recommender.git
APP=$HOME/runmate
PY=$APP/.venv/bin/python

# 메모리가 작은 서버(Azure B1s 1GB 등): 디스크 2GB를 메모리 대신 쓰게 하고(스왑), 동네 도로망은 한 곳만 들고 있는다.
# 동네 도로망이 동네당 수백 MB라 1GB로는 빠듯하다 — 모자라면 서버가 죽는 대신 느려지게 한다
MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
AREAS=6
if [ "$MEM_KB" -lt 2000000 ]; then
  AREAS=1
  if ! swapon --show | grep -q /swapfile; then
    echo "▶ 0. 스왑 2GB (메모리 $((MEM_KB / 1024))MB)"
    sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
fi

echo "▶ 1. 프로그램 설치"
sudo apt-get -o DPkg::Lock::Timeout=600 update -y
sudo -E apt-get -o DPkg::Lock::Timeout=600 install -y python3 python3-venv python3-pip git debian-keyring debian-archive-keyring apt-transport-https curl iptables-persistent
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get -o DPkg::Lock::Timeout=600 update -y && sudo -E apt-get -o DPkg::Lock::Timeout=600 install -y caddy
fi

echo "▶ 2. 저장소"
# RUNMATE_NO_PULL=1: 저장소를 새로 받지 않는다 (커밋 전 작업본을 직접 올려 둔 경우)
if [ "${RUNMATE_NO_PULL:-}" = 1 ]; then echo "  (저장소 받기 건너뜀)"
elif [ -d "$APP/.git" ]; then git -C "$APP" pull --ff-only; else git clone "$REPO" "$APP"; fi
cd "$APP"

echo "▶ 3. 패키지·지형 DB"
[ -x "$PY" ] || python3 -m venv .venv
$PY -m pip install -q --upgrade pip
$PY -m pip install -q -r requirements.txt -r requirements-map.txt
$PY -m src.setup_local

if ! grep -q '^TMAP_APP_KEY=.\+' .env 2>/dev/null; then
  echo "!! ~/runmate/.env 에 TMAP_APP_KEY 와 DATABASE_URL 을 넣은 뒤 이 스크립트를 다시 실행하세요."
  exit 1
fi

echo "▶ 4. 자동 실행 (systemd)"
sudo tee /etc/systemd/system/runmate.service >/dev/null <<UNIT
[Unit]
Description=Runmate course server
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
Environment=RUNMATE_AREAS_IN_MEMORY=$AREAS
# 동네 도로망을 메모리에 들고 있어서(동네당 약 300MB) 프로세스는 하나만 띄운다
ExecStart=$PY -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now runmate
sudo systemctl restart runmate

echo "▶ 5. HTTPS (Caddy)"
IP=$(curl -fsS https://api.ipify.org)
DOMAIN="${IP//./-}.sslip.io"
sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:8000 {
        # 긴 코스는 그 자리에서 새로 짜느라 1~2분 걸릴 수 있다
        transport http {
            read_timeout 300s
        }
    }
}
CADDY
sudo systemctl reload caddy || sudo systemctl restart caddy

echo "▶ 6. 방화벽 (80·443)"
for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport $port -j ACCEPT 2>/dev/null || sudo iptables -I INPUT -p tcp --dport $port -j ACCEPT
done
sudo netfilter-persistent save

echo
echo "끝. 서버 주소: https://$DOMAIN"
echo "확인: curl https://$DOMAIN/health"
echo "로그: journalctl -u runmate -f"
