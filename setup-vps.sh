#!/bin/bash
set -e

# ══════════════════════════════════════════
# AURELIA ENGINE — Setup Script for VPS
# Testado em Ubuntu 22.04/24.04 (Hostinger)
# ══════════════════════════════════════════

echo "═══════════════════════════════════════"
echo "  AURELIA ENGINE — VPS Setup"
echo "═══════════════════════════════════════"

# 1. Update system
echo "→ Atualizando sistema..."
sudo apt-get update -y
sudo apt-get upgrade -y

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "→ Instalando Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    echo "✓ Docker instalado. Faça logout e login para usar sem sudo."
else
    echo "✓ Docker já instalado"
fi

# 3. Install Docker Compose plugin if not present
if ! docker compose version &> /dev/null; then
    echo "→ Instalando Docker Compose..."
    sudo apt-get install -y docker-compose-plugin
else
    echo "✓ Docker Compose já instalado"
fi

# 4. Install Nginx
if ! command -v nginx &> /dev/null; then
    echo "→ Instalando Nginx..."
    sudo apt-get install -y nginx
else
    echo "✓ Nginx já instalado"
fi

# 5. Install Certbot for SSL
if ! command -v certbot &> /dev/null; then
    echo "→ Instalando Certbot..."
    sudo apt-get install -y certbot python3-certbot-nginx
else
    echo "✓ Certbot já instalado"
fi

# 6. Setup firewall
echo "→ Configurando firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

# 7. Create .env from template
if [ ! -f .env ]; then
    echo "→ Criando .env..."
    API_KEY=$(openssl rand -hex 32)
    cp .env.example .env
    sed -i "s/change-me-in-production/$API_KEY/" .env
    echo "✓ .env criado com API key: $API_KEY"
    echo ""
    echo "╔══════════════════════════════════════════════════╗"
    echo "║  GUARDE ESTA API KEY (vai usar no AudioBuilder) ║"
    echo "║  $API_KEY  ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo ""
else
    echo "✓ .env já existe"
fi

# 8. Build and start
echo "→ Fazendo build do Docker..."
docker compose build

echo "→ Iniciando Aurelia Engine..."
docker compose up -d

# 9. Check health
echo "→ Aguardando inicialização..."
sleep 5
if curl -s http://localhost:8000/health | grep -q "ok"; then
    echo "✓ Aurelia Engine rodando!"
else
    echo "⚠ Verificar logs: docker compose logs aurelia"
fi

echo ""
echo "═══════════════════════════════════════"
echo "  PRÓXIMOS PASSOS:"
echo "═══════════════════════════════════════"
echo ""
echo "1. Configure o DNS: aurelia.audiobuilder.com.br → IP da VPS"
echo ""
echo "2. Copie o nginx config:"
echo "   sudo cp nginx/aurelia.conf /etc/nginx/sites-available/aurelia"
echo "   sudo ln -s /etc/nginx/sites-available/aurelia /etc/nginx/sites-enabled/"
echo "   sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "3. Gere o SSL:"
echo "   sudo certbot --nginx -d aurelia.audiobuilder.com.br"
echo ""
echo "4. Teste a API:"
echo "   curl http://localhost:8000/health"
echo ""
echo "5. No AudioBuilder (.env), adicione:"
echo "   AURELIA_ENGINE_URL=https://aurelia.audiobuilder.com.br"
echo "   AURELIA_API_KEY=<a key que foi gerada acima>"
echo ""
