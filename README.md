# Aleen AI - Sistema de Agentes Inteligentes

Sistema de agentes de IA para automação de atendimento via WhatsApp com foco em fitness e nutrição.

## 🚀 Funcionalidades

### ✅ Implementadas
- **Sistema Multi-Agentes**: Onboarding, Sales, Support e Out-of-Context
- **Integração WhatsApp**: Via Evolution API com quebra automática de mensagens
- **Memória de Conversas**: Armazenamento Redis com TTL de 7 dias
- **Onboarding Inteligente**: Perguntas dinâmicas do banco de dados
- **Criação de Usuários**: Registro automático com autenticação Supabase
- **Tools Integradas**: Busca de perguntas e criação de usuários
- **Gerenciamento de Leads**: Vinculação automática de leads a usuários

### 🎯 Agentes Especializados
1. **Onboarding Agent**: Boas-vindas e apresentação do app
2. **Sales Agent**: Conversão e vendas consultivas
3. **Support Agent**: Suporte técnico e dúvidas sobre o app
4. **Out-of-Context Agent**: Redirecionamento para tópicos relevantes

## 📋 Pré-requisitos

- Python 3.9+
- Redis Server
- Conta Supabase
- Evolution API configurada
- OpenAI API Key

## 🔧 Instalação

1. **Clone o repositório**:
```bash
git clone https://github.com/loggicdev/aleen-ai.git
cd aleen-ai
```

2. **Instale as dependências**:
```bash
pip install -r requirements.txt
```

3. **Configure as variáveis de ambiente**:
```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

4. **Execute o servidor**:
```bash
python3 main.py
```

## ⚙️ Configuração

### Variáveis de Ambiente Obrigatórias

```env
# OpenAI
OPENAI_API_KEY=sk-your-openai-key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Redis
REDIS_URL=redis://localhost:6380

# Evolution API
EVOLUTION_API_BASE_URL=https://your-evolution-api.com
EVOLUTION_API_KEY=your-api-key
EVOLUTION_INSTANCE=your-instance-name
```

### Estrutura do Banco de Dados

O sistema requer as seguintes tabelas no Supabase:
- `agents` - Configuração dos agentes
- `onboarding_questions` - Perguntas do onboarding
- `onboarding_responses` - Respostas dos usuários
- `users` - Dados dos usuários
- `leads` - Gerenciamento de leads

## 🌐 Endpoints da API

### POST `/whatsapp-chat`
Processa mensagens do WhatsApp com contexto completo
```json
{
  "user_id": "temp-id",
  "user_name": "João Silva", 
  "phone_number": "5511999888777",
  "message": "Olá, quero conhecer o app",
  "send_to_whatsapp": true
}
```

### POST `/chat`
Endpoint básico para teste sem WhatsApp
```json
{
  "user_id": "test-user",
  "user_name": "Test User",
  "message": "Hello",
  "recommended_agent": "onboarding"
}
```

### GET `/health`
Health check completo do sistema

### GET `/agents`
Lista todos os agentes carregados

## 🔄 Fluxo de Onboarding

1. **Usuário inicia conversa** → Agente Onboarding
2. **Interesse demonstrado** → Tool `get_onboarding_questions`
3. **Perguntas apresentadas** → Usuário responde (nome, idade, email)
4. **Dados coletados** → Tool `create_user_and_save_onboarding`
5. **Conta criada** → Credenciais enviadas via WhatsApp
6. **Lead atualizado** → Usuário vinculado e marcado como convertido

## 🛠️ Tools Disponíveis

### `get_onboarding_questions`
Busca perguntas configuradas no banco para WhatsApp
- Filtra por `send_in = 'whatsapp'` e `is_active = true`
- Ordena por `step_number`

### `create_user_and_save_onboarding`
Cria usuário completo com autenticação
- Gera senha temporária segura
- Cria registro em `auth.users` via REST API
- Trigger automático cria registro em `public.users`
- Salva respostas de onboarding
- Vincula e atualiza leads existentes

## 🧠 Sistema de Memória

- **Armazenamento**: Redis com chave `user_memory:{phone}`
- **TTL**: 7 dias (604800 segundos)
- **Capacidade**: Últimas 20 mensagens por usuário
- **Contexto**: 2000 caracteres máximo por requisição

## 🚀 Deploy

### Docker
```bash
docker build -t aleen-ai .
docker run -p 9000:9000 --env-file .env aleen-ai
```

### Scripts Disponíveis
- `restart-python-ai.sh` - Reinicia o serviço
- `diagnose-python-ai.sh` - Diagnóstico do sistema
- `fix-python-ai.sh` - Correções automáticas

## 📊 Monitoramento

### Health Check
- **URL**: `GET /health`
- **Verifica**: Redis, OpenAI, Supabase, Agentes carregados
- **Status**: 200 (healthy) ou 503 (unhealthy)

### Logs
- Formato estruturado com emojis para facilitar debugging
- Log de execução de tools com argumentos
- Rastreamento de fluxo de agentes
- Métricas de memória e contexto

## 🔧 Troubleshooting

Consulte `TROUBLESHOOTING-PYTHON-AI.md` para problemas comuns e soluções.

## 📝 Licença

Este projeto está sob licença proprietária da Loggic Dev.

## 🤝 Contribuição

Para contribuir com o projeto, entre em contato com a equipe de desenvolvimento.
