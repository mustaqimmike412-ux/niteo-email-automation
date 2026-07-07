#!/bin/bash
# =============================================================================
# Niteo Solar 邮件自动化系统 - 一键部署脚本
# 在 Ubuntu 22.04 LTS 服务器上执行
# =============================================================================

set -e

APP_NAME="email_automation"
APP_DIR="/var/www/${APP_NAME}"
DOMAIN="${DOMAIN:-exim-flow.com}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/mustaqimmike412-ux/niteo-email-automation.git}"

echo "=========================================="
echo " Niteo Solar 邮件自动化系统部署脚本"
echo "=========================================="
echo ""

# 步骤 1：更新系统
echo "[1/10] 更新系统..."
apt update && apt upgrade -y

# 步骤 2：安装依赖
echo "[2/10] 安装系统依赖..."
apt install -y python3 python3-pip python3-venv python3-dev \
    nginx git curl wget \
    libnginx-mod-http-geoip2 geoipupdate \
    certbot python3-certbot-nginx

# 步骤 3：配置 GeoIP2
echo "[3/10] 配置 GeoIP2..."
if [ ! -f /etc/GeoIP.conf ]; then
    cat > /etc/GeoIP.conf << 'GEOF'
AccountID 0
LicenseKey 000000000000
EditionIDs GeoLite2-Country
GEOF
    echo "  ⚠ 请编辑 /etc/GeoIP.conf 填入你的 MaxMind License Key"
    echo "    获取地址: https://www.maxmind.com/en/geolite2/signup"
fi
geoipupdate 2>/dev/null || echo "  ⚠ geoipupdate 需要配置 License Key 后重试"

# 步骤 4：克隆代码
echo "[4/10] 克隆代码..."
mkdir -p /var/www
cd /var/www
if [ -d "${APP_DIR}" ]; then
    echo "  目录已存在，执行 git pull..."
    cd "${APP_DIR}" && git pull origin main
else
    git clone "${GITHUB_REPO}" "${APP_DIR}"
    cd "${APP_DIR}"
fi

# 步骤 5：创建 Python 虚拟环境
echo "[5/10] 安装 Python 依赖..."
cd "${APP_DIR}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 步骤 6：创建数据库目录
echo "[6/10] 创建数据库目录..."
mkdir -p "${APP_DIR}/database"
mkdir -p /var/backups/email_automation

# 步骤 7：配置 systemd 服务
echo "[7/10] 配置 systemd 服务..."
cat > /etc/systemd/system/email-automation.service << EOF
[Unit]
Description=Niteo Email Automation
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"
Environment="PYTHONPATH=${APP_DIR}"
Environment="DATABASE_PATH=${APP_DIR}/database/email_automation.db"
ExecStart=${APP_DIR}/venv/bin/gunicorn -w 1 -b 127.0.0.1:5000 --timeout 120 web.app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable email-automation

# 步骤 8：配置 Nginx
echo "[8/10] 配置 Nginx..."

cp "${APP_DIR}/deploy/nginx.conf" /etc/nginx/sites-available/email-automation
sed -i "s/your-domain.com/${DOMAIN}/g" /etc/nginx/sites-available/email-automation

# 启用配置
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
fi
if [ ! -f /etc/nginx/sites-enabled/email-automation ]; then
    ln -s /etc/nginx/sites-available/email-automation /etc/nginx/sites-enabled/
fi

nginx -t && systemctl restart nginx

# 步骤 9：配置 SSL
echo "[9/10] 配置 SSL (Let's Encrypt)..."
if ! certbot certificates | grep -q "${DOMAIN}"; then
    certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --email "admin@${DOMAIN}" || true
else
    echo "  SSL 证书已存在，跳过"
fi

# 步骤 10：启动服务
echo "[10/10] 启动服务..."
systemctl start email-automation
sleep 2
systemctl status email-automation --no-pager

echo ""
echo "=========================================="
echo " 部署完成！"
echo "=========================================="
echo ""
echo " 访问地址: https://${DOMAIN}"
echo ""
echo " 常用命令:"
echo "   查看日志: journalctl -u email-automation -f"
echo "   重启服务: systemctl restart email-automation"
echo "   查看状态: systemctl status email-automation"
echo "   备份数据库: ${APP_DIR}/deploy/backup.sh"
echo ""
echo " ⚠ 重要提醒:"
echo "   1. 配置环境变量: 编辑 /etc/systemd/system/email-automation.service"
echo "      添加 SMTP_PASSWORD、IMAP_PASSWORD、SECRET_KEY 等环境变量"
echo "      然后执行: systemctl daemon-reload && systemctl restart email-automation"
echo ""
echo "   2. 配置 GeoIP2 License Key: 编辑 /etc/GeoIP.conf"
echo "      然后执行: geoipupdate && systemctl restart nginx"
echo ""
