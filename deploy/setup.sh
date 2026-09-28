#!/bin/bash
# ============================================================
# Скрипт автоматической установки FiscalShop на Ubuntu 22.04/24.04
# ============================================================
set -e

echo "=========================================="
echo "  Установка FiscalShop на сервер"
echo "=========================================="

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Проверка root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Запустите с root: sudo bash setup.sh${NC}"
    exit 1
fi

# ======================== 1. ОБНОВЛЕНИЕ СИСТЕМЫ ========================
echo -e "\n${YELLOW}[1/8] Обновление системы...${NC}"
apt update && apt upgrade -y

# ======================== 2. УСТАНОВКА ЗАВИСИМОСТЕЙ ========================
echo -e "\n${YELLOW}[2/8] Установка зависимостей...${NC}"
apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx curl wget

# ======================== 3. СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ ========================
echo -e "\n${YELLOW}[3/8] Создание пользователя fiscalshop...${NC}"
if ! id -u fiscalshop &>/dev/null; then
    useradd -m -s /bin/bash fiscalshop
    usermod -aG sudo fiscalshop
fi

# ======================== 4. КОПИРОВАНИЕ ПРОЕКТА ========================
echo -e "\n${YELLOW}[4/8] Копирование проекта...${NC}"
mkdir -p /home/fiscalshop/app
cp -r ../* /home/fiscalshop/app/
chown -R fiscalshop:fiscalshop /home/fiscalshop/app

# ======================== 5. НАСТРОЙКА PYTHON ОКРУЖЕНИЯ ========================
echo -e "\n${YELLOW}[5/8] Настройка Python окружения...${NC}"
cd /home/fiscalshop/app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# ======================== 6. НАСТРОЙКА NGINX ========================
echo -e "\n${YELLOW}[6/8] Настройка Nginx...${NC}"

# Спрашиваем домен
read -p "Введите домен (например, fiscalshop.ru) или оставьте пустым для IP: " DOMAIN

if [ -n "$DOMAIN" ]; then
    # Конфиг с доменом
    cat > /etc/nginx/sites-available/fiscalshop << 'EOF'
server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/fiscalshop/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF
    sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" /etc/nginx/sites-available/fiscalshop
else
    # Конфиг без домена (по IP)
    cat > /etc/nginx/sites-available/fiscalshop << 'EOF'
server {
    listen 80;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/fiscalshop/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF
fi

# Включаем сайт
ln -sf /etc/nginx/sites-available/fiscalshop /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# ======================== 7. НАСТРОЙКА SYSTEMD ========================
echo -e "\n${YELLOW}[7/8] Настройка автозапуска...${NC}"

# Сервис для сайта
cat > /etc/systemd/system/fiscalshop.service << 'EOF'
[Unit]
Description=FiscalShop Web Application
After=network.target

[Service]
User=fiscalshop
Group=fiscalshop
WorkingDirectory=/home/fiscalshop/app
Environment="PATH=/home/fiscalshop/app/venv/bin"
ExecStart=/home/fiscalshop/app/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable fiscalshop
systemctl start fiscalshop

# ======================== 8. HTTPS (если есть домен) ========================
if [ -n "$DOMAIN" ]; then
    echo -e "\n${YELLOW}[8/8] Настройка HTTPS (Let's Encrypt)...${NC}"
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" || {
        echo -e "${YELLOW}Не удалось получить сертификат. Можно настроить позже:${NC}"
        echo "  sudo certbot --nginx -d $DOMAIN"
    }
    
    # Автообновление сертификата
    systemctl enable certbot.timer
    systemctl start certbot.timer
fi

# ======================== ГОТОВО ========================
echo ""
echo "=========================================="
echo -e "${GREEN}  Установка завершена!${NC}"
echo "=========================================="
echo ""

if [ -n "$DOMAIN" ]; then
    echo "Сайт: https://$DOMAIN"
else
    IP=$(curl -s ifconfig.me)
    echo "Сайт: http://$IP"
fi

echo ""
echo "Важные файлы:"
echo "  Проект:      /home/fiscalshop/app/"
echo "  .env:        /home/fiscalshop/app/.env"
echo "  Логи:        sudo journalctl -u fiscalshop -f"
echo "  Перезапуск:  sudo systemctl restart fiscalshop"
echo "  Остановка:   sudo systemctl stop fiscalshop"
echo ""
echo "Не забудьте отредактировать .env файл:"
echo "  sudo nano /home/fiscalshop/app/.env"
echo ""
echo "И установить Bitcoin Core (инструкция ниже)"
echo "=========================================="