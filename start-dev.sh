#!/bin/bash
# Start development environment with Cloudflare Tunnel
# Usage: ./start-dev.sh

set -e

echo "🚀 Starting Passing Circle Development Environment with Cloudflare Tunnel"
echo ""

# Check if .env.cloudflare exists
if [ ! -f .env.cloudflare ]; then
    echo "❌ Error: .env.cloudflare not found"
    echo "Please create it with your Cloudflare credentials"
    exit 1
fi

# Source environment variables
echo "📋 Loading Cloudflare credentials..."
set -a
source .env.cloudflare
set +a

# Check if tunnel token is set
if [ -z "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
    echo "❌ Error: CLOUDFLARE_TUNNEL_TOKEN not set in .env.cloudflare"
    exit 1
fi

echo "✅ Credentials loaded"
echo ""

# Start services
echo "🐳 Starting Docker services..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

echo ""
echo "⏳ Waiting for tunnel to connect..."
sleep 5

# Check tunnel status
echo ""
echo "📊 Tunnel Status:"
docker logs passingcircle-cloudflare-tunnel --tail 10 | grep -E "INF|ERR" || true

echo ""
echo "✅ Development environment started!"
echo ""
echo "🌐 Access your services at:"
echo "   - Chat:  https://chat.passingcircle.com"
echo "   - Auth:  https://auth.chat.passingcircle.com"
echo ""
echo "💡 To check tunnel status:"
echo "   docker logs passingcircle-cloudflare-tunnel"
echo ""
echo "🛑 To stop:"
echo "   docker compose -f docker-compose.yml -f docker-compose.dev.yml down"
