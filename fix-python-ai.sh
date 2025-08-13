#!/bin/bash

echo "🔧 Auto-reparo do Serviço Python AI"
echo "==================================="
echo

# Função para verificar se container está rodando
check_container() {
    local container_name=$1
    if docker ps | grep -q "$container_name"; then
        echo "✅ Container $container_name está rodando"
        return 0
    else
        echo "❌ Container $container_name NÃO está rodando"
        return 1
    fi
}

# Função para verificar health check
check_health() {
    local container_name=$1
    local health_status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "none")
    if [ "$health_status" = "healthy" ]; then
        echo "✅ Container $container_name está healthy"
        return 0
    else
        echo "❌ Container $container_name health status: $health_status"
        return 1
    fi
}

# Função para testar conectividade
test_connectivity() {
    echo "🌐 Testando conectividade..."
    if docker exec aleen-ia curl -s --max-time 3 http://python-ai:8000/health > /dev/null 2>&1; then
        echo "✅ Conectividade OK: aleen-ia -> python-ai"
        return 0
    else
        echo "❌ Falha na conectividade: aleen-ia -> python-ai"
        return 1
    fi
}

echo "📋 DIAGNÓSTICO INICIAL:"
echo "======================="

# Verificar se os containers existem e estão rodando
check_container "redis"
REDIS_OK=$?

check_container "python-ai"
PYTHON_AI_OK=$?

check_container "aleen-ia"
ALEEN_OK=$?

echo

# Verificar health checks
if [ $REDIS_OK -eq 0 ]; then
    check_health "redis"
fi

if [ $PYTHON_AI_OK -eq 0 ]; then
    check_health "python-ai"
fi

if [ $ALEEN_OK -eq 0 ]; then
    check_health "aleen-ia"
fi

echo

# Testar conectividade se containers estão rodando
if [ $PYTHON_AI_OK -eq 0 ] && [ $ALEEN_OK -eq 0 ]; then
    test_connectivity
    CONNECTIVITY_OK=$?
else
    CONNECTIVITY_OK=1
fi

echo
echo "🔧 INICIANDO REPARO AUTOMÁTICO:"
echo "==============================="

# Se tudo estiver OK, não fazer nada
if [ $REDIS_OK -eq 0 ] && [ $PYTHON_AI_OK -eq 0 ] && [ $ALEEN_OK -eq 0 ] && [ $CONNECTIVITY_OK -eq 0 ]; then
    echo "✅ Tudo funcionando corretamente! Nenhum reparo necessário."
    exit 0
fi

# Estratégia 1: Restart suave dos containers problemáticos
echo
echo "🔄 Estratégia 1: Restart suave..."
if [ $PYTHON_AI_OK -ne 0 ] || [ $CONNECTIVITY_OK -ne 0 ]; then
    echo "  Reiniciando python-ai..."
    docker-compose restart python-ai
    sleep 10
fi

if [ $ALEEN_OK -ne 0 ]; then
    echo "  Reiniciando aleen-ia..."
    docker-compose restart aleen-ia
    sleep 10
fi

# Testar novamente
echo
echo "🧪 Testando após restart suave..."
check_container "python-ai"
PYTHON_AI_OK=$?

check_container "aleen-ia"
ALEEN_OK=$?

if [ $PYTHON_AI_OK -eq 0 ] && [ $ALEEN_OK -eq 0 ]; then
    sleep 5
    test_connectivity
    CONNECTIVITY_OK=$?
    
    if [ $CONNECTIVITY_OK -eq 0 ]; then
        echo "✅ Problema resolvido com restart suave!"
        exit 0
    fi
fi

# Estratégia 2: Down/Up completo
echo
echo "🔄 Estratégia 2: Restart completo..."
echo "  Parando todos os containers..."
docker-compose down

echo "  Aguardando 5 segundos..."
sleep 5

echo "  Iniciando containers..."
docker-compose up -d

echo "  Aguardando containers iniciarem..."
sleep 20

# Testar novamente
echo
echo "🧪 Testando após restart completo..."
check_container "python-ai"
PYTHON_AI_OK=$?

check_container "aleen-ia"
ALEEN_OK=$?

if [ $PYTHON_AI_OK -eq 0 ] && [ $ALEEN_OK -eq 0 ]; then
    sleep 10
    test_connectivity
    CONNECTIVITY_OK=$?
    
    if [ $CONNECTIVITY_OK -eq 0 ]; then
        echo "✅ Problema resolvido com restart completo!"
        exit 0
    fi
fi

# Estratégia 3: Rebuild do python-ai
echo
echo "🔄 Estratégia 3: Rebuild do python-ai..."
echo "  Parando containers..."
docker-compose down

echo "  Fazendo rebuild do python-ai..."
docker-compose build --no-cache python-ai

echo "  Iniciando containers..."
docker-compose up -d

echo "  Aguardando containers iniciarem..."
sleep 30

# Teste final
echo
echo "🧪 Teste final..."
check_container "python-ai"
PYTHON_AI_OK=$?

check_container "aleen-ia"
ALEEN_OK=$?

if [ $PYTHON_AI_OK -eq 0 ] && [ $ALEEN_OK -eq 0 ]; then
    sleep 10
    test_connectivity
    CONNECTIVITY_OK=$?
    
    if [ $CONNECTIVITY_OK -eq 0 ]; then
        echo "✅ Problema resolvido com rebuild!"
        exit 0
    fi
fi

echo
echo "❌ FALHA NO REPARO AUTOMÁTICO"
echo "============================="
echo "O problema persiste após todas as tentativas."
echo "Recomendações para investigação manual:"
echo
echo "1. Verificar logs detalhados:"
echo "   docker-compose logs python-ai"
echo "   docker-compose logs aleen-ia"
echo
echo "2. Verificar configuração do Dockerfile.python:"
echo "   cat Dockerfile.python"
echo
echo "3. Verificar se as variáveis de ambiente estão corretas"
echo
echo "4. Entrar no container para debug:"
echo "   docker exec -it python-ai /bin/bash"
echo
echo "5. Verificar se as dependências Python estão instaladas:"
echo "   docker exec python-ai pip list"

exit 1
