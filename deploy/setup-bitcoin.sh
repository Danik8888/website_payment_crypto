#!/bin/bash
# ============================================================
# Установка Bitcoin Core в Prune Mode на Ubuntu
# Запускать после setup.sh
# ============================================================
set -e

echo "=========================================="
echo "  Установка Bitcoin Core"
echo "=========================================="

# 1. Скачиваем Bitcoin Core
echo -e "\n[1] Скачивание Bitcoin Core..."
cd /tmp
wget -q https://bitcoincore.org/bin/bitcoin-core-28.0/bitcoin-28.0-x86_64-linux-gnu.tar.gz
tar -xzf bitcoin-28.0-x86_64-linux-gnu.tar.gz
sudo install -m 0755 -o root -g root -t /usr/local/bin bitcoin-28.0/bin/*

# 2. Настройка bitcoin.conf
echo -e "\n[2] Настройка bitcoin.conf..."
mkdir -p /home/fiscalshop/.bitcoin

cat > /home/fiscalshop/.bitcoin/bitcoin.conf << 'EOF'
# Testnet (для тестирования)
testnet=1

# Prune mode - 550 МБ
prune=550

# RPC настройки
server=1
rpcuser=user
rpcpassword=password
rpcallowip=127.0.0.1
rpcport=18332

# Кошелек
disablewallet=0
EOF

chown -R fiscalshop:fiscalshop /home/fiscalshop/.bitcoin

# 3. Создаем systemd сервис для Bitcoin Core
echo -e "\n[3] Настройка автозапуска Bitcoin Core..."

cat > /etc/systemd/system/bitcoind.service << 'EOF'
[Unit]
Description=Bitcoin Core Daemon
After=network.target

[Service]
User=fiscalshop
Group=fiscalshop
ExecStart=/usr/local/bin/bitcoind -conf=/home/fiscalshop/.bitcoin/bitcoin.conf
ExecStop=/usr/local/bin/bitcoin-cli -conf=/home/fiscalshop/.bitcoin/bitcoin.conf stop
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bitcoind
systemctl start bitcoind

# 4. Ждем запуск
echo -e "\n[4] Ожидание запуска Bitcoin Core..."
sleep 10

# 5. Создаем кошелек
echo -e "\n[5] Создание кошелька..."
su - fiscalshop -c "bitcoin-cli -testnet createwallet 'fiscalshop'" 2>/dev/null || true

echo ""
echo "=========================================="
echo "  Bitcoin Core установлен!"
echo "=========================================="
echo ""
echo "Проверка статуса:"
echo "  sudo systemctl status bitcoind"
echo ""
echo "Логи:"
echo "  sudo journalctl -u bitcoind -f"
echo ""
echo "Баланс:"
echo "  sudo -u fiscalshop bitcoin-cli -testnet getbalance"
echo ""
echo "Синхронизация:"
echo "  sudo -u fiscalshop bitcoin-cli -testnet getblockchaininfo"
echo ""
echo "=========================================="