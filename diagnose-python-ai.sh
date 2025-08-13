#!/bin/bash

echo "🔍 Diagnóstico do Serviço Python AI na VPS"
echo "=========================================="
echo

# Verifica se os containers estão rodando
echo "📦 Verificando containers Docker:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(python-ai|aleen|redis)"
echo

# Verifica se todos os containers estão healthy
echo "🏥 Status de saúde dos containers:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(python-ai|aleen|redis)"
echo

# Verifica logs do container python-ai
echo "📋 Logs do container python-ai (últimas 20 linhas):"
docker logs --tail 20 python-ai 2>&1 || echo "❌ Container python-ai não encontrado"
echo

# Verifica a rede Docker
echo "🌐 Verificando rede Docker:"
docker network ls | grep -E "(bridge|aleen)"
echo
echo "📋 Containers na rede padrão:"
docker network inspect bridge --format='{{range .Containers}}{{.Name}} - {{.IPv4Address}}{{"\n"}}{{end}}' 2>/dev/null
echo

# Testa conectividade interna do Docker
echo "🌐 Testando conectividade interna Docker:"
echo "  Teste 1: aleen-ia -> python-ai"
docker exec aleen-ia ping -c 2 python-ai 2>/dev/null || echo "❌ Ping falhou"
echo "  Teste 2: aleen-ia -> python-ai:8000/health"
docker exec aleen-ia curl -s --max-time 5 http://python-ai:8000/health || echo "❌ Conexão HTTP falhou"
echo

# Verifica se a porta 8000 está aberta no container
echo "🔍 Verificando processo na porta 8000 do python-ai:"
docker exec python-ai netstat -tulpn | grep :8000 2>/dev/null || echo "❌ Porta 8000 não está sendo escutada"
echo

# Testa endpoint direto na porta exposta
echo "🌐 Testando endpoint direto na porta exposta:"
curl -s --max-time 5 http://localhost:8000/health || echo "❌ Endpoint externo não acessível"
echo

# Verifica variáveis de ambiente
echo "⚙️ Variáveis de ambiente do container aleen-ia:"
docker exec aleen-ia env | grep -E "(PYTHON_AI|REDIS|OPENAI)" | sort
echo

# Verifica se o processo FastAPI está rodando
echo "🐍 Verificando processo Python no container:"
docker exec python-ai ps aux | grep -E "(python|fastapi|uvicorn)" || echo "❌ Processo Python não encontrado"
echo

echo "🏁 Diagnóstico concluído!"
echo
echo "🔧 SOLUÇÕES POSSÍVEIS:"
echo "========================"
echo
echo "1. 🐍 Se o Python AI não estiver iniciando:"
echo "   docker-compose restart python-ai"
echo "   docker-compose logs -f python-ai"
echo
echo "2. 🌐 Se há problema de rede entre containers:"
echo "   docker-compose down"
echo "   docker-compose up -d"
echo
echo "3. 🏥 Se o container está unhealthy:"
echo "   docker exec python-ai curl http://localhost:8000/health"
echo "   docker exec python-ai ps aux"
echo
echo "4. 🔄 Rebuild completo se necessário:"
echo "   docker-compose down --volumes"
echo "   docker-compose build --no-cache python-ai"
echo "   docker-compose up -d"
echo
echo "5. 🐞 Debug detalhado:"
echo "   docker exec -it python-ai /bin/bash"
echo "   docker exec -it aleen-ia /bin/bash"
