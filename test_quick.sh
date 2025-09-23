#!/bin/bash
# 🧪 Teste Rápido - Python AI Service

echo "🚀 Testando Python AI Service..."

# Determinar URL baseado no ambiente
if [ "$1" = "prod" ]; then
    BASE_URL="https://ai-aleen.live.claudy.host"
    echo "🌐 Testando em PRODUÇÃO: $BASE_URL"
else
    BASE_URL="http://localhost:8000"
    echo "🔧 Testando em LOCAL: $BASE_URL"
fi

# Teste 1: Health Check
echo "1️⃣ Testando Health Check..."
curl -s $BASE_URL/health | jq '.'

echo ""

# Teste 2: Listar Agentes
echo "2️⃣ Listando Agentes..."
curl -s $BASE_URL/agents | jq '.'

echo ""

# Teste 3: Chat Simples
echo "3️⃣ Teste de Chat..."
curl -s -X POST $BASE_URL/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "user_name": "Test User", 
    "message": "Olá!"
  }' | jq '.'

echo ""
echo "✅ Testes concluídos!"
echo ""
echo "💡 Para testar produção: ./test_quick.sh prod"
