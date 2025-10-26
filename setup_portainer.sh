#!/bin/bash

echo "============================================"
echo "  Sistema de Protocolo - Setup Portainer"
echo "============================================"
echo ""

# Verificar se .env existe
if [ ! -f .env ]; then
    echo "❌ Arquivo .env não encontrado!"
    echo "📝 Copiando env.example para .env..."
    cp env.example .env
    echo "⚠️  IMPORTANTE: Edite o arquivo .env com suas configurações!"
    echo ""
fi

# Verificar se Python está instalado (para verificação local)
if command -v python3 &> /dev/null; then
    echo "✅ Python3 encontrado"
else
    echo "⚠️  Python3 não encontrado (não é necessário para Docker)"
fi

# Verificar se Docker está instalado
if command -v docker &> /dev/null; then
    echo "✅ Docker encontrado"
    docker --version
else
    echo "❌ Docker não encontrado! Instale o Docker primeiro."
    exit 1
fi

# Verificar se Docker Compose está instalado
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose encontrado"
    docker-compose --version
else
    echo "❌ Docker Compose não encontrado! Instale o Docker Compose primeiro."
    exit 1
fi

echo ""
echo "============================================"
echo "  Próximos Passos:"
echo "============================================"
echo ""
echo "1️⃣  Edite o arquivo .env com suas configurações"
echo "2️⃣  Execute: docker-compose up -d --build"
echo "3️⃣  Acesse: http://localhost:8800"
echo ""
echo "💡 Para ver logs: docker-compose logs -f"
echo "🛑 Para parar: docker-compose down"
echo ""
echo "📖 Para mais informações, leia: DEPLOY_PORTAINER.md"
echo ""
