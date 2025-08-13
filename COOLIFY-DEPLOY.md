# Aleen AI - Coolify Deploy Configuration

## 🚀 Deploy no Coolify

### 1. Configuração Básica
- **Repository**: https://github.com/loggicdev/aleen-ai.git
- **Branch**: main
- **Build Pack**: Docker
- **Port**: 8000

### 2. Variáveis de Ambiente Obrigatórias

Configure as seguintes variáveis no Coolify:

```bash
# OpenAI
OPENAI_API_KEY=sk-your-openai-key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Evolution API
EVOLUTION_API_BASE_URL=https://your-evolution-api.com
EVOLUTION_API_KEY=your-api-key
EVOLUTION_INSTANCE=your-instance-name

# Application (opcional)
PORT=8000
ENVIRONMENT=production
```

### 3. Redis Configuration

O Redis está incluído no docker-compose.yml. Para Coolify:
- **Serviço**: Redis será criado automaticamente
- **URL**: `redis://redis:6379` (interno do container)
- **Persistent Volume**: Configurado para `/data`

### 4. Health Check

- **Endpoint**: `/health`
- **Interval**: 30s
- **Timeout**: 10s
- **Retries**: 3

### 5. Deploy Steps

1. **Criar novo projeto no Coolify**
2. **Conectar o repositório GitHub**
3. **Configurar variáveis de ambiente**
4. **Fazer deploy**

### 6. Comandos Docker Manuais (se necessário)

```bash
# Build
docker build -t aleen-ai .

# Run with compose
docker-compose up -d

# View logs
docker-compose logs -f aleen-ai

# Stop
docker-compose down
```

### 7. Monitoramento

- **Health Check**: http://your-domain.com/health
- **Logs**: Acessíveis via Coolify dashboard
- **Metrics**: Redis e application metrics disponíveis

### 8. Troubleshooting

Se houver problemas:

1. **Verificar logs**: `docker-compose logs aleen-ai`
2. **Verificar Redis**: `docker-compose logs redis`
3. **Testar health**: `curl http://localhost:8000/health`
4. **Restart**: `docker-compose restart aleen-ai`

### 9. Recursos Recomendados

- **CPU**: 1-2 cores
- **RAM**: 1-2 GB
- **Storage**: 10 GB
- **Network**: 1 Gbps

### 10. Security

- Container roda com usuário não-root
- Health checks configurados
- Redis com política de memória configurada
- Logs estruturados para auditoria
