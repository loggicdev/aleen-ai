# Aleen IA - Python AI Service

## 🤖 **Serviço de IA em Python**

Serviço independente responsável pelo processamento de mensagens com OpenAI GPT-4, gerenciamento de agentes inteligentes e integração com Supabase.

### � **Funcionalidades**

- **OpenAI GPT-4**: Processamento avançado de mensagens
- **Sistema de Agentes**: onboarding, sales, support, out_context
- **Supabase Integration**: Carregamento dinâmico de prompts
- **Redis Caching**: Cache de contexto de usuários
- **Evolution API**: Envio direto de mensagens WhatsApp
- **Health Checks**: Monitoramento completo

### 📡 API Endpoints

#### Core Endpoints
- `POST /chat` - Processa mensagem com IA
- `POST /whatsapp-chat` - Processa + envia WhatsApp
- `POST /send-whatsapp` - Envio direto WhatsApp
- `GET /health` - Health check completo

#### Management Endpoints
- `GET /agents` - Lista agentes disponíveis
- `POST /reload-agents` - Recarrega agentes do Supabase
- `GET /agents/config` - Configuração dos agentes

### 🔧 Configuração

#### Variáveis de Ambiente
```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Redis
REDIS_URL=redis://redis:6379

# Supabase
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_ANON_KEY=eyJ...

# Evolution API
EVOLUTION_API_BASE_URL=https://...
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE=...
```

### 🐳 Docker

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

### 🚀 Deploy

1. **Local**: `python main.py`
2. **Docker**: `docker build -t aleen-ai-python . && docker run -p 8000:8000 aleen-ai-python`
3. **Dokploy**: Configure como serviço independente

### 📊 Monitoramento

- Health check: `GET /health`
- Logs estruturados com emojis
- Métricas de performance nos endpoints

### 🔄 **Integração com Node.js**

O serviço Node.js se comunica via HTTP:

**Produção**: `https://ai-aleen.live.claudy.host`  
**Local**: `http://localhost:8000`

```bash
# Exemplo de requisição
curl -X POST https://ai-aleen.live.claudy.host/chat 
  -H "Content-Type: application/json" 
  -d '{
    "user_id": "user_123",
    "user_name": "João", 
    "message": "Olá!",
    "conversation_history": []
  }'
```
