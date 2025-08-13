#!/bin/bash

echo "🔄 Reiniciando Serviço Python AI na VPS"
echo "======================================"
echo

# Para o container se estiver rodando
echo "⏹️ Parando container python-ai..."
docker stop python-ai 2>/dev/null || echo "Container já estava parado"

# Remove o container se existir
echo "🗑️ Removendo container python-ai..."
docker rm python-ai 2>/dev/null || echo "Container já foi removido"

# Reconstrói e inicia os serviços
echo "🏗️ Reconstruindo e iniciando serviços..."
docker-compose up -d --build python-ai

# Aguarda um pouco para o serviço iniciar
echo "⏳ Aguardando serviço iniciar..."
sleep 10

# Verifica se está funcionando
echo "✅ Verificando se o serviço está funcionando:"
docker logs --tail 10 python-ai
echo

echo "🌐 Testando conectividade:"
docker exec aleen-ia curl -s --max-time 5 http://python-ai:8000/health && echo "✅ Serviço funcionando!" || echo "❌ Serviço ainda com problemas"

echo
echo "🏁 Reinicialização concluída!"
echo "Para monitorar os logs em tempo real, execute:"
echo "  docker-compose logs -f python-ai"
