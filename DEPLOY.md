# 🚀 Deploy Aleen IA Node.js - Dokploy

## 📋 Pré-requisitos

- Dokploy instalado e configurado
- Repositório Git: `https://github.com/loggicdev/aleen-ia`
- Domínio configurado (opcional)

## 🔧 Configuração no Dokploy

### 1. Criar Nova Aplicação

1. Acesse o painel do Dokploy
2. Clique em "New Application"
3. Selecione "Git Repository"
4. Cole a URL: `https://github.com/loggicdev/aleen-ia`
5. Branch: `main`
6. Build Context: `/node` (importante!)

### 2. Configurar Build

```yaml
# Build Command
npm ci && npm run build

# Start Command  
npm start

# Port
3000

# Dockerfile Path
./Dockerfile
```

### 3. Variáveis de Ambiente

Configure as seguintes variáveis no painel do Dokploy:

```env
# Servidor
NODE_ENV=production
PORT=3000

# Redis (usar serviço Redis do Dokploy)
REDIS_URL=redis://redis:6379

# Python AI Service
PYTHON_AI_BASE_URL=http://python-ai:8000

# Evolution API
EVOLUTION_API_BASE_URL=https://evo-iafit.live.claudy.host
EVOLUTION_API_KEY=20414AF89B46-4C4F-A49C-58285CF2F44A
EVOLUTION_INSTANCE=aleen

# Supabase
SUPABASE_URL=https://qzzeewrkdruavnnecypl.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF6emVld3JrZHJ1YXZubmVjeXBsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI0NDQ0NDQsImV4cCI6MjA2ODAyMDQ0NH0.-SBE14H0vUeNtUmDiaStAN30dmFcQCHuO-QMAV0nyb0

# Webhook
WEBHOOK_SECRET=your-webhook-secret-here

# Logs
LOG_LEVEL=info
LOG_FORMAT=json
```

### 4. Serviços Dependentes

#### Redis
1. No Dokploy, adicione um serviço Redis:
   - Type: `Redis`
   - Name: `redis`
   - Port: `6379`
   - Network: Mesma rede da aplicação

#### Python AI (Opcional)
Se quiser incluir o serviço Python:
1. Criar segunda aplicação para `/python`
2. Configurar na mesma rede
3. Ajustar `PYTHON_AI_BASE_URL`

### 5. Networking

Certifique-se de que todos os serviços estão na mesma rede Docker para comunicação interna.

### 6. Domínio (Opcional)

Configure um domínio personalizado:
- Exemplo: `api-aleen.yourdomain.com`
- SSL automático via Let's Encrypt
- Proxy reverso automático

## 🔍 Verificação de Deploy

### Health Checks

```bash
# Verificar se a API está respondendo
curl https://your-domain.com/api/webhook/health

# Resposta esperada:
{
  "success": true,
  "message": "Aleen IA is running",
  "timestamp": "2025-08-12T...",
  "version": "1.0.0"
}
```

### Logs

Monitore os logs no painel do Dokploy para:
- ✅ "Aleen IA started successfully"
- ✅ "Supabase client initialized" 
- ✅ "Redis connected successfully"

### Teste de Webhook

```bash
curl -X POST https://your-domain.com/api/webhook/evolution \
  -H 'Content-Type: application/json' \
  -d '{
    "event": "messages.upsert",
    "instance": "aleen",
    "data": {
      "key": {
        "remoteJid": "5511999999999@s.whatsapp.net",
        "fromMe": false,
        "id": "test123"
      },
      "pushName": "Teste",
      "message": {
        "conversation": "Teste de webhook"
      },
      "messageType": "conversation",
      "messageTimestamp": 1691848800,
      "instanceId": "aleen",
      "source": "android"
    },
    "apikey": "20414AF89B46-4C4F-A49C-58285CF2F44A"
  }'
```

## 🚨 Troubleshooting

### Problema: Redis Connection Failed
```bash
# Verificar se o Redis está na mesma rede
docker network ls
docker network inspect dokploy_default
```

### Problema: Build Failed
```bash
# Verificar se o Build Context está correto: /node
# Verificar se o Dockerfile está na raiz do contexto
```

### Problema: Environment Variables
```bash
# Verificar se todas as variáveis estão configuradas
# Verificar sintaxe das URLs (sem barra final)
```

## 📊 Monitoramento

### Métricas Importantes
- Response Time da API
- Status do Redis
- Logs de erro
- Webhooks processados
- Memory/CPU usage

### Alertas Recomendados
- API Health Check falhando
- Redis desconectado
- High memory usage
- Error rate > 5%

## 🔄 Atualizações

Para atualizar o projeto:
1. Push para branch `main`
2. Dokploy detecta automaticamente
3. Build e deploy automático
4. Zero downtime deployment

## 📞 Suporte

Em caso de problemas:
1. Verificar logs no painel Dokploy
2. Testar health checks
3. Validar configurações de rede
4. Contatar equipe de desenvolvimento
