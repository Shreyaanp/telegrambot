#!/bin/bash
# Quick script to check production bot status

echo "📊 Telegram Bot Production Status"
echo "=================================="
echo ""

# Service status
echo "🤖 Service Status:"
sudo systemctl status telegrambot --no-pager | head -10
echo ""

# Nginx status
echo "🌐 Nginx Status:"
sudo systemctl status nginx --no-pager | head -5
echo ""

# SSL certificate
echo "🔒 SSL Certificate:"
sudo certbot certificates | grep telegram.mercle.ai -A 5
echo ""

# Health check
echo "💓 Health Check:"
curl -s https://telegram.mercle.ai/health | jq || echo "Bot not responding"
echo ""

# Recent logs
echo "📝 Recent Logs (last 20 lines):"
sudo journalctl -u telegrambot -n 20 --no-pager
echo ""

# Webhook info
echo "🔗 Webhook Info:"
curl -s https://telegram.mercle.ai/webhook/info | jq || echo "Cannot fetch webhook info"

