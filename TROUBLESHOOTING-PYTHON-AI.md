# 🚨 Troubleshooting: Erro "getaddrinfo ENOTFOUND python-ai" na VPS

## Problema
O serviço TypeScript na VPS não consegue conectar com o serviço Python AI, resultando no erro:
```
getaddrinfo ENOTFOUND python-ai
```

## Soluções

### 1. 🔍 Diagnóstico Completo
Execute o script de diagnóstico para identificar o problema:
```bash
./diagnose-python-ai.sh
```

### 2. 🔄 Reinício do Serviço Python AI
Se o serviço estiver parado ou com problemas:
```bash
./restart-python-ai.sh
```

### 3. 📋 Verificação Manual

#### Verificar containers rodando:
```bash
docker ps
```

#### Verificar logs do Python AI:
```bash
docker logs python-ai
```

#### Testar conectividade interna:
```bash
docker exec aleen-ia curl http://python-ai:8000/health
```

#### Testar conectividade externa:
```bash
curl http://localhost:8000/health
```

### 4. 🏗️ Rebuild Completo (se necessário)
```bash
# Para todos os serviços
docker-compose down

# Remove imagens antigas
docker image prune -f

# Reconstrói e inicia
docker-compose up -d --build
```

## Novos Recursos Implementados

### ✨ Fallback Inteligente
- O sistema agora detecta quando o Python AI está offline
- Envia mensagem informativa para o usuário explicando a manutenção
- Não deixa o usuário sem resposta

### 🏥 Health Check Robusto
- Novo endpoint `/health` testa todas as dependências:
  - Redis
  - OpenAI API
  - Supabase
  - Agentes carregados
- Retorna status detalhado de cada componente

### 📊 Monitoramento Aprimorado
- Logs mais detalhados sobre problemas de conectividade
- Distinção entre diferentes tipos de erro
- Métricas de saúde do serviço

## Prevenção

### 🔧 Monitoramento Contínuo
```bash
# Monitore logs em tempo real
docker-compose logs -f python-ai

# Verifique status periodicamente
watch -n 30 'docker exec aleen-ia curl -s http://python-ai:8000/health'
```

### ⚙️ Configuração de Auto-restart
O `docker-compose.yml` já inclui `restart: unless-stopped` para todos os serviços.

### 🚨 Alertas
Configure alertas para monitorar:
- Status dos containers Docker
- Response time do endpoint `/health`
- Logs de erro nos serviços

## Contato
Se o problema persistir, verifique:
1. Configuração de rede Docker
2. Variáveis de ambiente
3. Recursos do servidor (CPU/RAM)
4. Quotas da OpenAI API
