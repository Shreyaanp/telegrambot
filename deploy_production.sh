#!/bin/bash
# Production deployment script for EC2

set -e

echo "🚀 Starting production deployment..."

# Update .env with webhook configuration
cat >> .env << 'EOF'

# Production Webhook Configuration
WEBHOOK_URL=https://telegram.mercle.ai
WEBHOOK_PATH=/webhook/secure-path-$(openssl rand -hex 16)
EOF

echo "✅ Updated .env with webhook configuration"

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required packages
echo "📦 Installing Nginx and Certbot..."
sudo apt install -y nginx certbot python3-certbot-nginx

# Create Nginx configuration
echo "⚙️ Configuring Nginx..."
sudo tee /etc/nginx/sites-available/telegrambot > /dev/null <<'NGINX_EOF'
server {
    listen 80;
    server_name telegram.mercle.ai;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://localhost:8000/health;
        access_log off;
    }
}
NGINX_EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/telegrambot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
echo "🧪 Testing Nginx configuration..."
sudo nginx -t

# Restart Nginx
echo "🔄 Restarting Nginx..."
sudo systemctl restart nginx
sudo systemctl enable nginx

# Get SSL certificate
echo "🔒 Setting up SSL certificate..."
sudo certbot --nginx -d telegram.mercle.ai --non-interactive --agree-tos --email admin@mercle.ai --redirect

echo "✅ SSL certificate installed"

# Create systemd service
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/telegrambot.service > /dev/null <<EOF
[Unit]
Description=Telegram Verification Bot (Webhook)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegrambot
Environment="PATH=/home/ubuntu/telegrambot/venv/bin"
EnvironmentFile=/home/ubuntu/telegrambot/.env
ExecStart=/home/ubuntu/telegrambot/venv/bin/uvicorn webhook_server:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegrambot

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
echo "🚀 Starting bot service..."
sudo systemctl enable telegrambot
sudo systemctl start telegrambot

# Wait a few seconds for service to start
sleep 5

# Check status
echo "📊 Service status:"
sudo systemctl status telegrambot --no-pager

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Check logs: sudo journalctl -u telegrambot -f"
echo "2. Test health: curl https://telegram.mercle.ai/health"
echo "3. Check webhook: curl https://telegram.mercle.ai/webhook/info"
echo ""
echo "🤖 Your bot is now live at: https://telegram.mercle.ai"

