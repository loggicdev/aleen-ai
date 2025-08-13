# Aleen AI - Coolify Deploy Configuration

## 🚀 Deploy no Coolify

### 1. Configuração Básica
- **Repository**: https://github.com/loggicdev/aleen-ai.git
- **Branch**: main
- **Build Pack**: Docker
- **Port**: 9000

### 2. Variáveis de Ambiente Obrigatórias

Configure as seguintes variáveis no Coolify:

```bash
# OpenAI
OPENAI_API_KEY=sk-your-openai-key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Redis Cloud (External)
REDIS_HOST=fo8400okko0gckwcw8gksscc
REDIS_PORT=6379
REDIS_USERNAME=default
REDIS_PASSWORD=4sBBfBGYfo26H9PYa65sFVBxxK848fPEdgUgGVMp5BcurxpSUKJuz23jTHIkdilD
REDIS_DB=0

# Evolution API
EVOLUTION_API_BASE_URL=https://your-evolution-api.com
EVOLUTION_API_KEY=your-api-key
EVOLUTION_INSTANCE=your-instance-name

# Application (opcional)
PORT=9000
ENVIRONMENT=production
```

### 3. Redis Configuration

O projeto usa **Redis Cloud externo** (mesmo do projeto Node):
- **Host**: fo8400okko0gckwcw8gksscc
- **Port**: 6379  
- **Username**: default
- **Password**: [configurado via variáveis]
- **Database**: 0
- **Network**: coolify (externa)

**Importante para Coolify**: 
- Usa Redis Cloud compartilhado entre projetos Node e Python
- Configurado via variáveis REDIS_HOST, REDIS_PORT, REDIS_USERNAME, REDIS_PASSWORD
- Fallback automático para Redis local em desenvolvimento
- Network externa "coolify" para comunicação entre serviços

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
3. **Testar health**: `curl http://localhost:9000/health`
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
