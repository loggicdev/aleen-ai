import os
import re
import time
import sys
import json
import requests
import secrets
import string
import traceback
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from agents import Agent, Runner
from typing import List, Optional, Dict
import redis
from dotenv import load_dotenv
from supabase import create_client, Client

# Force stdout to be unbuffered for Docker logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

load_dotenv()

app = FastAPI(title="Aleen AI Agents", version="1.0.0")

# Redis connection with retry mechanism
def connect_redis_with_retry(max_retries=10, delay=3):
    for attempt in range(max_retries):
        try:
            # Priorizar variáveis de ambiente individuais (mesmo padrão do Node.js)
            redis_host = os.getenv("REDIS_HOST")
            redis_port = os.getenv("REDIS_PORT")
            redis_username = os.getenv("REDIS_USERNAME", "default")
            redis_password = os.getenv("REDIS_PASSWORD")
            redis_db = int(os.getenv("REDIS_DB", "0"))
            
            if redis_host and redis_password:
                # Configuração individual (preferida) - Redis Cloud
                print(f"🔍 Tentativa {attempt + 1}/{max_retries} - Redis individual config:")
                print(f"   Host: {redis_host}")
                print(f"   Port: {redis_port}")
                print(f"   Username: {redis_username}")
                print(f"   Password length: {len(redis_password) if redis_password else 0}")
                print(f"   DB: {redis_db}")
                
                redis_client = redis.Redis(
                    host=redis_host,
                    port=int(redis_port) if redis_port else 6379,
                    username=redis_username,
                    password=redis_password,
                    db=redis_db,
                    decode_responses=True,
                    socket_timeout=10,
                    socket_connect_timeout=10,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    retry_on_timeout=True,
                    health_check_interval=30
                )
            else:
                # Fallback para URL-based configuration
                redis_url = os.getenv("REDIS_URL")
                if not redis_url:
                    # Auto-detecta ambiente
                    if os.getenv("ENVIRONMENT") == "production" or os.path.exists("/.dockerenv"):
                        redis_url = "redis://redis:6379"
                    else:
                        redis_url = "redis://localhost:6380"
                
                print(f"🔍 Tentativa {attempt + 1}/{max_retries} - Redis URL config: {redis_url}")
                
                redis_client = redis.from_url(
                    redis_url, 
                    decode_responses=True, 
                    socket_timeout=10, 
                    socket_connect_timeout=10,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
            
            # Test connection
            redis_client.ping()
            print("✅ Redis conectado com sucesso")
            return redis_client
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Tentativa {attempt + 1}/{max_retries} - Erro ao conectar Redis: {e}")
                print(f"🔄 Tentando novamente em {delay} segundos...")
                time.sleep(delay)
            else:
                print(f"❌ Falha ao conectar Redis após {max_retries} tentativas: {e}")
                print("🔧 Usando cliente Redis mock para desenvolvimento")
                # Create a mock Redis client for development
                class MockRedis:
                    def get(self, key): 
                        print(f"📝 MockRedis.get({key}) -> None")
                        return None
                    def setex(self, key, time, value): 
                        print(f"📝 MockRedis.setex({key}, {time}, [value])")
                        pass
                    def ping(self): 
                        return True
                    def delete(self, key):
                        print(f"📝 MockRedis.delete({key})")
                        pass
                return MockRedis()

redis_client = connect_redis_with_retry()

# Funções para gerenciar memória do usuário
def get_user_memory(phone_number: str) -> List[str]:
    """Recupera a memória/histórico do usuário baseado no número de telefone"""
    try:
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        memory_key = f"user_memory:{clean_phone}"
        
        memory_data = redis_client.get(memory_key)
        if memory_data:
            # Como decode_responses=True, memory_data já é uma string
            import json
            return json.loads(memory_data)
        return []
    except Exception as e:
        print(f"⚠️ Erro ao recuperar memória do usuário {phone_number}: {e}")
        return []

def save_user_memory(phone_number: str, conversation_history: List[str], max_messages: int = 20):
    """Salva a memória/histórico do usuário baseado no número de telefone"""
    try:
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        memory_key = f"user_memory:{clean_phone}"
        
        # Mantém apenas as últimas max_messages mensagens para não sobrecarregar
        if len(conversation_history) > max_messages:
            conversation_history = conversation_history[-max_messages:]
        
        # Salva como JSON com TTL de 7 dias (604800 segundos)
        import json
        redis_client.setex(memory_key, 604800, json.dumps(conversation_history, ensure_ascii=False))
        
        print(f"💾 Memória salva para {clean_phone}: {len(conversation_history)} mensagens")
    except Exception as e:
        print(f"⚠️ Erro ao salvar memória do usuário {phone_number}: {e}")

def add_to_user_memory(phone_number: str, user_message: str, ai_response: str):
    """Adiciona uma nova interação à memória do usuário"""
    try:
        # Recupera memória existente
        memory = get_user_memory(phone_number)
        
        # Adiciona nova interação
        memory.append(f"Usuário: {user_message}")
        memory.append(f"Aleen: {ai_response}")
        
        # Salva memória atualizada
        save_user_memory(phone_number, memory)
        
    except Exception as e:
        print(f"⚠️ Erro ao adicionar à memória do usuário {phone_number}: {e}")

def get_conversation_context(phone_number: str, current_message: str, max_context_length: int = 2000) -> str:
    """Gera contexto da conversa para enviar à IA"""
    try:
        memory = get_user_memory(phone_number)
        
        # Se não há memória, retorna apenas a mensagem atual
        if not memory:
            return current_message
        
        # Constrói o contexto
        context_parts = []
        context_parts.extend(memory[-10:])  # Últimas 10 mensagens da memória
        context_parts.append(f"Usuário: {current_message}")
        
        full_context = "\n".join(context_parts)
        
        # Se o contexto for muito longo, corta mantendo as mensagens mais recentes
        if len(full_context) > max_context_length:
            # Tenta com menos mensagens
            context_parts = memory[-6:] + [f"Usuário: {current_message}"]
            full_context = "\n".join(context_parts)
            
            if len(full_context) > max_context_length:
                # Se ainda for muito longo, corta o texto
                full_context = full_context[-max_context_length:]
        
        return full_context
        
    except Exception as e:
        print(f"⚠️ Erro ao gerar contexto para {phone_number}: {e}")
        return current_message

# OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Supabase client
supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Supabase URL and key are required")

supabase: Client = create_client(supabase_url, supabase_key)

# Tools para os agentes
def get_user_id_by_phone(phone: str) -> str:
    """
    Busca o user_id de um usuário baseado no número de telefone
    Retorna None se não encontrar
    """
    try:
        clean_phone = re.sub(r'[^\d]', '', phone)
        response = supabase.table('users').select('id').eq('phone', clean_phone).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]['id']
        return None
        
    except Exception as e:
        print(f"❌ Erro ao buscar user_id por telefone {phone}: {e}")
        return None

def get_onboarding_questions() -> dict:
    """
    Busca as perguntas de onboarding do banco de dados
    Retorna apenas perguntas configuradas para WhatsApp
    """
    try:
        response = supabase.table('onboarding_questions').select('*').eq('send_in', 'whatsapp').eq('is_active', True).order('step_number').execute()
        
        if not response.data:
            return {
                "success": False,
                "message": "Nenhuma pergunta encontrada",
                "questions": []
            }
        
        questions = []
        for question in response.data:
            questions.append({
                "id": question.get('id'),
                "step": question.get('step_number'),
                "question": question.get('title', ''),
                "subtitle": question.get('subtitle', ''),
                "type": question.get('question_type', 'text'),
                "field_name": question.get('field_name', ''),
                "required": question.get('required', True),
                "options": question.get('options', []),
                "emoji": question.get('emoji', ''),
                "placeholder": question.get('placeholder', '')
            })
        
        return {
            "success": True,
            "message": f"Encontradas {len(questions)} perguntas",
            "questions": questions
        }
        
    except Exception as e:
        print(f"❌ Erro ao buscar perguntas de onboarding: {e}")
        return {
            "success": False,
            "message": f"Erro ao buscar perguntas: {str(e)}",
            "questions": []
        }

def create_user_and_save_onboarding(name: str, age: str, email: str, phone: str) -> dict:
    """
    Cria um usuário com autenticação usando Supabase Auth REST API,
    salva na tabela users e registra respostas de onboarding
    Args:
        name: Nome do usuário
        age: Idade do usuário  
        email: Email do usuário
        phone: Telefone do usuário
    """
    try:
        print(f"🔧 Criando usuário: {name}, {age}, {email}, {phone}")
        
        # 1. Gerar senha temporária segura
        import secrets
        import string
        temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits + "!@#$%") for i in range(16))
        
        # 2. Criar usuário usando Supabase Auth REST API diretamente
        print(f"🔐 Criando usuário via Auth REST API...")
        
        try:
            import requests
            
            # URL da API de signup do Supabase
            auth_url = f"{supabase_url}/auth/v1/signup"
            
            # Headers para a requisição
            headers = {
                "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY')}"
            }
            
            # Dados do usuário
            auth_data = {
                "email": email,
                "password": temp_password,
                "data": {
                    "name": name,
                    "age": age,
                    "created_via": "whatsapp_onboarding"
                }
            }
            
            print(f"📡 Enviando requisição para: {auth_url}")
            print(f"📋 Dados: email={email}, password=[HIDDEN]")
            
            # Fazer a requisição
            response = requests.post(auth_url, json=auth_data, headers=headers, timeout=30)
            
            print(f"📊 Status da resposta: {response.status_code}")
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data.get('user') and response_data['user'].get('id'):
                    user_id = response_data['user']['id']
                    print(f"✅ Usuário criado na auth com ID: {user_id}")
                else:
                    print(f"⚠️ Resposta inesperada da Auth API: {response_data}")
                    return {
                        "success": False,
                        "message": "Resposta inesperada da API de autenticação",
                        "user_id": None,
                        "details": str(response_data)
                    }
            else:
                error_msg = response.text
                print(f"❌ Erro HTTP {response.status_code}: {error_msg}")
                return {
                    "success": False,
                    "message": f"Erro HTTP {response.status_code} ao criar usuário",
                    "user_id": None,
                    "details": error_msg
                }
                
        except Exception as auth_error:
            print(f"❌ Erro na criação via Auth REST API: {auth_error}")
            print(f"📋 Dados enviados: email={email}, phone={phone}")
            print(f"🔍 Auth URL: {auth_url}")
            print(f"🔑 Headers: {headers}")
            return {
                "success": False,
                "message": f"Erro na autenticação: {str(auth_error)}",
                "user_id": None
            }
        
        # 3. O trigger handle_new_user criará automaticamente o registro em public.users
        # Vamos aguardar um momento para o trigger executar e depois atualizar com informações adicionais
        try:
            import time
            time.sleep(1)  # Aguarda o trigger executar
            
            # Atualiza o registro criado pelo trigger com informações adicionais
            user_update_data = {
                "name": name,
                "phone": phone,
                "nickname": name  # Usa o nome como nickname inicial
            }
            
            user_response = supabase.table('users').update(user_update_data).eq('id', user_id).execute()
            
            if not user_response.data:
                print("⚠️ Usuário criado na auth, mas erro ao atualizar informações na tabela users")
                # Mesmo assim, continuamos pois o usuário foi criado
            else:
                print(f"✅ Informações do usuário atualizadas na tabela users")
            
        except Exception as user_error:
            print(f"❌ Erro ao atualizar informações na tabela users: {user_error}")
            # Não retornamos erro aqui, pois o usuário foi criado com sucesso na auth
        
        # 4. Buscar as perguntas básicas de onboarding (nome, idade, email)
        try:
            questions_response = supabase.table('onboarding_questions').select('*').eq('send_in', 'whatsapp').eq('is_active', True).in_('field_name', ['name', 'age', 'email']).execute()
            
            if not questions_response.data:
                print("⚠️ Perguntas de onboarding não encontradas, mas usuário foi criado")
            else:
                # 5. Salvar respostas na tabela onboarding_responses
                responses_data = []
                for question in questions_response.data:
                    field_name = question.get('field_name')
                    response_value = ""
                    
                    if field_name == 'name':
                        response_value = name
                    elif field_name == 'age':
                        response_value = age
                    elif field_name == 'email':
                        response_value = email
                        
                    if response_value:
                        responses_data.append({
                            "user_id": user_id,
                            "question_id": question.get('id'),
                            "response_value": response_value
                        })
                
                if responses_data:
                    responses_response = supabase.table('onboarding_responses').insert(responses_data).execute()
                    
                    if responses_response.data:
                        print(f"✅ {len(responses_data)} respostas de onboarding salvas")
                    else:
                        print("⚠️ Erro ao salvar respostas de onboarding, mas usuário foi criado")
                        
        except Exception as questions_error:
            print(f"⚠️ Erro ao processar perguntas de onboarding: {questions_error}")
        
        # 6. Atualizar lead se existir
        try:
            lead_response = supabase.table('leads').select('id').eq('phone', phone).execute()
            if lead_response.data:
                lead_id = lead_response.data[0]['id']
                supabase.table('leads').update({
                    "user_id": user_id,
                    "onboarding_concluido": True
                }).eq('id', lead_id).execute()
                print(f"✅ Lead atualizado para usuário {user_id}")
        except Exception as lead_error:
            print(f"⚠️ Erro ao atualizar lead: {lead_error}")
        
        return {
            "success": True,
            "message": f"🎉 Conta criada com sucesso!\n\n📧 Email: {email}\n🔑 Senha temporária: {temp_password}\n\nVocê já pode fazer login no app da Aleen usando essas credenciais. Recomendamos alterar sua senha após o primeiro login.\n\n🔗 Continue seu onboarding aqui: https://aleen.dp.claudy.host/onboarding/{user_id}",
            "user_id": user_id,
            "temp_password": temp_password,
            "email": email,
            "onboarding_url": f"https://aleen.dp.claudy.host/onboarding/{user_id}",
            "login_instructions": "Use o email e senha temporária para fazer login no app da Aleen, depois complete seu onboarding no link acima."
        }
        
    except Exception as e:
        print(f"❌ Erro geral ao criar usuário: {e}")
        import traceback
        print(f"📋 Stack trace: {traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Erro ao criar usuário: {str(e)}",
            "user_id": None
        }

# Definição das tools disponíveis para os agentes
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_onboarding_questions",
            "description": "Busca as perguntas de onboarding configuradas no banco de dados para WhatsApp. Use esta ferramenta quando o usuário demonstrar interesse em iniciar o processo de onboarding/cadastro.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "create_user_and_save_onboarding",
            "description": "Cria um novo usuário com autenticação Supabase após coletar nome, idade e email durante o onboarding inicial. O usuário receberá uma senha temporária, pode fazer login imediatamente E receberá automaticamente o link de onboarding para continuar o processo na plataforma web. Use quando o usuário fornecer as 3 informações básicas (nome, idade, email).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome completo do usuário"
                    },
                    "age": {
                        "type": "string", 
                        "description": "Idade do usuário"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email do usuário para login"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Telefone do usuário (número de WhatsApp)"
                    }
                },
                "required": ["name", "age", "email", "phone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_user_meal_plan",
            "description": "Verifica se o usuário atual já possui um plano alimentar ativo. Use sempre antes de criar um novo plano.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_onboarding_responses",
            "description": "Busca todas as respostas do onboarding do usuário atual para analisar perfil e necessidades nutricionais.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_foods",
            "description": "Busca todos os alimentos disponíveis no banco de dados com informações nutricionais. Use SEMPRE antes de criar receitas ou planos alimentares.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_weekly_meal_plan",
            "description": "Cria um plano alimentar semanal básico para o usuário atual. A IA deve usar os alimentos disponíveis (get_available_foods) para criar sugestões de refeições personalizadas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {
                        "type": "string",
                        "description": "Nome do plano alimentar (ex: 'Plano de Emagrecimento - Semana 1')"
                    },
                    "weekly_meals": {
                        "type": "object",
                        "description": "Objeto simples com estrutura livre para organizar as refeições da semana. A IA pode definir a estrutura conforme necessário."
                    }
                },
                "required": ["plan_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_recipe_with_ingredients",
            "description": "Cria uma nova receita com ingredientes específicos no banco de dados. Use quando o usuário quiser criar uma receita personalizada ou quando uma receita mencionada não existir no sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_name": {
                        "type": "string",
                        "description": "Nome da receita"
                    },
                    "description": {
                        "type": "string", 
                        "description": "Descrição da receita (opcional)"
                    },
                    "ingredients_data": {
                        "type": "array",
                        "description": "Lista de ingredientes com quantidades",
                        "items": {
                            "type": "object",
                            "properties": {
                                "food_name": {"type": "string"},
                                "quantity_grams": {"type": "number"},
                                "display_unit": {"type": "string"}
                            },
                            "required": ["food_name", "quantity_grams"]
                        }
                    }
                },
                "required": ["recipe_name", "ingredients_data"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "register_complete_meal_plan",
            "description": "Registra um plano alimentar completo seguindo a estrutura completa do guia de desenvolvimento. Use quando tiver um plano alimentar detalhado com todas as refeições da semana já definidas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_data": {
                        "type": "object",
                        "description": "Dados completos do plano no formato: {planName, startDate, endDate, weeklyPlan}",
                        "properties": {
                            "planName": {"type": "string"},
                            "startDate": {"type": "string", "format": "date"},
                            "endDate": {"type": "string", "format": "date"},
                            "weeklyPlan": {
                                "type": "object",
                                "description": "Refeições organizadas por dia da semana"
                            }
                        },
                        "required": ["planName", "startDate", "endDate", "weeklyPlan"]
                    }
                },
                "required": ["plan_data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_current_meal",
            "description": "Obtém a próxima refeição do usuário baseada no horário atual e no plano alimentar ativo.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "get_user_meal_plan_details",
            "description": "Obtém todos os detalhes do plano alimentar ativo do usuário, incluindo todas as refeições da semana.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_meals", 
            "description": "Obtém todas as refeições do dia atual do usuário baseado no plano alimentar ativo.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_alternative_recipes",
            "description": "Sugere receitas alternativas por categoria (café da manhã, almoço, lanche, jantar) baseado nas receitas disponíveis.",
            "parameters": {
                "type": "object", 
                "properties": {
                    "meal_type": {
                        "type": "string",
                        "description": "Tipo de refeição para filtrar sugestões",
                        "enum": ["Café da Manhã", "Almoço", "Lanche da Tarde", "Jantar"]
                    },
                    "exclude_recipe": {
                        "type": "string",
                        "description": "Nome da receita a ser excluída das sugestões (opcional)"
                    }
                },
                "required": ["meal_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_meal_in_plan",
            "description": "Atualiza uma refeição específica no plano alimentar do usuário, trocando por uma receita diferente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day_of_week": {
                        "type": "string",
                        "description": "Dia da semana da refeição a ser alterada",
                        "enum": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
                    },
                    "meal_type": {
                        "type": "string", 
                        "description": "Tipo de refeição a ser alterada",
                        "enum": ["Café da Manhã", "Almoço", "Lanche da Tarde", "Jantar"]
                    },
                    "new_recipe_name": {
                        "type": "string",
                        "description": "Nome da nova receita para substituir a atual"
                    }
                },
                "required": ["day_of_week", "meal_type", "new_recipe_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "interpret_user_choice",
            "description": "Interpreta escolhas do usuário quando ele se refere a 'Opção 1', 'Opção 2', etc. baseado no contexto da conversa anterior.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_choice": {
                        "type": "string",
                        "description": "A escolha exata que o usuário digitou (ex: 'Opção 1', 'primeira', 'omelete')"
                    },
                    "meal_type": {
                        "type": "string",
                        "description": "Tipo de refeição sendo discutida",
                        "enum": ["Café da Manhã", "Almoço", "Lanche da Tarde", "Jantar"]
                    }
                },
                "required": ["user_choice", "meal_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipe_ingredients",
            "description": "Busca todos os ingredientes de uma receita específica com quantidades exatas. Use quando o usuário perguntar sobre ingredientes de uma receita.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_name": {
                        "type": "string",
                        "description": "Nome exato da receita para buscar ingredientes"
                    }
                },
                "required": ["recipe_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_user_training_plan",
            "description": "Verifica se o usuário atual já possui um plano de treino ativo. Use sempre antes de criar um novo plano.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_exercises",
            "description": "Busca exercícios disponíveis no banco com filtros opcionais por grupo muscular, equipamento e dificuldade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "muscle_group": {
                        "type": "string",
                        "description": "Filtrar por grupo muscular (ex: 'Peitoral', 'Dorsal', 'Quadríceps')"
                    },
                    "equipment": {
                        "type": "string", 
                        "description": "Filtrar por equipamento (ex: 'Halteres', 'Banco', 'Nenhum')"
                    },
                    "difficulty": {
                        "type": "string",
                        "description": "Filtrar por dificuldade",
                        "enum": ["Iniciante", "Intermediário", "Avançado"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_weekly_training_plan",
            "description": "Cria um plano de treino semanal personalizado para o usuário com exercícios específicos. SEMPRE salva no banco de dados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_name": {
                        "type": "string",
                        "description": "Nome do plano de treino"
                    },
                    "objective": {
                        "type": "string",
                        "description": "Objetivo do treino (ex: 'Hipertrofia', 'Emagrecimento', 'Força')"
                    },
                    "weekly_workouts": {
                        "type": "object",
                        "description": "Estrutura dos treinos semanais",
                        "properties": {
                            "days": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "day_of_week": {"type": "integer", "description": "Dia da semana (1=segunda, 7=domingo)"},
                                        "workout_name": {"type": "string", "description": "Nome do treino"},
                                        "exercises": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "exercise_name": {"type": "string"},
                                                    "sets": {"type": "integer"},
                                                    "reps": {"type": "string"},
                                                    "rest_seconds": {"type": "integer"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "required": ["plan_name", "objective", "weekly_workouts"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_workouts",
            "description": "Busca os treinos programados para hoje do usuário baseado no seu fuso horário.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_workout_plan_details",
            "description": "Busca detalhes completos do plano de treino ativo do usuário.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_alternative_exercises",
            "description": "Sugere exercícios alternativos do banco de dados por grupo muscular.",
            "parameters": {
                "type": "object",
                "properties": {
                    "muscle_group": {
                        "type": "string",
                        "description": "Grupo muscular para buscar alternativas (ex: 'Peitoral', 'Dorsal', 'Quadríceps')"
                    },
                    "exclude_exercise": {
                        "type": "string",
                        "description": "Nome do exercício a ser excluído das sugestões (opcional)"
                    }
                },
                "required": ["muscle_group"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_workout_exercise",
            "description": "Atualiza um exercício específico no plano de treino do usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day_of_week": {
                        "type": "string",
                        "description": "Dia da semana do treino",
                        "enum": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
                    },
                    "workout_name": {
                        "type": "string",
                        "description": "Nome do treino a ser modificado"
                    },
                    "old_exercise_name": {
                        "type": "string",
                        "description": "Nome do exercício atual a ser substituído"
                    },
                    "new_exercise_name": {
                        "type": "string",
                        "description": "Nome do novo exercício para substituir"
                    }
                },
                "required": ["day_of_week", "workout_name", "old_exercise_name", "new_exercise_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_exercise_details",
            "description": "Busca detalhes completos de um exercício específico incluindo instruções e dicas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise_name": {
                        "type": "string",
                        "description": "Nome do exercício para buscar detalhes"
                    }
                },
                "required": ["exercise_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_onboarding_for_workout_plan",
            "description": "Analisa as respostas do onboarding do usuário para recomendar um plano de treino personalizado.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_workout_session",
            "description": "Registra uma sessão de treino completada pelo usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workout_date": {
                        "type": "string",
                        "description": "Data do treino no formato YYYY-MM-DD"
                    },
                    "workout_name": {
                        "type": "string",
                        "description": "Nome do treino realizado"
                    },
                    "exercises_performed": {
                        "type": "array",
                        "description": "Lista de exercícios realizados",
                        "items": {
                            "type": "object",
                            "properties": {
                                "exercise_name": {"type": "string"},
                                "sets_completed": {"type": "integer"},
                                "reps_completed": {"type": "string"},
                                "weight_used": {"type": "number"},
                                "notes": {"type": "string"}
                            }
                        }
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duração do treino em minutos"
                    },
                    "intensity_rating": {
                        "type": "integer",
                        "description": "Avaliação da intensidade do treino (1-10)"
                    }
                },
                "required": ["workout_date", "workout_name", "exercises_performed"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_workout_progress",
            "description": "Busca o progresso de treinos do usuário incluindo histórico e estatísticas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period_days": {
                        "type": "integer",
                        "description": "Período em dias para analisar o progresso (padrão: 30)"
                    }
                },
                "required": []
            }
        }
    }
]

# Implementações das tools para planos de treino
def check_user_workout_plan(phone_number: str):
    """Verifica se o usuário já possui um plano de treino ativo"""
    try:
        # Busca usuário pelo telefone
        user_result = supabase.table('users').select('id, onboarding').eq('phone', phone_number).execute()
        
        if not user_result.data:
            return {
                "has_plan": False,
                "message": "Usuário não encontrado",
                "user_id": None,
                "onboarding_completed": False
            }
        
        user_data = user_result.data[0]
        user_id = user_data['id']
        
        # Verifica se onboarding foi completado
        onboarding_completed = user_data.get('onboarding', {}) is not None and user_data.get('onboarding', {}) != {}
        
        # Busca plano de treino ativo
        plan_result = supabase.table('training_plans').select('*').eq('user_id', user_id).eq('is_active', True).execute()
        
        if plan_result.data:
            plan = plan_result.data[0]
            return {
                "has_plan": True,
                "message": f"Usuário já possui plano de treino ativo: {plan['name']}",
                "plan_details": plan,
                "user_id": user_id,
                "onboarding_completed": onboarding_completed
            }
        else:
            return {
                "has_plan": False,
                "status": "no_plan_found",
                "message": "Perfeito! Vejo que você ainda não possui um plano de treino ativo. Vamos criar um plano personalizado para você!",
                "user_id": user_id,
                "onboarding_completed": onboarding_completed,
                "action_needed": "create_plan"
            }
    
    except Exception as e:
        return {"error": f"Erro ao verificar plano de treino: {str(e)}"}

def get_available_exercises(muscle_group: str = None, equipment: str = None, difficulty: str = None):
    """Busca exercícios disponíveis com filtros opcionais"""
    try:
        query = supabase.table('exercises').select('*')
        
        if muscle_group:
            query = query.eq('primary_muscle_group', muscle_group)
        if equipment:
            query = query.eq('equipment_needed', equipment)
        if difficulty:
            query = query.eq('difficulty_level', difficulty)
            
        result = query.execute()
        
        return {
            "success": True,
            "exercises": result.data,
            "total": len(result.data),
            "filters_applied": {
                "muscle_group": muscle_group,
                "equipment": equipment,
                "difficulty": difficulty
            }
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar exercícios: {str(e)}"}

def analyze_onboarding_for_workout_plan(phone_number: str):
    """Analisa respostas do onboarding para recomendar plano de treino personalizado"""
    try:
        print(f"🔍 ANALISANDO ONBOARDING PARA TREINO: {phone_number}")
        
        # Busca respostas do onboarding
        onboarding_result = get_user_onboarding_responses(phone_number)
        
        if not onboarding_result.get('success'):
            return {"error": "Não foi possível obter dados do onboarding"}
        
        responses = onboarding_result.get('responses', [])
        user_data = onboarding_result.get('user_data', {})
        
        # Processa respostas para extrair informações relevantes para treino
        fitness_profile = {
            'experience_level': 'Iniciante',  # Default
            'goals': [],
            'available_days': 3,  # Default
            'session_duration': 60,  # Default
            'equipment_access': 'Academia',  # Default
            'physical_limitations': [],
            'preferred_activities': [],
            'age_group': 'adult',
            'gender': 'not_specified'
        }
        
        # Analisa cada resposta do onboarding
        for response in responses:
            step = response.get('step_number')
            field_name = response.get('field_name', '')
            answer = response.get('answer', '').lower()
            
            # Step 1: Nível de experiência com exercícios
            if step == 1 and 'experiencia' in field_name:
                if 'iniciante' in answer or 'nunca' in answer:
                    fitness_profile['experience_level'] = 'Iniciante'
                elif 'intermediario' in answer or 'alguns meses' in answer:
                    fitness_profile['experience_level'] = 'Intermediário'
                elif 'avancado' in answer or 'anos' in answer:
                    fitness_profile['experience_level'] = 'Avançado'
            
            # Step 2: Objetivos principais
            if step == 2 and 'objetivo' in field_name:
                if 'perder peso' in answer or 'emagrecer' in answer:
                    fitness_profile['goals'].append('Perda de Peso')
                if 'ganhar musculo' in answer or 'hipertrofia' in answer:
                    fitness_profile['goals'].append('Hipertrofia')
                if 'melhorar condicionamento' in answer or 'cardio' in answer:
                    fitness_profile['goals'].append('Condicionamento')
                if 'forca' in answer or 'força' in answer:
                    fitness_profile['goals'].append('Força')
                if 'flexibilidade' in answer or 'alongamento' in answer:
                    fitness_profile['goals'].append('Flexibilidade')
            
            # Step 3: Disponibilidade semanal
            if step == 3 and 'disponibilidade' in field_name:
                if '1-2' in answer or 'pouco tempo' in answer:
                    fitness_profile['available_days'] = 2
                elif '3-4' in answer or 'moderado' in answer:
                    fitness_profile['available_days'] = 4
                elif '5-6' in answer or 'bastante' in answer:
                    fitness_profile['available_days'] = 5
                elif 'todos os dias' in answer or '7' in answer:
                    fitness_profile['available_days'] = 6
            
            # Step 4: Duração preferida da sessão
            if step == 4 and 'duracao' in field_name:
                if '30' in answer or 'rapido' in answer:
                    fitness_profile['session_duration'] = 45
                elif '60' in answer or 'moderado' in answer:
                    fitness_profile['session_duration'] = 60
                elif '90' in answer or 'longo' in answer:
                    fitness_profile['session_duration'] = 75
            
            # Step 5: Acesso a equipamentos
            if step == 5 and 'equipamento' in field_name:
                if 'casa' in answer or 'peso corporal' in answer:
                    fitness_profile['equipment_access'] = 'Casa'
                elif 'academia' in answer or 'completo' in answer:
                    fitness_profile['equipment_access'] = 'Academia'
                elif 'limitado' in answer or 'basico' in answer:
                    fitness_profile['equipment_access'] = 'Básico'
            
            # Step 6: Limitações físicas
            if step == 6 and 'limitacao' in field_name:
                if 'joelho' in answer:
                    fitness_profile['physical_limitations'].append('joelho')
                if 'costa' in answer or 'coluna' in answer:
                    fitness_profile['physical_limitations'].append('coluna')
                if 'ombro' in answer:
                    fitness_profile['physical_limitations'].append('ombro')
                if 'nenhuma' in answer:
                    fitness_profile['physical_limitations'] = []
            
            # Informações demográficas
            if 'idade' in field_name:
                age = int(answer) if answer.isdigit() else 30
                if age < 25:
                    fitness_profile['age_group'] = 'young'
                elif age > 50:
                    fitness_profile['age_group'] = 'senior'
                else:
                    fitness_profile['age_group'] = 'adult'
            
            if 'sexo' in field_name or 'genero' in field_name:
                if 'masculino' in answer or 'homem' in answer:
                    fitness_profile['gender'] = 'male'
                elif 'feminino' in answer or 'mulher' in answer:
                    fitness_profile['gender'] = 'female'
        
        print(f"👤 PERFIL FITNESS EXTRAÍDO: {fitness_profile}")
        
        # Gera recomendações baseadas no perfil
        recommendations = generate_workout_recommendations(fitness_profile)
        
        return {
            "success": True,
            "fitness_profile": fitness_profile,
            "recommendations": recommendations,
            "message": "Análise do onboarding concluída com sucesso"
        }
        
    except Exception as e:
        print(f"❌ ERRO na análise do onboarding: {str(e)}")
        return {"error": f"Erro ao analisar onboarding: {str(e)}"}

def generate_workout_recommendations(fitness_profile: dict):
    """Gera recomendações de treino baseadas no perfil do usuário"""
    try:
        recommendations = {
            "plan_name": "",
            "objective": "",
            "weekly_structure": {},
            "exercise_selection_criteria": {},
            "progression_notes": ""
        }
        
        # Define nome e objetivo do plano
        experience = fitness_profile['experience_level']
        goals = fitness_profile['goals']
        days = fitness_profile['available_days']
        
        if 'Perda de Peso' in goals:
            recommendations["plan_name"] = f"Plano Queima Gordura - {experience}"
            recommendations["objective"] = "Perda de peso e definição muscular"
        elif 'Hipertrofia' in goals:
            recommendations["plan_name"] = f"Plano Hipertrofia - {experience}"
            recommendations["objective"] = "Ganho de massa muscular"
        elif 'Força' in goals:
            recommendations["plan_name"] = f"Plano Força - {experience}"
            recommendations["objective"] = "Desenvolvimento de força e potência"
        else:
            recommendations["plan_name"] = f"Plano Geral - {experience}"
            recommendations["objective"] = "Condicionamento físico geral"
        
        # Estrutura semanal baseada na disponibilidade
        equipment = fitness_profile['equipment_access']
        duration = fitness_profile['session_duration']
        
        if days <= 2:
            # Treino Full Body 2x/semana
            recommendations["weekly_structure"] = {
                "frequency": "2x por semana",
                "type": "Full Body",
                "recommended_days": ["segunda-feira", "quinta-feira"],
                "focus": "Exercícios compostos para máxima eficiência"
            }
        elif days <= 4:
            # Treino Upper/Lower ou ABC
            if experience == 'Iniciante':
                recommendations["weekly_structure"] = {
                    "frequency": "3x por semana",
                    "type": "Full Body Alternado",
                    "recommended_days": ["segunda-feira", "quarta-feira", "sexta-feira"],
                    "focus": "Adaptação e aprendizado de movimentos"
                }
            else:
                recommendations["weekly_structure"] = {
                    "frequency": "4x por semana",
                    "type": "Upper/Lower Split",
                    "recommended_days": ["segunda-feira", "terça-feira", "quinta-feira", "sexta-feira"],
                    "focus": "Volume moderado com recuperação adequada"
                }
        else:
            # Treino dividido ABC/ABCD
            recommendations["weekly_structure"] = {
                "frequency": f"{days}x por semana",
                "type": "Treino Dividido ABCD",
                "recommended_days": ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira"],
                "focus": "Alto volume e especialização muscular"
            }
        
        # Critérios de seleção de exercícios
        criteria = {
            "muscle_groups": [],
            "equipment_preference": equipment,
            "intensity_level": experience,
            "avoid_exercises": []
        }
        
        # Exercícios baseados no objetivo
        if 'Perda de Peso' in goals:
            criteria["muscle_groups"] = ["Pernas", "Peito", "Costas", "Core"]
            criteria["cardio_emphasis"] = "Alto"
            criteria["rep_range"] = "12-20"
        elif 'Hipertrofia' in goals:
            criteria["muscle_groups"] = ["Peito", "Costas", "Pernas", "Ombros", "Braços"]
            criteria["cardio_emphasis"] = "Baixo"
            criteria["rep_range"] = "8-12"
        elif 'Força' in goals:
            criteria["muscle_groups"] = ["Peito", "Costas", "Pernas"]
            criteria["cardio_emphasis"] = "Muito Baixo"
            criteria["rep_range"] = "4-8"
        
        # Adaptações para limitações físicas
        limitations = fitness_profile['physical_limitations']
        if 'joelho' in limitations:
            criteria["avoid_exercises"].extend(["Agachamento Profundo", "Leg Press Completo"])
        if 'coluna' in limitations:
            criteria["avoid_exercises"].extend(["Deadlift", "Agachamento com Barra"])
        if 'ombro' in limitations:
            criteria["avoid_exercises"].extend(["Desenvolvimento por Trás", "Supino Inclinado"])
        
        recommendations["exercise_selection_criteria"] = criteria
        
        # Notas de progressão
        if experience == 'Iniciante':
            recommendations["progression_notes"] = "Foco na técnica e progressão gradual. Aumente carga apenas quando dominarem o movimento."
        elif experience == 'Intermediário':
            recommendations["progression_notes"] = "Progressão linear semanal. Variar exercícios a cada 4-6 semanas."
        else:
            recommendations["progression_notes"] = "Periodização avançada. Ajustar volume e intensidade conforme resposta individual."
        
        print(f"💡 RECOMENDAÇÕES GERADAS: {recommendations}")
        return recommendations
        
    except Exception as e:
        print(f"❌ ERRO ao gerar recomendações: {str(e)}")
        return {"error": f"Erro ao gerar recomendações: {str(e)}"}

def create_weekly_workout_plan(phone_number: str, plan_name: str, objective: str, weekly_workouts: dict):
    """Cria um plano de treino semanal SIMPLES usando templates existentes"""
    try:
        print(f"🏋️ CRIANDO PLANO DE TREINO: {plan_name} para {phone_number}")
        print(f"📊 Dados recebidos: {weekly_workouts}")
        
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        print(f"👤 User ID: {user_id}")
        
        # Desativa planos existentes
        supabase.table('training_plans').update({'is_active': False}).eq('user_id', user_id).execute()
        
        # Cria novo plano
        plan_data = {
            'user_id': user_id,
            'name': plan_name,
            'objective': objective,
            'start_date': datetime.now().strftime('%Y-%m-%d'),
            'end_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'is_active': True
        }
        
        plan_result = supabase.table('training_plans').insert(plan_data).execute()
        if not plan_result.data:
            return {"error": "Erro ao criar plano de treino"}
        
        plan_id = plan_result.data[0]['id']
        print(f"📋 Plano criado: {plan_id}")
        
        # BUSCA TEMPLATES EXISTENTES (SIMPLIFICADO!)
        templates_result = supabase.table('workout_templates').select('id, name').execute()
        if not templates_result.data:
            return {"error": "Nenhum template de treino encontrado"}
        
        available_templates = {t['name']: t['id'] for t in templates_result.data}
        print(f"🎯 Templates disponíveis: {list(available_templates.keys())}")
        
        # Liga templates aos dias da semana (ESTRUTURA SIMPLES)
        workout_count = 0
        days_list = weekly_workouts.get('days', [])
        
        if days_list:
            print(f"📅 Processando {len(days_list)} dias de treino")
            
            for day_info in days_list:
                day_of_week = day_info.get('day_of_week')  # 1-7 
                workout_name = day_info.get('workout_name', 'Full Body Iniciante')
                
                # Converte número para dia da semana em português
                day_names = {
                    1: 'segunda-feira',
                    2: 'terça-feira', 
                    3: 'quarta-feira',
                    4: 'quinta-feira',
                    5: 'sexta-feira',
                    6: 'sábado',
                    7: 'domingo'
                }
                
                day_text = day_names.get(day_of_week, 'segunda-feira')
                
                # Mapeia nome do treino para template existente (estratégia simples)
                template_id = None
                if 'peito' in workout_name.lower() or 'triceps' in workout_name.lower():
                    template_id = available_templates.get('Treino A - Peito e Tríceps')
                elif 'costas' in workout_name.lower() or 'biceps' in workout_name.lower():
                    template_id = available_templates.get('Treino B - Costas e Bíceps')
                elif 'pernas' in workout_name.lower() or 'core' in workout_name.lower():
                    template_id = available_templates.get('Treino C - Pernas e Core')
                else:
                    # Fallback para template genérico
                    template_id = available_templates.get('Full Body Iniciante')
                
                if template_id:
                    # INSERE NA ESTRUTURA CORRETA COM TEXTO!
                    plan_workout_data = {
                        'training_plan_id': plan_id,        # CORRETO: plano principal
                        'workout_template_id': template_id,  # CORRETO: template existente  
                        'day_of_week': day_text             # CORRETO: "segunda-feira" em texto
                    }
                    
                    print(f"🏋️ Ligando template '{workout_name}' ao dia {day_text}")
                    plan_workout_result = supabase.table('plan_workouts').insert(plan_workout_data).execute()
                    
                    if plan_workout_result.data:
                        workout_count += 1
                        print(f"✅ Treino ligado com sucesso!")
                    else:
                        print(f"❌ Erro ao ligar template ao plano")
                else:
                    print(f"⚠️ Template não encontrado para: {workout_name}")
        
        print(f"🎯 PLANO CRIADO: {workout_count} treinos adicionados")
        
        return {
            "success": True,
            "message": f"Plano de treino '{plan_name}' criado com sucesso!",
            "plan_id": plan_id,
            "total_workouts": workout_count,
            "objective": objective,
            "duration": "30 dias"
        }
        
    except Exception as e:
        print(f"❌ ERRO ao criar plano de treino: {str(e)}")
        print(f"📊 DEBUG - weekly_workouts: {weekly_workouts}")
        import traceback
        print(f"📊 Stack trace: {traceback.format_exc()}")
        return {"error": f"Erro ao criar plano de treino: {str(e)}"}

def get_today_workouts(phone_number: str):
    """Busca treinos do usuário para hoje baseado no seu fuso horário"""
    try:
        # Busca usuário e timezone
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Busca timezone do usuário a partir do onboarding
        timezone_offset = get_user_timezone_offset(phone_number)
        
        # Calcula dia atual no timezone do usuário
        utc_now = datetime.utcnow()
        user_time = utc_now + timedelta(hours=timezone_offset)
        current_day = user_time.strftime('%A').lower()
        
        # Mapeia dias em inglês para português (IGUAL À NUTRIÇÃO!)
        day_mapping = {
            'monday': 'segunda-feira',
            'tuesday': 'terça-feira', 
            'wednesday': 'quarta-feira',
            'thursday': 'quinta-feira',
            'friday': 'sexta-feira',
            'saturday': 'sábado',
            'sunday': 'domingo'
        }
        
        day_portuguese = day_mapping.get(current_day, current_day)
        
        # Busca treinos de hoje usando TEXTO do dia
        workouts = supabase.table('plan_workouts').select('''
            *,
            training_plans(name),
            workout_templates(name, description)
        ''').eq('training_plans.user_id', user_id).eq('day_of_week', day_portuguese).execute()
        
        if not workouts.data:
            return {
                "success": True,
                "current_day": day_portuguese,
                "workouts": [],
                "message": f"Nenhum treino programado para {day_portuguese}"
            }
        
        return {
            "success": True,
            "current_day": day_portuguese,
            "user_time": user_time.strftime('%H:%M'),
            "workouts": workouts.data,
            "total_workouts": len(workouts.data)
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar treinos de hoje: {str(e)}"}

def get_user_workout_plan_details(phone_number: str):
    """Busca detalhes completos do plano de treino do usuário"""
    try:
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Busca plano ativo (TABELA CORRETA!)
        plan_result = supabase.table('training_plans').select('*').eq('user_id', user_id).eq('is_active', True).execute()
        
        if not plan_result.data:
            return {"error": "Nenhum plano de treino ativo encontrado"}
        
        plan = plan_result.data[0]
        
        # Busca todos os treinos do plano (ESTRUTURA CORRIGIDA!)
        workouts_result = supabase.table('plan_workouts').select('''
            *,
            workout_templates(
                name,
                description,
                workout_template_exercises(
                    order_in_workout,
                    target_sets,
                    target_reps,
                    target_rest_seconds,
                    notes,
                    exercises(name, description, target_muscle_groups, equipment_needed, difficulty_level)
                )
            )
        ''').eq('training_plan_id', plan['id']).order('day_of_week').execute()
        
        return {
            "success": True,
            "plan_details": plan,
            "workouts": workouts_result.data,
            "total_workouts": len(workouts_result.data),
            "plan_name": plan['name'],
            "objective": plan['objective']
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar detalhes do plano: {str(e)}"}

def suggest_alternative_exercises(muscle_group: str, exclude_exercise: str = None):
    """Sugere exercícios alternativos REAIS do banco de dados por grupo muscular"""
    try:
        # Busca exercícios do grupo muscular
        query = supabase.table('exercises').select('name, primary_muscle_group, secondary_muscle_group, equipment_needed, difficulty_level, instructions')
        
        # Filtra por grupo muscular (primário ou secundário)
        if muscle_group:
            query = query.or_(f'primary_muscle_group.eq.{muscle_group},secondary_muscle_group.eq.{muscle_group}')
        
        # Exclui exercício específico se fornecido
        if exclude_exercise:
            query = query.neq('name', exclude_exercise)
        
        exercises_result = query.execute()
        
        if not exercises_result.data:
            return {"error": f"Nenhum exercício encontrado para {muscle_group}"}
        
        # Limita a 4 sugestões e formata com números
        limited_suggestions = exercises_result.data[:4]
        
        formatted_suggestions = []
        for i, exercise in enumerate(limited_suggestions, 1):
            formatted_suggestions.append({
                "option_number": i,
                "exercise_name": exercise['name'],
                "primary_muscle": exercise['primary_muscle_group'],
                "equipment": exercise.get('equipment_needed', 'Não especificado'),
                "difficulty": exercise.get('difficulty_level', 'Intermediário'),
                "instructions": exercise.get('instructions', ''),
                "formatted_text": f"{i}. {exercise['name']}"
            })
        
        return {
            "success": True,
            "muscle_group": muscle_group,
            "excluded_exercise": exclude_exercise,
            "suggestions": formatted_suggestions,
            "total_suggestions": len(formatted_suggestions),
            "message": "Todos os exercícios são REAIS e existem no banco de dados"
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar sugestões: {str(e)}"}

def update_workout_exercise(phone_number: str, day_of_week: str, workout_name: str, old_exercise_name: str, new_exercise_name: str):
    """Atualiza um exercício específico no plano de treino do usuário"""
    try:
        print(f"🔍 UPDATE_WORKOUT_EXERCISE DEBUG:")
        print(f"📞 Telefone: {phone_number}")
        print(f"📅 Dia: {day_of_week}")
        print(f"🏋️ Treino: {workout_name}")
        print(f"🔄 Trocando: {old_exercise_name} → {new_exercise_name}")
        
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Busca plano ativo (CORRIGIDO!)
        plan_result = supabase.table('training_plans').select('id').eq('user_id', user_id).eq('is_active', True).execute()
        if not plan_result.data:
            return {"error": "Nenhum plano de treino ativo encontrado"}
        
        plan_id = plan_result.data[0]['id']
        
        # Verifica se o novo exercício existe
        exercise_result = supabase.table('exercises').select('id, name').ilike('name', new_exercise_name).execute()
        if not exercise_result.data:
            # Tenta busca parcial
            exercise_result = supabase.table('exercises').select('id, name').ilike('name', f'%{new_exercise_name}%').execute()
            
        if not exercise_result.data:
            return {"error": f"Exercício '{new_exercise_name}' não encontrado no banco de dados"}
        
        new_exercise_id = exercise_result.data[0]['id']
        actual_exercise_name = exercise_result.data[0]['name']
        
        # Busca o treino específico
        workout_result = supabase.table('plan_workouts').select('id').eq('user_workout_plan_id', plan_id).eq('day_of_week', day_of_week).eq('workout_name', workout_name).execute()
        
        if not workout_result.data:
            return {"error": f"Treino '{workout_name}' não encontrado para {day_of_week}"}
        
        workout_id = workout_result.data[0]['id']
        
        # Busca o exercício a ser substituído
        exercise_to_update = supabase.table('workout_exercises').select('id, exercises(name)').eq('plan_workout_id', workout_id).eq('exercises.name', old_exercise_name).execute()
        
        if not exercise_to_update.data:
            return {"error": f"Exercício '{old_exercise_name}' não encontrado no treino"}
        
        exercise_entry_id = exercise_to_update.data[0]['id']
        
        # Atualiza o exercício
        update_result = supabase.table('workout_exercises').update({
            'exercise_id': new_exercise_id
        }).eq('id', exercise_entry_id).execute()
        
        if update_result.data:
            return {
                "success": True,
                "message": f"Exercício atualizado com sucesso!",
                "day": day_of_week,
                "workout": workout_name,
                "old_exercise": old_exercise_name,
                "new_exercise": actual_exercise_name,
                "updated_at": update_result.data[0]
            }
        else:
            return {"error": "Falha ao atualizar o exercício"}
        
    except Exception as e:
        print(f"❌ ERRO em update_workout_exercise: {str(e)}")
        return {"error": f"Erro ao atualizar exercício: {str(e)}"}

def get_exercise_details(exercise_name: str):
    """Busca detalhes completos de um exercício específico"""
    try:
        # Busca exercício por nome
        result = supabase.table('exercises').select('*').ilike('name', exercise_name).execute()
        
        if not result.data:
            # Tenta busca parcial
            result = supabase.table('exercises').select('*').ilike('name', f'%{exercise_name}%').execute()
            
        if not result.data:
            return {"error": f"Exercício '{exercise_name}' não encontrado"}
        
        exercise = result.data[0]
        
        return {
            "success": True,
            "exercise": exercise,
            "name": exercise['name'],
            "primary_muscle": exercise['primary_muscle_group'],
            "secondary_muscle": exercise.get('secondary_muscle_group'),
            "equipment": exercise.get('equipment_needed'),
            "difficulty": exercise.get('difficulty_level'),
            "instructions": exercise.get('instructions'),
            "tips": exercise.get('form_tips')
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar detalhes do exercício: {str(e)}"}

def record_workout_session(phone_number: str, workout_date: str, workout_name: str, exercises_performed: list, duration_minutes: int = None, intensity_rating: int = None):
    """Registra uma sessão de treino completada pelo usuário"""
    try:
        print(f"🏋️ REGISTRANDO SESSÃO DE TREINO para {phone_number}")
        print(f"📅 Data: {workout_date}")
        print(f"🎯 Treino: {workout_name}")
        print(f"💪 Exercícios: {len(exercises_performed)}")
        
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Busca plano ativo (CORRIGIDO!)
        plan_result = supabase.table('training_plans').select('id').eq('user_id', user_id).eq('is_active', True).execute()
        if not plan_result.data:
            return {"error": "Nenhum plano de treino ativo encontrado"}
        
        plan_id = plan_result.data[0]['id']
        
        # Registra a sessão de treino
        session_data = {
            'user_id': user_id,
            'workout_plan_id': plan_id,
            'workout_date': workout_date,
            'workout_name': workout_name,
            'duration_minutes': duration_minutes or 60,
            'intensity_rating': intensity_rating,
            'completed_at': datetime.now().isoformat()
        }
        
        session_result = supabase.table('workout_sessions').insert(session_data).execute()
        
        if not session_result.data:
            return {"error": "Falha ao registrar sessão de treino"}
        
        session_id = session_result.data[0]['id']
        
        # Registra os exercícios realizados
        exercises_registered = []
        for exercise in exercises_performed:
            exercise_name = exercise.get('exercise_name')
            sets_completed = exercise.get('sets_completed', 0)
            reps_completed = exercise.get('reps_completed', '0')
            weight_used = exercise.get('weight_used', 0)
            notes = exercise.get('notes', '')
            
            # Busca ID do exercício
            exercise_result = supabase.table('exercises').select('id').eq('name', exercise_name).execute()
            if exercise_result.data:
                exercise_id = exercise_result.data[0]['id']
                
                exercise_session_data = {
                    'workout_session_id': session_id,
                    'exercise_id': exercise_id,
                    'sets_completed': sets_completed,
                    'reps_completed': reps_completed,
                    'weight_used': weight_used,
                    'notes': notes
                }
                
                supabase.table('workout_session_exercises').insert(exercise_session_data).execute()
                exercises_registered.append({
                    'exercise_name': exercise_name,
                    'sets': sets_completed,
                    'reps': reps_completed,
                    'weight': weight_used
                })
        
        return {
            "success": True,
            "message": f"Sessão de treino '{workout_name}' registrada com sucesso!",
            "session_id": session_id,
            "workout_date": workout_date,
            "exercises_registered": len(exercises_registered),
            "duration_minutes": duration_minutes or 60,
            "intensity_rating": intensity_rating
        }
        
    except Exception as e:
        print(f"❌ ERRO em record_workout_session: {str(e)}")
        return {"error": f"Erro ao registrar sessão: {str(e)}"}

def get_workout_progress(phone_number: str, period_days: int = 30):
    """Busca o progresso de treinos do usuário incluindo histórico e estatísticas"""
    try:
        print(f"📊 BUSCANDO PROGRESSO DE TREINOS para {phone_number}")
        print(f"📅 Período: {period_days} dias")
        
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Calcula data de início do período
        from datetime import datetime, timedelta
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=period_days)
        
        # Busca sessões de treino no período
        sessions_result = supabase.table('workout_sessions').select('''
            *,
            workout_session_exercises(
                *,
                exercises(name, primary_muscle_group)
            )
        ''').eq('user_id', user_id).gte('workout_date', str(start_date)).lte('workout_date', str(end_date)).order('workout_date', desc=True).execute()
        
        sessions = sessions_result.data
        
        if not sessions:
            return {
                "success": True,
                "period_days": period_days,
                "total_sessions": 0,
                "total_exercises": 0,
                "avg_duration": 0,
                "avg_intensity": 0,
                "sessions": [],
                "message": f"Nenhum treino registrado nos últimos {period_days} dias"
            }
        
        # Calcula estatísticas
        total_sessions = len(sessions)
        total_duration = sum(s.get('duration_minutes', 0) for s in sessions)
        avg_duration = round(total_duration / total_sessions) if total_sessions > 0 else 0
        
        intensities = [s.get('intensity_rating') for s in sessions if s.get('intensity_rating')]
        avg_intensity = round(sum(intensities) / len(intensities), 1) if intensities else 0
        
        # Conta total de exercícios únicos
        all_exercises = set()
        for session in sessions:
            for exercise in session.get('workout_session_exercises', []):
                all_exercises.add(exercise['exercises']['name'])
        
        # Prepara dados das sessões
        formatted_sessions = []
        for session in sessions:
            session_exercises = session.get('workout_session_exercises', [])
            formatted_sessions.append({
                'date': session['workout_date'],
                'workout_name': session['workout_name'],
                'duration_minutes': session.get('duration_minutes', 0),
                'intensity_rating': session.get('intensity_rating'),
                'exercises_count': len(session_exercises),
                'exercises': [ex['exercises']['name'] for ex in session_exercises]
            })
        
        return {
            "success": True,
            "period_days": period_days,
            "total_sessions": total_sessions,
            "total_exercises": len(all_exercises),
            "avg_duration_minutes": avg_duration,
            "avg_intensity_rating": avg_intensity,
            "sessions": formatted_sessions,
            "message": f"Progresso dos últimos {period_days} dias: {total_sessions} treinos realizados"
        }
        
    except Exception as e:
        print(f"❌ ERRO em get_workout_progress: {str(e)}")
        return {"error": f"Erro ao buscar progresso: {str(e)}"}

# Implementações das tools para planos alimentares
def check_user_meal_plan(phone_number: str):
    """Verifica se o usuário já possui um plano alimentar ativo e se completou o onboarding"""
    try:
        # Busca usuário pelo telefone com informações de onboarding
        user_result = supabase.table('users').select('id, onboarding').eq('phone', phone_number).execute()
        
        if not user_result.data:
            return {
                "has_plan": False,
                "message": "Usuário não encontrado",
                "user_id": None,
                "onboarding_completed": False
            }
        
        user_data = user_result.data[0]
        user_id = user_data['id']
        onboarding_completed = user_data.get('onboarding', False)
        
        # Se onboarding não foi completado, retorna informação
        if not onboarding_completed:
            return {
                "has_plan": False,
                "message": "Usuário precisa completar o onboarding antes de criar plano alimentar",
                "user_id": user_id,
                "onboarding_completed": False
            }
        
        # Verifica se há plano ativo
        plan_result = supabase.table('user_meal_plans').select('*').eq('user_id', user_id).eq('is_active', True).execute()
        
        if plan_result.data:
            return {
                "has_plan": True,
                "plan": plan_result.data[0],
                "user_id": user_id,
                "onboarding_completed": True
            }
        else:
            return {
                "has_plan": False,
                "status": "no_plan_found",
                "message": "Perfeito! Vejo que você ainda não possui um plano alimentar ativo. Vamos criar um plano nutricional personalizado para você!",
                "user_id": user_id,
                "onboarding_completed": True,
                "action_needed": "create_plan"
            }
            
    except Exception as e:
        return {
            "has_plan": False,
            "error": f"Erro ao verificar plano: {str(e)}",
            "user_id": None,
            "onboarding_completed": False
        }

def get_user_onboarding_responses(phone_number: str):
    """Busca todas as respostas do onboarding do usuário"""
    try:
        # Busca usuário pelo telefone
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        
        if not user_result.data:
            return {
                "success": False,
                "message": "Usuário não encontrado",
                "responses": []
            }
        
        user_id = user_result.data[0]['id']
        
        # Busca respostas do onboarding diretamente
        try:
            responses_result = supabase.table('onboarding_responses').select('*').eq('user_id', user_id).execute()
            
            if not responses_result.data:
                return {
                    "success": False,
                    "message": "Nenhuma resposta de onboarding encontrada para este usuário",
                    "responses": [],
                    "user_id": user_id
                }
            
            return {
                "success": True,
                "user_id": user_id,
                "responses": responses_result.data,
                "message": f"Encontradas {len(responses_result.data)} respostas de onboarding"
            }
            
        except Exception as db_error:
            return {
                "success": False,
                "error": f"Erro na consulta do banco: {str(db_error)}",
                "responses": [],
                "user_id": user_id
            }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao buscar respostas: {str(e)}",
            "responses": []
        }

def get_available_foods():
    """Busca todos os alimentos disponíveis no banco de dados com informações nutricionais"""
    try:
        foods_result = supabase.table('foods').select('*').execute()
        
        if not foods_result.data:
            return {
                "success": False,
                "message": "Nenhum alimento encontrado no banco de dados",
                "foods": []
            }
        
        return {
            "success": True,
            "message": f"Encontrados {len(foods_result.data)} alimentos disponíveis",
            "foods": foods_result.data
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao buscar alimentos: {str(e)}",
            "foods": []
        }

def create_weekly_meal_plan(phone_number: str, plan_name: str, weekly_meals: dict):
    """
    Cria um plano alimentar semanal completo seguindo o guia de desenvolvimento.
    
    Args:
        phone_number: Telefone do usuário
        plan_name: Nome do plano
        weekly_meals: Estrutura JSON do plano semanal no formato:
        {
            "startDate": "2025-09-01",
            "endDate": "2025-12-01", 
            "weeklyPlan": {
                "segunda-feira": [
                    {"mealType": "Café da Manhã", "recipeName": "Ovos com Café", "order": 1}
                ],
                ...
            }
        }
    """
    try:
        # Busca usuário pelo telefone
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        
        if not user_result.data:
            return {
                "success": False,
                "message": "Usuário não encontrado"
            }
        
        user_id = user_result.data[0]['id']
        
        # Passo 1: Desativar planos antigos (opcional, mas recomendado)
        supabase.table('user_meal_plans').update({
            'is_active': False
        }).eq('user_id', user_id).execute()
        
        # Definir datas padrão se não fornecidas
        from datetime import datetime, timedelta
        start_date = weekly_meals.get('startDate', datetime.now().date().isoformat())
        end_date = weekly_meals.get('endDate', (datetime.now().date() + timedelta(days=7)).isoformat())
        
        # Passo 2: Criar o registro principal em user_meal_plans
        plan_result = supabase.table('user_meal_plans').insert({
            'user_id': user_id,
            'name': plan_name,
            'start_date': start_date,
            'end_date': end_date,
            'is_active': True
        }).execute()
        
        if not plan_result.data:
            return {
                "success": False,
                "message": "Erro ao criar plano principal"
            }
        
        plan_id = plan_result.data[0]['id']
        
        # Passo 3: Processar o plano semanal se fornecido
        weekly_plan = weekly_meals.get('weeklyPlan', {})
        if weekly_plan:
            # Extrair todos os nomes de receitas únicos do JSON
            recipe_names = []
            for day, meals in weekly_plan.items():
                for meal in meals:
                    recipe_name = meal.get('recipeName')
                    if recipe_name and recipe_name not in recipe_names:
                        recipe_names.append(recipe_name)
            
            if recipe_names:
                # Buscar IDs das receitas existentes no banco
                recipes_result = supabase.table('recipes').select('id, name').in_('name', recipe_names).execute()
                
                # Criar mapa de nome para ID
                recipe_name_to_id_map = {}
                for recipe in recipes_result.data:
                    recipe_name_to_id_map[recipe['name']] = recipe['id']
                
                # Preparar registros para inserir em plan_meals
                meals_to_insert = []
                recipes_not_found = []
                
                for day, meals in weekly_plan.items():
                    for meal in meals:
                        recipe_name = meal.get('recipeName')
                        meal_type = meal.get('mealType')
                        order = meal.get('order', 1)
                        
                        if recipe_name in recipe_name_to_id_map:
                            meals_to_insert.append({
                                'user_meal_plan_id': plan_id,
                                'day_of_week': day,
                                'meal_type': meal_type,
                                'recipe_id': recipe_name_to_id_map[recipe_name],
                                'display_order': order
                            })
                        else:
                            recipes_not_found.append(recipe_name)
                
                # Passo 4: Inserir as refeições em plan_meals
                if meals_to_insert:
                    supabase.table('plan_meals').insert(meals_to_insert).execute()
                
                result_message = f"Plano alimentar '{plan_name}' criado com sucesso!"
                if recipes_not_found:
                    result_message += f" Receitas não encontradas na base de dados: {', '.join(recipes_not_found)}"
                
                return {
                    "success": True,
                    "message": result_message,
                    "plan_id": plan_id,
                    "user_id": user_id,
                    "meals_created": len(meals_to_insert),
                    "recipes_not_found": recipes_not_found
                }
            
        # Se não houver plano semanal, retornar apenas o plano base criado
        return {
            "success": True,
            "message": f"Plano alimentar '{plan_name}' criado com sucesso!",
            "plan_id": plan_id,
            "user_id": user_id,
            "instructions": "Plano base criado. As refeições específicas podem ser definidas posteriormente conforme necessário."
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Erro ao criar plano alimentar: {str(e)}"
        }


def create_recipe_with_ingredients(recipe_name: str, description: str, ingredients_data: list):
    """
    Cria uma nova receita com seus ingredientes no banco de dados.
    
    Args:
        recipe_name: Nome da receita
        description: Descrição da receita (opcional)
        ingredients_data: Lista de ingredientes no formato:
        [
            {"food_name": "Peito de frango", "quantity_grams": 150, "display_unit": "150g"},
            {"food_name": "Arroz integral", "quantity_grams": 100, "display_unit": "1/2 xícara"}
        ]
    
    Returns:
        dict: Resultado da operação com recipe_id se bem-sucedida
    """
    try:
        # Criar a receita
        recipe_result = supabase.table('recipes').insert({
            'name': recipe_name,
            'description': description or f"Receita de {recipe_name} criada automaticamente"
        }).execute()
        
        if not recipe_result.data:
            return {
                "success": False,
                "message": "Erro ao criar receita"
            }
        
        recipe_id = recipe_result.data[0]['id']
        
        # Se há ingredientes, buscar seus IDs e criar os relacionamentos
        if ingredients_data:
            food_names = [ingredient['food_name'] for ingredient in ingredients_data]
            
            # Buscar IDs dos alimentos
            foods_result = supabase.table('foods').select('id, name').in_('name', food_names).execute()
            
            # Criar mapa de nome para ID
            food_name_to_id_map = {}
            for food in foods_result.data:
                food_name_to_id_map[food['name']] = food['id']
            
            # Preparar ingredientes para inserir
            recipe_ingredients = []
            foods_not_found = []
            
            for ingredient in ingredients_data:
                food_name = ingredient['food_name']
                if food_name in food_name_to_id_map:
                    recipe_ingredients.append({
                        'recipe_id': recipe_id,
                        'food_id': food_name_to_id_map[food_name],
                        'quantity_in_grams': ingredient['quantity_grams'],
                        'display_unit': ingredient.get('display_unit', f"{ingredient['quantity_grams']}g")
                    })
                else:
                    foods_not_found.append(food_name)
            
            # Inserir ingredientes da receita
            if recipe_ingredients:
                supabase.table('recipe_ingredients').insert(recipe_ingredients).execute()
            
            result_message = f"Receita '{recipe_name}' criada com sucesso!"
            if foods_not_found:
                result_message += f" Alimentos não encontrados: {', '.join(foods_not_found)}"
            
            return {
                "success": True,
                "message": result_message,
                "recipe_id": recipe_id,
                "ingredients_added": len(recipe_ingredients),
                "foods_not_found": foods_not_found
            }
        
        # Receita criada sem ingredientes
        return {
            "success": True,
            "message": f"Receita '{recipe_name}' criada com sucesso (sem ingredientes)!",
            "recipe_id": recipe_id
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Erro ao criar receita: {str(e)}"
        }


def register_complete_meal_plan(phone_number: str, plan_data: dict):
    """
    Função completa para registrar um plano alimentar seguindo exatamente o guia fornecido.
    
    Args:
        phone_number: Telefone do usuário
        plan_data: JSON completo do plano no formato do guia:
        {
            "planName": "Plano de Cutting - Foco em Proteína",
            "startDate": "2025-09-01", 
            "endDate": "2025-12-01",
            "weeklyPlan": {
                "segunda-feira": [
                    {"mealType": "Café da Manhã", "recipeName": "Ovos com Café", "order": 1}
                ],
                ...
            }
        }
    """
    try:
        # Buscar usuário pelo telefone
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        
        if not user_result.data:
            return {
                "success": False,
                "message": "Usuário não encontrado"
            }
        
        user_id = user_result.data[0]['id']
        
        # Passo 1: Desativar planos antigos
        supabase.table('user_meal_plans').update({
            'is_active': False
        }).eq('user_id', user_id).execute()
        
        # Passo 2: Criar o novo plano
        plan_result = supabase.table('user_meal_plans').insert({
            'user_id': user_id,
            'name': plan_data['planName'],
            'start_date': plan_data['startDate'],
            'end_date': plan_data['endDate'],
            'is_active': True
        }).execute()
        
        if not plan_result.data:
            return {
                "success": False,
                "message": "Falha ao criar o plano: Erro na inserção do plano principal"
            }
        
        new_plan_id = plan_result.data[0]['id']
        
        # Passo 3: Mapear nomes de receitas para IDs
        weekly_plan = plan_data.get('weeklyPlan', {})
        recipe_names = list(set([
            meal['recipeName'] 
            for day_meals in weekly_plan.values() 
            for meal in day_meals
        ]))
        
        if not recipe_names:
            return {
                "success": True,
                "message": f"Plano '{plan_data['planName']}' criado sem refeições específicas",
                "plan_id": new_plan_id
            }
        
        # Buscar receitas existentes
        recipes_result = supabase.table('recipes').select('id, name').in_('name', recipe_names).execute()
        recipe_name_to_id_map = {recipe['name']: recipe['id'] for recipe in recipes_result.data}
        
        # Passo 4: Preparar e inserir as refeições
        meals_to_insert = []
        recipes_not_found = []
        
        for day, meals in weekly_plan.items():
            for meal in meals:
                recipe_name = meal['recipeName']
                recipe_id = recipe_name_to_id_map.get(recipe_name)
                
                if recipe_id:
                    meals_to_insert.append({
                        'user_meal_plan_id': new_plan_id,
                        'day_of_week': day,
                        'meal_type': meal['mealType'],
                        'recipe_id': recipe_id,
                        'display_order': meal['order']
                    })
                else:
                    recipes_not_found.append(recipe_name)
        
        # Inserir refeições
        if meals_to_insert:
            insert_result = supabase.table('plan_meals').insert(meals_to_insert).execute()
            if not insert_result.data:
                # Em um cenário real, deveria fazer rollback do plano criado
                return {
                    "success": False,
                    "message": "Falha ao inserir as refeições do plano"
                }
        
        # Resultado final
        result = {
            "success": True,
            "plan_id": new_plan_id,
            "message": f"Plano '{plan_data['planName']}' registrado com sucesso!",
            "meals_registered": len(meals_to_insert)
        }
        
        if recipes_not_found:
            result["warning"] = f"Receitas não encontradas: {', '.join(recipes_not_found)}"
            result["recipes_not_found"] = recipes_not_found
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Falha ao registrar plano: {str(e)}"
        }


# Novas funções para consulta e edição de planos alimentares
def get_user_timezone_offset(phone_number: str):
    """Obtém o offset de timezone baseado na localização do usuário no onboarding"""
    try:
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return -3  # Default Brasil se não encontrar usuário
        
        user_id = user_result.data[0]['id']
        
        # Busca resposta da pergunta de localização (step 20, field_name 'location')
        location_response = supabase.table('onboarding_responses').select('response_value').eq('user_id', user_id).execute()
        
        if not location_response.data:
            return -3  # Default Brasil se não tiver onboarding
        
        # Procura pela resposta de location
        location_value = None
        for response in location_response.data:
            # Assumindo que uma das respostas contém a localização
            response_val = response.get('response_value', '').lower()
            if any(country in response_val for country in ['brazil', 'brasil', 'br']):
                return -3  # Brasil UTC-3
            elif any(country in response_val for country in ['usa', 'united states', 'america']):
                return -5  # EST UTC-5 (pode variar)
            elif any(country in response_val for country in ['portugal', 'pt']):
                return 0   # UTC+0
            elif any(country in response_val for country in ['argentina', 'ar']):
                return -3  # UTC-3
            elif any(country in response_val for country in ['chile', 'cl']):
                return -3  # UTC-3
            # Adicione mais países conforme necessário
        
        return -3  # Default Brasil
        
    except Exception as e:
        print(f"Erro ao buscar timezone: {str(e)}")
        return -3  # Default Brasil em caso de erro


def detect_future_promises(ai_response: str, user_message: str, user_context) -> bool:
    """
    Detecta se a IA está prometendo fazer algo no futuro ao invés de executar agora.
    Retorna True se detectar promessas futuras que deveriam ser executadas imediatamente.
    """
    try:
        if not ai_response:
            return False
        
        # Converte para lowercase para análise
        response_lower = ai_response.lower()
        message_lower = user_message.lower()
        
        # Padrões de promessas futuras que indicam ação que deveria ser executada agora
        future_promise_patterns = [
            "vou criar",
            "vou elaborar", 
            "vou desenvolver",
            "vou preparar",
            "vou fazer",
            "vou montar",
            "vou gerar",
            "irei criar",
            "irei elaborar",
            "criarei um",
            "elaborarei um",
            "farei um",
            "montarei um",
            "let me create",
            "i will create",
            "i'll create",
            "i will prepare",
            "i'll prepare"
        ]
        
        # Contextos onde a ação deveria ser executada imediatamente
        immediate_action_contexts = [
            ("plano", ["treino", "exercicio", "exercício", "musculação", "workout", "training"]),
            ("plano", ["alimentar", "nutricao", "nutrição", "meal", "nutrition", "dieta"]),
            ("criar", ["treino", "exercicio", "exercício", "workout", "training"]),
            ("criar", ["alimentar", "nutricao", "nutrição", "meal", "nutrition", "dieta"]),
            ("montar", ["treino", "exercicio", "exercício", "workout"]),
            ("elaborar", ["treino", "exercicio", "exercício", "workout"]),
            ("check", ["plano", "status", "progresso"])
        ]
        
        # Verifica se há promessa futura na resposta
        has_future_promise = any(pattern in response_lower for pattern in future_promise_patterns)
        
        if not has_future_promise:
            return False
        
        # Verifica se o contexto indica ação que deveria ser executada imediatamente
        has_immediate_context = False
        for action, keywords in immediate_action_contexts:
            if action in message_lower:
                if any(keyword in message_lower for keyword in keywords):
                    has_immediate_context = True
                    break
        
        # Se tem promessa futura + contexto de ação imediata = detecta problema
        if has_future_promise and has_immediate_context:
            print(f"🚨 PROMESSA FUTURA DETECTADA:")
            print(f"   - Promessa encontrada: {[p for p in future_promise_patterns if p in response_lower]}")
            print(f"   - Contexto de ação imediata: {has_immediate_context}")
            print(f"   - Mensagem do usuário: '{user_message[:50]}...'")
            print(f"   - Resposta da IA: '{ai_response[:100]}...'")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Erro na detecção de promessas futuras: {e}")
        return False


def execute_immediate_action(user_message: str, phone_number: str, user_context) -> str:
    """
    Executa ação imediata quando detecta que a IA prometeu fazer algo no futuro.
    Tenta executar a ação e retorna uma resposta apropriada.
    """
    try:
        message_lower = user_message.lower()
        
        # Detecta tipo de ação necessária
        if any(word in message_lower for word in ["plano", "treino", "exercicio", "exercício", "workout", "training"]):
            # Ação de treino necessária
            print(f"🏋️ Executando ação imediata: PLANO DE TREINO")
            
            # Verifica se já tem plano
            check_result = execute_tool("check_user_training_plan", {}, phone_number)
            if check_result and check_result.get('has_plan'):
                return f"✅ Você já possui um plano de treino ativo: {check_result.get('plan_details', {}).get('name', 'Plano Personalizado')}\n\nPosso ajudar com mais informações sobre seu treino atual!"
            
            # Busca dados do onboarding
            onboarding_result = execute_tool("get_user_onboarding_responses", {}, phone_number)
            if not onboarding_result or not onboarding_result.get('success'):
                return "❌ Para criar seu plano personalizado, preciso que complete seu onboarding primeiro. Vou te ajudar com isso!"
            
            # Cria plano de treino
            training_plan = {
                "days": [
                    {
                        "day_of_week": 1,
                        "workout_name": "Treino A - Peito e Tríceps",
                        "exercises": [
                            {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "8-12", "rest_seconds": 90},
                            {"exercise_name": "Agachamento", "sets": 3, "reps": "10-15", "rest_seconds": 90},
                            {"exercise_name": "Prancha", "sets": 3, "reps": "30-60s", "rest_seconds": 60}
                        ]
                    },
                    {
                        "day_of_week": 3,
                        "workout_name": "Treino B - Costas e Bíceps", 
                        "exercises": [
                            {"exercise_name": "Agachamento", "sets": 3, "reps": "8-12", "rest_seconds": 90},
                            {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "10-15", "rest_seconds": 90},
                            {"exercise_name": "Prancha", "sets": 3, "reps": "30-60s", "rest_seconds": 60}
                        ]
                    }
                ]
            }
            
            create_result = execute_tool("create_weekly_training_plan", {
                "plan_name": "Plano Personalizado Aleen IA",
                "objective": "Condicionamento Geral",
                "weekly_workouts": training_plan
            }, phone_number)
            
            if create_result and create_result.get('success'):
                return f"🎉 Perfeito! Acabei de criar e salvar seu plano de treino personalizado!\n\n✅ **{create_result.get('plan_name', 'Plano Personalizado')}**\n🎯 Objetivo: {create_result.get('objective', 'Condicionamento Geral')}\n📅 Duração: {create_result.get('duration', '30 dias')}\n\nSeu plano já está ativo e você pode começar hoje mesmo! Quer saber quais são os treinos de hoje?"
            else:
                # NUNCA mostra erro técnico - mensagem sutil e humana
                return f"😅 Estou com algumas dificuldades técnicas no momento para organizar seu plano.\n\nEnquanto isso, que tal me contar mais sobre seus objetivos? Quer focar em ganhar força, definição muscular ou melhorar o condicionamento?\n\nAssim que tudo normalizar, vou criar o plano perfeito para você! 💪"
        
        elif any(word in message_lower for word in ["plano", "alimentar", "nutricao", "nutrição", "meal", "nutrition", "dieta"]):
            # Ação de nutrição necessária
            print(f"🥗 Executando ação imediata: PLANO ALIMENTAR")
            
            # Verifica se já tem plano
            check_result = execute_tool("check_user_meal_plan", {}, phone_number)
            if check_result and check_result.get('has_plan'):
                return f"✅ Você já possui um plano alimentar ativo: {check_result.get('plan_details', {}).get('name', 'Plano Personalizado')}\n\nPosso ajudar com mais informações sobre sua alimentação atual!"
            
            # Busca dados do onboarding  
            onboarding_result = execute_tool("get_user_onboarding_responses", {}, phone_number)
            if not onboarding_result or not onboarding_result.get('success'):
                return "❌ Para criar seu plano alimentar personalizado, preciso que complete seu onboarding primeiro. Vou te ajudar com isso!"
            
            # Cria plano alimentar básico
            create_result = execute_tool("create_weekly_meal_plan", {
                "plan_name": "Plano Alimentar Personalizado Aleen IA"
            }, phone_number)
            
            if create_result and create_result.get('success'):
                return f"🎉 Perfeito! Acabei de criar e salvar seu plano alimentar personalizado!\n\n✅ **{create_result.get('plan_name', 'Plano Personalizado')}**\n📅 Duração: 7 dias\n\nSeu plano já está ativo! Quer saber quais são as refeições de hoje?"
            else:
                # NUNCA mostra erro técnico - mensagem sutil e humana
                return f"😅 Estou com algumas dificuldades técnicas no momento para montar seu cardápio.\n\nEnquanto isso, que tal me contar sobre suas preferências alimentares? Tem alguma restrição ou alimento favorito?\n\nAssim que tudo normalizar, vou preparar um plano alimentar incrível para você! 🥗"
        
        # Se não conseguiu identificar a ação específica
        return None
        
    except Exception as e:
        print(f"❌ Erro na execução de ação imediata: {e}")
        return None


def get_user_current_meal(phone_number: str):
    """Obtém a próxima refeição do usuário baseada no horário atual"""
    try:
        from datetime import datetime, timedelta
        
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Busca plano ativo
        plan_result = supabase.table('user_meal_plans').select('id').eq('user_id', user_id).eq('is_active', True).execute()
        if not plan_result.data:
            return {"error": "Nenhum plano alimentar ativo encontrado"}
        
        plan_id = plan_result.data[0]['id']
        
        # Determina dia da semana e refeição atual - TIMEZONE DO USUÁRIO
        timezone_offset = get_user_timezone_offset(phone_number)
        current_time = datetime.utcnow() + timedelta(hours=timezone_offset)
        days_pt = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
        current_day = days_pt[current_time.weekday()]
        
        # Determina refeição baseada no horário
        hour = current_time.hour
        if hour < 10:
            meal_type = "Café da Manhã"
        elif hour < 14:
            meal_type = "Almoço"
        elif hour < 18:
            meal_type = "Lanche da Tarde"
        else:
            meal_type = "Jantar"
        
        # Busca refeição específica
        meal_result = supabase.table('plan_meals').select('''
            id, day_of_week, meal_type, display_order,
            recipes (name, description)
        ''').eq('user_meal_plan_id', plan_id).eq('day_of_week', current_day).eq('meal_type', meal_type).execute()
        
        if not meal_result.data:
            return {
                "message": f"Nenhuma refeição encontrada para {meal_type} de {current_day}",
                "current_day": current_day,
                "current_meal_type": meal_type
            }
        
        return {
            "success": True,
            "current_meal": meal_result.data[0],
            "current_day": current_day,
            "current_meal_type": meal_type,
            "current_time": current_time.strftime("%H:%M")
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar refeição atual: {str(e)}"}


def get_user_meal_plan_details(phone_number: str):
    """Obtém todos os detalhes do plano alimentar ativo do usuário"""
    try:
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Busca plano ativo com todas as refeições
        plan_result = supabase.table('user_meal_plans').select('''
            id, name, start_date, end_date, created_at,
            plan_meals (
                id, day_of_week, meal_type, display_order,
                recipes (name, description)
            )
        ''').eq('user_id', user_id).eq('is_active', True).execute()
        
        if not plan_result.data:
            return {"error": "Nenhum plano alimentar ativo encontrado"}
        
        plan = plan_result.data[0]
        
        # Organiza refeições por dia da semana
        meals_by_day = {}
        for meal in plan['plan_meals']:
            day = meal['day_of_week']
            if day not in meals_by_day:
                meals_by_day[day] = []
            meals_by_day[day].append({
                "meal_type": meal['meal_type'],
                "recipe_name": meal['recipes']['name'],
                "recipe_description": meal['recipes'].get('description', ''),
                "order": meal['display_order']
            })
        
        # Ordena refeições por ordem de exibição
        for day in meals_by_day:
            meals_by_day[day].sort(key=lambda x: x['order'])
        
        return {
            "success": True,
            "plan_name": plan['name'],
            "start_date": plan['start_date'],
            "end_date": plan['end_date'],
            "created_at": plan['created_at'],
            "meals_by_day": meals_by_day,
            "total_meals": len(plan['plan_meals'])
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar detalhes do plano: {str(e)}"}


def get_today_meals(phone_number: str):
    """Obtém todas as refeições do dia atual do usuário"""
    try:
        from datetime import datetime, timedelta
        
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        if not user_result.data:
            return {"error": "Usuário não encontrado"}
        
        user_id = user_result.data[0]['id']
        
        # Busca plano ativo
        plan_result = supabase.table('user_meal_plans').select('id, name').eq('user_id', user_id).eq('is_active', True).execute()
        if not plan_result.data:
            return {"error": "Nenhum plano alimentar ativo encontrado"}
        
        plan_id = plan_result.data[0]['id']
        plan_name = plan_result.data[0]['name']
        
        # Determina dia atual - TIMEZONE DO USUÁRIO
        timezone_offset = get_user_timezone_offset(phone_number)
        current_time = datetime.utcnow() + timedelta(hours=timezone_offset)
        days_pt = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
        today = days_pt[current_time.weekday()]
        
        # Busca todas as refeições do dia
        meals_result = supabase.table('plan_meals').select('''
            id, meal_type, display_order,
            recipes (name, description)
        ''').eq('user_meal_plan_id', plan_id).eq('day_of_week', today).order('display_order').execute()
        
        if not meals_result.data:
            return {
                "message": f"Nenhuma refeição encontrada para hoje ({today})",
                "today": today
            }
        
        meals = []
        for meal in meals_result.data:
            meals.append({
                "meal_type": meal['meal_type'],
                "recipe_name": meal['recipes']['name'],
                "recipe_description": meal['recipes'].get('description', ''),
                "order": meal['display_order']
            })
        
        return {
            "success": True,
            "plan_name": plan_name,
            "today": today,
            "date": current_time.strftime("%Y-%m-%d"),
            "meals": meals,
            "total_meals": len(meals)
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar refeições de hoje: {str(e)}"}


def suggest_alternative_recipes(meal_type: str, exclude_recipe: str = None):
    """Sugere receitas alternativas REAIS do banco de dados por categoria"""
    try:
        # Busca TODAS as receitas disponíveis no banco
        query = supabase.table('recipes').select('name, description')
        
        # Exclui receita específica se fornecida
        if exclude_recipe:
            query = query.neq('name', exclude_recipe)
        
        recipes_result = query.execute()
        
        if not recipes_result.data:
            return {"error": "Nenhuma receita encontrada no banco de dados"}
        
        # Filtra receitas adequadas baseado no tipo de refeição
        suitable_recipes = []
        for recipe in recipes_result.data:
            recipe_name = recipe['name'].lower()
            
            # Lógica para categorizar receitas por tipo de refeição
            if meal_type == "Café da Manhã":
                breakfast_keywords = ['omelete', 'vitamina', 'smoothie', 'panqueca', 'aveia', 'tapioca', 'ovos']
                if any(keyword in recipe_name for keyword in breakfast_keywords):
                    suitable_recipes.append(recipe)
            elif meal_type == "Lanche da Tarde":
                snack_keywords = ['iogurte', 'mix', 'castanhas', 'pasta', 'amendoim', 'banana']
                if any(keyword in recipe_name for keyword in snack_keywords):
                    suitable_recipes.append(recipe)
            elif meal_type in ["Almoço", "Jantar"]:
                main_keywords = ['frango', 'peixe', 'salmão', 'carne', 'quinoa', 'salada', 'sopa', 'wrap', 'tilápia']
                if any(keyword in recipe_name for keyword in main_keywords):
                    suitable_recipes.append(recipe)
        
        # Se não encontrou por keywords, pega todas as receitas disponíveis
        if not suitable_recipes:
            suitable_recipes = recipes_result.data
        
        # Limita a 4 sugestões e formata com números
        limited_suggestions = suitable_recipes[:4]
        
        # Formata as sugestões com números para facilitar escolha do usuário
        formatted_suggestions = []
        for i, recipe in enumerate(limited_suggestions, 1):
            formatted_suggestions.append({
                "option_number": i,
                "recipe_name": recipe['name'],
                "description": recipe.get('description', ''),
                "formatted_text": f"{i}. {recipe['name']}"
            })
        
        return {
            "success": True,
            "meal_type": meal_type,
            "excluded_recipe": exclude_recipe,
            "suggestions": formatted_suggestions,
            "total_suggestions": len(formatted_suggestions),
            "message": "Todas as receitas são REAIS e existem no banco de dados"
        }
        
    except Exception as e:
        return {"error": f"Erro ao buscar sugestões: {str(e)}"}


def update_meal_in_plan(phone_number: str, day_of_week: str, meal_type: str, new_recipe_name: str):
    """Atualiza uma refeição específica no plano alimentar do usuário"""
    try:
        print(f"🔍 UPDATE_MEAL_IN_PLAN DEBUG:")
        print(f"📞 Telefone: {phone_number}")
        print(f"📅 Dia: {day_of_week}")
        print(f"🍽️ Tipo: {meal_type}")
        print(f"🥘 Nova receita: {new_recipe_name}")
        
        # Busca usuário
        user_result = supabase.table('users').select('id').eq('phone', phone_number).execute()
        print(f"👤 Usuário encontrado: {user_result.data}")
        
        if not user_result.data:
            return {"error": f"Usuário não encontrado com telefone {phone_number}"}
        
        user_id = user_result.data[0]['id']
        print(f"🆔 User ID: {user_id}")
        
        # Busca plano ativo
        plan_result = supabase.table('user_meal_plans').select('id, name').eq('user_id', user_id).eq('is_active', True).execute()
        print(f"📋 Plano encontrado: {plan_result.data}")
        
        if not plan_result.data:
            return {"error": "Nenhum plano alimentar ativo encontrado"}
        
        plan_id = plan_result.data[0]['id']
        plan_name = plan_result.data[0]['name']
        print(f"📋 Plan ID: {plan_id}")
        
        # Verifica se a nova receita existe (busca case-insensitive)
        recipe_result = supabase.table('recipes').select('id, name').ilike('name', new_recipe_name).execute()
        print(f"🥘 Receita encontrada (exata): {recipe_result.data}")
        
        if not recipe_result.data:
            # Tenta busca com LIKE parcial
            recipe_result = supabase.table('recipes').select('id, name').ilike('name', f'%{new_recipe_name}%').execute()
            print(f"🥘 Receita encontrada (parcial): {recipe_result.data}")
            
        if not recipe_result.data:
            return {"error": f"Receita '{new_recipe_name}' não encontrada no banco de dados"}
        
        new_recipe_id = recipe_result.data[0]['id']
        actual_recipe_name = recipe_result.data[0]['name']  # Nome correto do banco
        print(f"🥘 Recipe ID: {new_recipe_id} - Nome: {actual_recipe_name}")
        
        # Busca a refeição existente para atualizar
        meal_result = supabase.table('plan_meals').select('id, recipes(name)').eq('user_meal_plan_id', plan_id).eq('day_of_week', day_of_week).eq('meal_type', meal_type).execute()
        print(f"🍽️ Refeição atual encontrada: {meal_result.data}")
        
        if not meal_result.data:
            return {"error": f"Refeição não encontrada para {meal_type} de {day_of_week}"}
        
        meal_id = meal_result.data[0]['id']
        old_recipe_name = meal_result.data[0]['recipes']['name']
        print(f"🍽️ Meal ID: {meal_id} - Receita antiga: {old_recipe_name}")
        
        # Atualiza a refeição
        print(f"🔄 Atualizando meal_id {meal_id} para recipe_id {new_recipe_id}")
        update_result = supabase.table('plan_meals').update({
            'recipe_id': new_recipe_id
        }).eq('id', meal_id).execute()
        
        print(f"✅ Resultado da atualização: {update_result.data}")
        
        if update_result.data:
            return {
                "success": True,
                "message": f"Refeição atualizada com sucesso!",
                "plan_name": plan_name,
                "day": day_of_week,
                "meal_type": meal_type,
                "old_recipe": old_recipe_name,
                "new_recipe": actual_recipe_name,  # Usa nome correto do banco
                "updated_at": update_result.data[0],
                "debug_info": {
                    "phone": phone_number,
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "meal_id": meal_id,
                    "new_recipe_id": new_recipe_id
                }
            }
        else:
            return {"error": "Falha ao atualizar a refeição"}
        
    except Exception as e:
        print(f"❌ ERRO em update_meal_in_plan: {str(e)}")
        return {"error": f"Erro ao atualizar refeição: {str(e)}"}


def interpret_user_choice(user_choice: str, meal_type: str, recent_suggestions: list = None):
    """Interpreta escolhas do usuário baseado nas SUGESTÕES REAIS da IA"""
    try:
        user_choice_lower = user_choice.lower().strip()
        
        print(f"🔍 INTERPRETANDO ESCOLHA: '{user_choice}'")
        print(f"📋 SUGESTÕES RECENTES: {recent_suggestions}")
        
        # PRIORIDADE 1: Se temos sugestões da IA, mapeia baseado nelas
        if recent_suggestions:
            # Verifica se é escolha numérica (1, 2, 3, etc)
            import re
            numeric_match = re.search(r'\b(\d+)\b', user_choice_lower)
            if numeric_match:
                choice_number = int(numeric_match.group(1))
                if 1 <= choice_number <= len(recent_suggestions):
                    selected = recent_suggestions[choice_number - 1]
                    recipe_name = selected.get('recipe_name')
                    print(f"✅ ESCOLHA NUMÉRICA {choice_number} = {recipe_name}")
                    return {
                        "success": True,
                        "interpretation": "numeric_from_ai_suggestions",
                        "choice_number": choice_number,
                        "recipe_name": recipe_name,
                        "message": f"Usuário escolheu opção {choice_number}: {recipe_name}"
                    }
            
            # Verifica referências ordinais (primeira, segunda, etc)
            ordinal_mapping = {
                'primeira': 1, 'primeiro': 1, '1ª': 1,
                'segunda': 2, 'segundo': 2, '2ª': 2,
                'terceira': 3, 'terceiro': 3, '3ª': 3,
                'quarta': 4, 'quarto': 4, '4ª': 4
            }
            
            for ordinal, number in ordinal_mapping.items():
                if ordinal in user_choice_lower:
                    if 1 <= number <= len(recent_suggestions):
                        selected = recent_suggestions[number - 1]
                        recipe_name = selected.get('recipe_name')
                        print(f"✅ ESCOLHA ORDINAL '{ordinal}' = {recipe_name}")
                        return {
                            "success": True,
                            "interpretation": "ordinal_from_ai_suggestions",
                            "choice_number": number,
                            "recipe_name": recipe_name,
                            "message": f"Usuário escolheu a {ordinal} opção: {recipe_name}"
                        }
            
            # Busca por nome/palavra-chave nas sugestões da IA
            for i, suggestion in enumerate(recent_suggestions, 1):
                recipe_name = suggestion.get('recipe_name', '').lower()
                
                # Match exato ou parcial
                if user_choice_lower in recipe_name or recipe_name in user_choice_lower:
                    print(f"✅ MATCH DIRETO '{user_choice}' = {suggestion.get('recipe_name')}")
                    return {
                        "success": True,
                        "interpretation": "name_from_ai_suggestions",
                        "choice_number": i,
                        "recipe_name": suggestion.get('recipe_name'),
                        "message": f"Usuário escolheu por nome: {suggestion.get('recipe_name')}"
                    }
                
                # Match por palavras-chave
                recipe_words = recipe_name.split()
                choice_words = user_choice_lower.split()
                
                for choice_word in choice_words:
                    if len(choice_word) > 3:  # Palavras com mais de 3 chars
                        for recipe_word in recipe_words:
                            if choice_word in recipe_word or recipe_word in choice_word:
                                print(f"✅ MATCH PALAVRA '{choice_word}' = {suggestion.get('recipe_name')}")
                                return {
                                    "success": True,
                                    "interpretation": "keyword_from_ai_suggestions",
                                    "choice_number": i,
                                    "recipe_name": suggestion.get('recipe_name'),
                                    "message": f"Usuário escolheu por palavra-chave: {suggestion.get('recipe_name')}"
                                }
        
        # PRIORIDADE 2: Se não tem sugestões, busca no banco geral
        print("🔍 Buscando no banco geral...")
        recipes_result = supabase.table('recipes').select('name').execute()
        
        if recipes_result.data:
            best_match = None
            best_score = 0
            
            for recipe in recipes_result.data:
                recipe_name = recipe['name'].lower()
                
                # Match exato
                if user_choice_lower == recipe_name or user_choice_lower in recipe_name:
                    print(f"✅ MATCH EXATO NO BANCO: {recipe['name']}")
                    return {
                        "success": True,
                        "interpretation": "exact_match_database",
                        "recipe_name": recipe['name'],
                        "message": f"Encontrou receita exata: {recipe['name']}"
                    }
                
                # Match por palavras (scoring)
                recipe_words = set(recipe_name.split())
                choice_words = set(user_choice_lower.split())
                common_words = recipe_words & choice_words
                
                if common_words:
                    score = len(common_words) / len(recipe_words)
                    if score > best_score:
                        best_score = score
                        best_match = recipe
            
            if best_match and best_score > 0.3:
                print(f"✅ MELHOR MATCH NO BANCO: {best_match['name']} (score: {best_score})")
                return {
                    "success": True,
                    "interpretation": "partial_match_database", 
                    "recipe_name": best_match['name'],
                    "confidence": best_score,
                    "message": f"Melhor match encontrado: {best_match['name']}"
                }
        
        # Não conseguiu interpretar
        print(f"❌ NÃO CONSEGUIU INTERPRETAR: '{user_choice}'")
        return {
            "success": False,
            "interpretation": "unclear",
            "message": f"Não consegui interpretar '{user_choice}'. Pode repetir o número da opção ou o nome da receita?",
            "user_choice": user_choice
        }
        
    except Exception as e:
        print(f"❌ ERRO na interpretação: {str(e)}")
        return {
            "success": False,
            "error": f"Erro ao interpretar escolha: {str(e)}"
        }


def get_recipe_ingredients(recipe_name: str):
    """Busca todos os ingredientes de uma receita específica com quantidades"""
    try:
        print(f"🔍 BUSCANDO INGREDIENTES DA RECEITA: {recipe_name}")
        
        # Busca a receita e seus ingredientes
        result = supabase.table('recipe_ingredients').select('''
            recipes(name, description),
            foods(name),
            quantity_in_grams,
            display_unit
        ''').eq('recipes.name', recipe_name).execute()
        
        print(f"📋 Resultado da busca: {result.data}")
        
        if not result.data:
            # Tenta busca case-insensitive
            recipes_result = supabase.table('recipes').select('id, name').ilike('name', f'%{recipe_name}%').execute()
            
            if not recipes_result.data:
                return {"error": f"Receita '{recipe_name}' não encontrada"}
            
            recipe_id = recipes_result.data[0]['id']
            actual_name = recipes_result.data[0]['name']
            
            # Busca ingredientes pelo ID
            ingredients_result = supabase.table('recipe_ingredients').select('''
                foods(name),
                quantity_in_grams,
                display_unit
            ''').eq('recipe_id', recipe_id).execute()
            
            if not ingredients_result.data:
                return {
                    "recipe_name": actual_name,
                    "ingredients": [],
                    "message": f"Receita '{actual_name}' encontrada mas não tem ingredientes cadastrados"
                }
            
            # Formata os ingredientes
            ingredients = []
            for item in ingredients_result.data:
                ingredients.append({
                    "name": item['foods']['name'],
                    "quantity_grams": float(item['quantity_in_grams']),
                    "display_unit": item['display_unit']
                })
            
            return {
                "success": True,
                "recipe_name": actual_name,
                "ingredients": ingredients,
                "total_ingredients": len(ingredients),
                "message": f"Encontrados {len(ingredients)} ingredientes para {actual_name}"
            }
        
        # Se encontrou diretamente
        recipe_info = result.data[0]['recipes']
        ingredients = []
        
        for item in result.data:
            ingredients.append({
                "name": item['foods']['name'],
                "quantity_grams": float(item['quantity_in_grams']),
                "display_unit": item['display_unit']
            })
        
        return {
            "success": True,
            "recipe_name": recipe_info['name'],
            "recipe_description": recipe_info['description'],
            "ingredients": ingredients,
            "total_ingredients": len(ingredients),
            "message": f"Ingredientes da receita {recipe_info['name']}"
        }
        
    except Exception as e:
        print(f"❌ ERRO em get_recipe_ingredients: {str(e)}")
        return {"error": f"Erro ao buscar ingredientes: {str(e)}"}


# Executor das tools
def execute_tool(tool_name: str, arguments: dict, context_phone: str = None):
    """Executa uma tool baseada no nome"""
    if tool_name == "get_onboarding_questions":
        return get_onboarding_questions()
    elif tool_name == "create_user_and_save_onboarding":
        # O telefone deve vir do contexto da conversa, não dos argumentos
        phone = context_phone or arguments.get('phone', '')
        
        if not phone:
            return {
                "success": False,
                "message": "Telefone não fornecido no contexto da conversa",
                "user_id": None
            }
            
        return create_user_and_save_onboarding(
            name=arguments.get('name'),
            age=arguments.get('age'), 
            email=arguments.get('email'),
            phone=phone
        )
    elif tool_name == "check_user_meal_plan":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return check_user_meal_plan(context_phone)
    elif tool_name == "get_user_onboarding_responses":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return get_user_onboarding_responses(context_phone)
    elif tool_name == "get_available_foods":
        return get_available_foods()
    elif tool_name == "create_weekly_meal_plan":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return create_weekly_meal_plan(
            phone_number=context_phone,
            plan_name=arguments.get('plan_name'),
            weekly_meals=arguments.get('weekly_meals')
        )
    
    elif tool_name == "create_recipe_with_ingredients":
        return create_recipe_with_ingredients(
            recipe_name=arguments.get('recipe_name'),
            description=arguments.get('description'),
            ingredients_data=arguments.get('ingredients_data')
        )
    
    elif tool_name == "register_complete_meal_plan":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return register_complete_meal_plan(
            phone_number=context_phone,
            plan_data=arguments.get('plan_data')
        )
    
    elif tool_name == "get_user_current_meal":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return get_user_current_meal(phone_number=context_phone)
    
    elif tool_name == "get_user_meal_plan_details":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return get_user_meal_plan_details(phone_number=context_phone)
    
    elif tool_name == "get_today_meals":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return get_today_meals(phone_number=context_phone)
    
    elif tool_name == "suggest_alternative_recipes":
        return suggest_alternative_recipes(
            meal_type=arguments.get('meal_type'),
            exclude_recipe=arguments.get('exclude_recipe')
        )
    
    elif tool_name == "update_meal_in_plan":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return update_meal_in_plan(
            phone_number=context_phone,
            day_of_week=arguments.get('day_of_week'),
            meal_type=arguments.get('meal_type'),
            new_recipe_name=arguments.get('new_recipe_name')
        )
    
    elif tool_name == "interpret_user_choice":
        return interpret_user_choice(
            user_choice=arguments.get('user_choice'),
            meal_type=arguments.get('meal_type'),
            recent_suggestions=arguments.get('recent_suggestions')
        )
    
    elif tool_name == "get_recipe_ingredients":
        return get_recipe_ingredients(
            recipe_name=arguments.get('recipe_name')
        )
    
    # TRAINING TOOLS
    elif tool_name == "check_user_training_plan":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return check_user_workout_plan(phone_number=context_phone)
    
    elif tool_name == "get_available_exercises":
        return get_available_exercises(
            muscle_group=arguments.get('muscle_group'),
            equipment=arguments.get('equipment'),
            difficulty=arguments.get('difficulty')
        )
    
    elif tool_name == "create_weekly_training_plan":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return create_weekly_workout_plan(
            phone_number=context_phone,
            plan_name=arguments.get('plan_name'),
            objective=arguments.get('objective'),
            weekly_workouts=arguments.get('weekly_workouts')
        )
    
    elif tool_name == "get_today_workouts":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return get_today_workouts(phone_number=context_phone)
    
    elif tool_name == "get_user_workout_plan_details":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return get_user_workout_plan_details(phone_number=context_phone)
    
    elif tool_name == "suggest_alternative_exercises":
        return suggest_alternative_exercises(
            muscle_group=arguments.get('muscle_group'),
            exclude_exercise=arguments.get('exclude_exercise')
        )
    
    elif tool_name == "update_workout_exercise":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return update_workout_exercise(
            phone_number=context_phone,
            day_of_week=arguments.get('day_of_week'),
            workout_name=arguments.get('workout_name'),
            old_exercise_name=arguments.get('old_exercise_name'),
            new_exercise_name=arguments.get('new_exercise_name')
        )
    
    elif tool_name == "get_exercise_details":
        return get_exercise_details(
            exercise_name=arguments.get('exercise_name')
        )
    
    elif tool_name == "analyze_onboarding_for_workout_plan":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return analyze_onboarding_for_workout_plan(phone_number=context_phone)
    
    elif tool_name == "record_workout_session":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return record_workout_session(
            phone_number=context_phone,
            workout_date=arguments.get('workout_date'),
            workout_name=arguments.get('workout_name'),
            exercises_performed=arguments.get('exercises_performed'),
            duration_minutes=arguments.get('duration_minutes'),
            intensity_rating=arguments.get('intensity_rating')
        )
    
    elif tool_name == "get_workout_progress":
        if not context_phone:
            return {"error": "Telefone não disponível no contexto"}
        return get_workout_progress(
            phone_number=context_phone,
            period_days=arguments.get('period_days', 30)
        )
    
    else:
        return {"error": f"Tool '{tool_name}' não encontrada"}

# Evolution API Integration
class EvolutionAPIService:
    def __init__(self):
        self.base_url = os.getenv("EVOLUTION_API_BASE_URL", "")
        self.api_key = os.getenv("EVOLUTION_API_KEY", "")
        self.instance = os.getenv("EVOLUTION_INSTANCE", "")
        
        if not all([self.base_url, self.api_key, self.instance]):
            print("⚠️ Evolution API configuration incomplete")
    
    def clean_phone_number(self, phone: str) -> str:
        """Remove caracteres especiais do número de telefone"""
        return re.sub(r'[^\d]', '', phone)
    
    def split_message(self, text: str, max_length: int = 200) -> List[str]:
        """Quebra mensagem longa em múltiplas partes respeitando quebras naturais"""
        if len(text) <= max_length:
            return [text]
        
        # Primeiro, quebra pelos \n\n que a IA já inseriu intencionalmente
        parts = text.split('\\n\\n')  # Split por \n\n literal que vem da IA
        if len(parts) == 1:
            # Se não tem \n\n literal, tenta \n\n normal
            parts = text.split('\n\n')
        
        messages = []
        current_message = ""
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Se a parte sozinha cabe no limite
            if len(part) <= max_length:
                # Se adicionar essa parte excede o limite, envia a atual e inicia nova
                if current_message and len(current_message + " " + part) > max_length:
                    messages.append(current_message.strip())
                    current_message = part
                elif current_message:
                    current_message += " " + part
                else:
                    current_message = part
            else:
                # Parte muito longa, quebra por frases
                if current_message:
                    messages.append(current_message.strip())
                    current_message = ""
                
                sentences = re.split(r'(?<=[.!?])\s+', part)
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    if current_message and len(current_message + " " + sentence) > max_length:
                        messages.append(current_message.strip())
                        current_message = sentence
                    elif len(sentence) > max_length:
                        # Frase muito longa, força quebra por palavras
                        if current_message:
                            messages.append(current_message.strip())
                            current_message = ""
                        
                        words = sentence.split()
                        for word in words:
                            if current_message and len(current_message + " " + word) > max_length:
                                messages.append(current_message.strip())
                                current_message = word
                            else:
                                current_message += " " + word if current_message else word
                    else:
                        current_message += " " + sentence if current_message else sentence
        
        if current_message:
            messages.append(current_message.strip())
        
        # Limpa as mensagens removendo \n extras e múltiplos espaços
        clean_messages = []
        for msg in messages:
            # Remove \n\n literais que podem ter sobrado
            cleaned = msg.replace('\\n\\n', ' ').replace('\\n', ' ').replace('\n', ' ')
            # Remove múltiplos espaços
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if cleaned:
                clean_messages.append(cleaned)
        
        return clean_messages if clean_messages else [text.replace('\\n\\n', ' ').replace('\\n', ' ')]
    
    def send_text_message(self, phone_number: str, text: str, delay: int = 3500) -> bool:
        """Envia mensagem de texto via Evolution API com quebra automática"""
        try:
            clean_number = self.clean_phone_number(phone_number)
            messages = self.split_message(text)
            
            print(f"📱 Enviando {len(messages)} mensagem(s) para {clean_number}")
            print(f"🔍 Mensagens quebradas:")
            for i, msg in enumerate(messages):
                print(f"   {i+1}. ({len(msg)} chars): {msg[:50]}...")
            
            for i, message in enumerate(messages):
                payload = {
                    "number": clean_number,
                    "text": message,
                    "options": {
                        "delay": delay,
                        "presence": "composing", 
                        "linkPreview": False
                    }
                }
                
                url = f"{self.base_url}/message/sendText/{self.instance}"
                
                headers = {
                    "Content-Type": "application/json",
                    "apikey": self.api_key
                }
                
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                
                if response.status_code in [200, 201]:
                    print(f"✅ Mensagem {i+1}/{len(messages)} enviada com sucesso")
                    if i < len(messages) - 1:  # Delay entre mensagens (só se não for a última)
                        print(f"⏱️ Aguardando {delay/1000}s antes da próxima mensagem...")
                        time.sleep(delay / 1000)  # Convert ms to seconds
                else:
                    print(f"❌ Erro ao enviar mensagem {i+1}: {response.status_code} - {response.text}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem via WhatsApp: {e}")
            return False

# Instanciar o serviço Evolution API
evolution_service = EvolutionAPIService()

class MessageRequest(BaseModel):
    user_id: str
    user_name: str
    message: str
    conversation_history: Optional[List[str]] = []
    recommended_agent: Optional[str] = None

class UserContext(BaseModel):
    has_account: bool = False
    onboarding_completed: bool = False
    user_type: str = "new_user"  # 'new_user' | 'incomplete_onboarding' | 'complete_user'
    onboarding_url: Optional[str] = None
    is_lead: bool = False
    is_user: bool = False

class WhatsAppMessageRequest(BaseModel):
    user_id: str
    user_name: str
    phone_number: str
    message: str
    conversation_history: Optional[List[str]] = []
    recommended_agent: Optional[str] = None
    send_to_whatsapp: bool = True
    user_context: Optional[UserContext] = None

class MessageResponse(BaseModel):
    response: str
    agent_used: str
    should_handoff: bool = False
    next_agent: Optional[str] = None

class WhatsAppMessageResponse(BaseModel):
    response: str
    agent_used: str
    should_handoff: bool = False
    next_agent: Optional[str] = None
    whatsapp_sent: bool = False
    messages_sent: int = 0

class SendWhatsAppRequest(BaseModel):
    phone_number: str
    message: str

# Cache para armazenar agentes do Supabase
agents_cache: Dict[str, Agent] = {}
agents_config: Dict[str, Dict] = {}

def load_agents_from_supabase():
    """Carrega os agentes e seus prompts do Supabase"""
    try:
        response = supabase.table('agents').select('*').execute()
        
        if not response.data:
            print("Nenhum agente encontrado no Supabase")
            return False
            
        global agents_cache, agents_config
        agents_cache.clear()
        agents_config.clear()
        
        # Mapeia os identifiers para tipos de agente (contexto FITNESS/NUTRIÇÃO)
        identifier_map = {
            'GREETING_WITHOUT_MEMORY': 'onboarding',  # Prompt fitness em inglês
            'DOUBT': 'support',                       # Prompt fitness em inglês  
            'SALES': 'sales',                         # Prompt fitness em inglês
            'OUT_CONTEXT': 'out_context',             # Agente para mensagens fora de contexto
            'ONBOARDING_REMINDER': 'onboarding_reminder',  # Agente para onboarding incompleto
            'nutrition': 'nutrition',                 # Agente especialista em nutrição
            'fitness': 'fitness',                     # Agente especialista em treinos
            'onboarding': 'onboarding',              # Agente de onboarding atualizado
            # Mantém compatibilidade com identifiers antigos
            'ONBOARDING_INIT': 'onboarding',
            'GREETING_WITH_MEMORY': 'onboarding',
            'ONBOARDING_PENDING': 'onboarding'
        }
        
        for agent_data in response.data:
            identifier = agent_data.get('identifier', '')
            agent_type = identifier_map.get(identifier, 'onboarding')
            
            # Sempre carrega o agente, pode sobrescrever se necessário
            agents_config[agent_type] = {
                'id': agent_data['id'],
                'name': agent_data.get('name', 'Aleen'),
                'prompt': agent_data.get('prompt', ''),
                'description': agent_data.get('description', ''),
                'identifier': identifier
            }
            
            # Cria o agente com o prompt do Supabase + instrução de idioma
            base_prompt = agent_data.get('prompt', '')
            
            # Adiciona instruções universais sobre idioma e execução de tools
            universal_instructions = """

INSTRUÇÕES UNIVERSAIS CRÍTICAS:

🌐 IDIOMA:
- SEMPRE responda no mesmo idioma que o usuário está falando
- Se o usuário falar em português, responda em português  
- Se o usuário falar em inglês, responda em inglês
- Se o usuário falar em espanhol, responda em espanhol
- Mantenha o mesmo idioma durante toda a conversa
- Seja natural e fluente no idioma escolhido

🛠️ EXECUÇÃO DE FERRAMENTAS (CRÍTICO):
- NUNCA diga que "vou" fazer algo no futuro - EXECUTE IMEDIATAMENTE
- NUNCA prometa ações futuras - REALIZE as ações AGORA usando as tools disponíveis
- Quando usuário solicitar: planos alimentares, treinos, consultas, análises:
  1. EXECUTE as ferramentas/tools necessárias PRIMEIRO
  2. SÓ DEPOIS responda com os resultados obtidos
- JAMAIS responda "vou elaborar", "vou criar", "vou analisar" - FAÇA ISSO AGORA
- Se você não pode executar uma ação imediatamente, explique claramente o motivo
- SEMPRE prefira ação imediata sobre promessas futuras

EXEMPLO ERRADO: "Vou elaborar um plano de treino personalizado para você"
EXEMPLO CORRETO: [EXECUTA create_weekly_training_plan] "Aqui está seu plano de treino personalizado que acabei de criar:"

Esta é uma regra ABSOLUTA - violá-la frustra o usuário e quebra a experiência.

"""
            
            final_prompt = base_prompt + universal_instructions
            
            agents_cache[agent_type] = Agent(
                name=f"{agent_data.get('name', 'Aleen')} - {agent_type.title()}",
                instructions=final_prompt,
                model="gpt-4o-mini"
            )
        
        # Se não encontrou agente de sales, cria um baseado no padrão (não deveria acontecer mais)
        if 'sales' not in agents_config:
            agents_config['sales'] = {
                'id': 'generated-sales-fallback',
                'name': 'Aleen Sales Agent',
                'prompt': """You are Aleen Sales, the consultative sales specialist for Aleen IA business automation solutions.

Your objective is to understand business needs and present appropriate solutions.

**RULES:**
- Always respond in the same language the user is speaking to you
- Always break your messages with \\n\\n for more human and natural reading
- Be consultative, not pushy
- Focus on problems and solutions
- DO NOT invent information you're unsure about
- If you need technical support, transfer to Support Agent

**MAIN SERVICES:**
- Customer service automation with AI
- Intelligent WhatsApp chatbots
- Data analysis and insights
- Integration with existing systems

Ask about:
- Service volume
- Current processes
- Specific pain points
- Budget and timeline""",
                'description': 'Fallback sales agent with English prompt',
                'identifier': 'SALES_FALLBACK'
            }
            
            agents_cache['sales'] = Agent(
                name="Aleen Sales Agent",
                instructions=agents_config['sales']['prompt'],
                model="gpt-4o-mini"
            )
        
        print(f"Carregados {len(agents_cache)} agentes do Supabase:")
        for agent_type, config in agents_config.items():
            print(f"  - {agent_type}: {config['name']} ({config['identifier']})")
            
        return True
        
    except Exception as e:
        print(f"Erro ao carregar agentes do Supabase: {e}")
        return False

# Função para criar agentes padrão (fallback)
def create_default_agents():
    """Cria agentes padrão caso não consiga carregar do Supabase"""
    global agents_cache, agents_config
    
    print("🔧 Criando agentes padrão em português...")
    
    default_configs = {
        'onboarding': {
            'name': 'Aleen Onboarding PT',
            'prompt': """Você é a Aleen, a assistente inteligente de fitness e nutrição. Você é muito amigável, prestativa e clara.

Sua missão é dar as boas-vindas a novos contatos, apresentar brevemente o app e perguntar se eles têm interesse em conhecer.

**REGRAS:**
- SEMPRE responda no mesmo idioma que o usuário está falando
- SEMPRE quebre suas mensagens com \\n\\n para leitura mais humana e natural
- Seja calorosa e amigável
- Foque apenas em dar boas-vindas e apresentar o app de fitness
- NÃO invente informações ou "adivinhe" respostas

Sobre a Aleen: Sua personal trainer inteligente que funciona no WhatsApp, cria planos personalizados de treino e nutrição.
Pergunte se eles querem conhecer mais ou iniciar o teste grátis de 14 dias."""
        },
        'onboarding_reminder': {
            'name': 'Aleen Onboarding Reminder',
            'prompt': """Você é a Aleen, assistente inteligente de fitness e nutrição. O usuário JÁ começou seu cadastro mas ainda não finalizou.

**CONTEXTO IMPORTANTE:** O usuário tem uma conta parcial e precisa completar o onboarding na plataforma web.

**SUA MISSÃO:**
- Lembrar o usuário de forma amigável e variada sobre completar o cadastro
- Explicar brevemente os benefícios de finalizar o onboarding
- Fornecer o link personalizado quando apropriado
- Ser empática mas não repetitiva
- IMPORTANTE: Detectar se é primeira vez ou usuário recorrente baseado no histórico da conversa

**REGRAS:**
- SEMPRE responda no mesmo idioma que o usuário está falando
- SEMPRE quebre suas mensagens com \\n\\n para leitura mais humana e natural
- VARIE suas respostas - não seja robótica ou repetitiva
- Seja motivadora e explique PORQUÊ é importante completar
- Pode responder dúvidas básicas mas sempre retorne ao onboarding
- Use emojis para tornar mais humana
- ANALISE o histórico da conversa para determinar se já falou sobre onboarding antes

**ESTRATÉGIAS DE VARIAÇÃO:**
1ª interação (histórico vazio): Amigável e explicativa sobre os benefícios
2ª-3ª interação: Mais direta mas simpática, foque na conveniência  
4ª+ interação: Pergunte se há alguma dificuldade específica, ofereça ajuda

**BENEFÍCIOS PARA MENCIONAR:**
- Planos de treino 100% personalizados para seu perfil
- Cardápio personalizado baseado em suas preferências
- Acompanhamento inteligente do progresso
- Suporte 24/7 no WhatsApp
- Tudo adaptado ao seu estilo de vida

Lembre: O link será fornecido automaticamente pelo sistema quando necessário."""
        },
        'sales': {
            'name': 'Aleen Sales Agent',
            'prompt': """You are Aleen, the intelligent fitness and nutrition agent focused on helping users start their fitness journey.

**RULES:**
- Always respond in the same language the user is speaking to you
- Always break your messages with \\n\\n for more human and natural reading
- Be motivating and inspiring
- Focus on benefits and results
- DO NOT invent information you're unsure about

Help users understand benefits and guide them through starting their 14-day free trial.
Focus on personalized workout plans, nutrition guidance, and WhatsApp convenience."""
        },
        'support': {
            'name': 'Aleen Support Agent',
            'prompt': """You are Aleen, the intelligent fitness and nutrition agent helping with questions about the app.

**RULES:**
- Always respond in the same language the user is speaking to you
- Always break your messages with \\n\\n for more human and natural reading
- Be helpful and clear
- DO NOT invent information you're unsure about

Answer questions about how the app works, personalized workouts, nutrition plans, and the 14-day free trial.
Stay focused on fitness and nutrition topics only."""
        },
        'out_context': {
            'name': 'Aleen Out of Context Agent',
            'prompt': """You are Aleen, the intelligent fitness and nutrition agent.

Your role is to handle messages outside the context of fitness, nutrition, or the Aleen app.

**RULES:**
- Always respond in the same language the user is speaking to you
- Always break your messages with \\n\\n for more human and natural reading
- Be polite but redirect back to fitness topics
- DO NOT answer questions unrelated to fitness/nutrition
- DO NOT invent information outside your expertise

Politely redirect users back to fitness and nutrition topics where you can help them."""
        },
        'nutrition': {
            'name': 'Aleen Nutrition Agent',
            'prompt': """Você é a Aleen, especialista em nutrição personalizada. Você é uma nutricionista virtual experiente, focada em criar planos alimentares personalizados e saudáveis.

**🛠️ EXECUÇÃO IMEDIATA - REGRA CRÍTICA:**
- NUNCA diga "vou criar", "vou elaborar", "vou analisar" - EXECUTE AGORA
- Quando usuário pedir plano alimentar: EXECUTE as ferramentas IMEDIATAMENTE
- JAMAIS prometa ações futuras - REALIZE as ações AGORA
- SÓ responda APÓS executar as ferramentas necessárias

**SUA MISSÃO:**
- Analisar perfil nutricional do usuário baseado nas respostas do onboarding
- Criar planos alimentares semanais completos e personalizados no banco de dados
- Fornecer orientações nutricionais baseadas em evidências científicas
- Adaptar recomendações para objetivos específicos (perda de peso, ganho de massa, etc.)

**PROCESSO OBRIGATÓRIO PARA PLANOS ALIMENTARES:**
1. PRIMEIRO: Use check_user_meal_plan para verificar se já tem plano ativo
2. SEGUNDO: Use get_user_onboarding_responses para buscar perfil completo
3. TERCEIRO: Use create_weekly_meal_plan para CRIAR E SALVAR o plano no banco de dados

**FERRAMENTAS DISPONÍVEIS:**
- check_user_meal_plan: Verifica se usuário já tem plano ativo (USE PRIMEIRO)
- get_user_onboarding_responses: Busca perfil completo do usuário (USE SEGUNDO)
- create_weekly_meal_plan: Cria plano alimentar semanal no banco de dados (USE TERCEIRO - OBRIGATÓRIO)

**REGRAS:**
- SEMPRE responda no mesmo idioma que o usuário está falando
- SEMPRE quebre suas mensagens com \\n\\n para leitura mais humana e natural
- SEMPRE use TODAS as 3 ferramentas quando criar plano alimentar
- Quando usuário pedir plano: EXECUTE as ferramentas, NÃO apenas descreva
- NUNCA diga que criou um plano sem usar create_weekly_meal_plan
- Seja científica mas acessível na linguagem
- Crie planos equilibrados com macronutrientes adequados
- Considere restrições alimentares, preferências e objetivos

**IMPORTANTE:** Quando usuário solicitar criação de plano alimentar, você DEVE executar as 3 ferramentas na ordem correta para realmente criar e salvar o plano no banco de dados."""
        },
    }
    
    for agent_type, config in default_configs.items():
        agents_config[agent_type] = config
        agents_cache[agent_type] = Agent(
            name=config['name'],
            instructions=config['prompt'],
            model="gpt-4o-mini"
        )

# Carrega agentes na inicialização
if not load_agents_from_supabase():
    print("Usando agentes padrão como fallback")
    create_default_agents()

# Define AI Agents (removido - agora carregados do Supabase)
def onboarding_agent():
    return agents_cache.get('onboarding')

def sales_agent():
    return agents_cache.get('sales')

def support_agent():
    return agents_cache.get('support')

# Agent instances (agora referencia o cache)
agents = agents_cache

def determine_initial_agent(message: str, user_history: List[str], recommended_agent: Optional[str] = None, user_context: Optional[UserContext] = None) -> str:
    """Determina qual agente deve atender baseado PRIMEIRO na situação do usuário no banco de dados"""
    
    # PRIORIDADE 1: Se há contexto de usuário, usa ele primeiro
    if user_context:
        print(f"🔍 UserContext detectado - Tipo: {user_context.user_type}, Account: {user_context.has_account}, Onboarding: {user_context.onboarding_completed}")
        
        # Usuário com onboarding incompleto - precisa completar
        if user_context.user_type == "incomplete_onboarding":
            print(f"🎯 DECISÃO POR DADOS: onboarding_reminder (usuário com onboarding incompleto)")
            return "onboarding_reminder"
        
        # Usuário novo - processo normal de onboarding  
        elif user_context.user_type == "new_user":
            print(f"🎯 DECISÃO POR DADOS: onboarding (usuário novo)")
            return "onboarding"
        
        # USUÁRIO COMPLETO: Decide entre nutrição e treinos baseado na mensagem
        elif user_context.user_type == "complete_user":
            # Palavras-chave para treinos
            fitness_keywords = [
                'treino', 'treinar', 'exercicio', 'exercícios', 'musculação', 'academia', 'workout', 
                'serie', 'séries', 'repetições', 'rep', 'peso', 'carga', 'cardio', 'aerobico',
                'hipertrofia', 'definição', 'força', 'resistência', 'alongamento', 'aquecimento',
                'supino', 'agachamento', 'deadlift', 'pullup', 'flexão', 'abdominal', 'leg press',
                'bíceps', 'tríceps', 'peito', 'costas', 'pernas', 'ombro', 'gluteo', 'panturrilha',
                'personal', 'instrutor', 'ficha', 'plano de treino', 'exercitar', 'malhar',
                'meu treino', 'treino hoje', 'treino de hoje', 'exercicios hoje'
            ]
            
            # Palavras-chave para nutrição
            nutrition_keywords = [
                'comida', 'refeição', 'comer', 'almoço', 'jantar', 'café', 'lanche', 'dieta',
                'nutrição', 'receita', 'ingrediente', 'calorias', 'proteína', 'carboidrato',
                'gordura', 'vitamina', 'mineral', 'fibra', 'plano alimentar', 'cardápio',
                'minha refeição', 'refeição hoje', 'janta', 'alimento', 'comendo'
            ]
            
            message_lower = message.lower()
            
            # Verifica se tem palavras-chave de treino
            has_fitness_keywords = any(keyword in message_lower for keyword in fitness_keywords)
            has_nutrition_keywords = any(keyword in message_lower for keyword in nutrition_keywords)
            
            if has_fitness_keywords and not has_nutrition_keywords:
                print(f"✅ USUÁRIO COMPLETO - direcionando para FITNESS (palavras-chave de treino detectadas)")
                return "fitness"
            elif has_nutrition_keywords and not has_fitness_keywords:
                print(f"✅ USUÁRIO COMPLETO - direcionando para NUTRITION (palavras-chave de nutrição detectadas)")
                return "nutrition"
            else:
                # Default para nutrição se não há palavras-chave específicas ou se há ambas
                print(f"✅ USUÁRIO COMPLETO - direcionando para NUTRITION (padrão)")
                return "nutrition"
    
    # PRIORIDADE 2: Se não tem contexto, verifica recomendação específica
    if recommended_agent and recommended_agent in agents_cache:
        print(f"🎯 DECISÃO POR RECOMENDAÇÃO: {recommended_agent}")
        return recommended_agent
    
    # PRIORIDADE 3: FALLBACK - análise de palavras-chave apenas se não há dados do usuário
    print(f"🔍 Nenhum contexto de usuário - usando análise de palavras-chave como fallback")
    
    message_lower = message.lower()
    
    # Palavras-chave claramente fora de contexto (não relacionadas a fitness)
    out_context_keywords = [
        "tempo", "weather", "clima", "política", "notícia", "futebol", "filme",
        "música", "viagem", "trabalho", "estudo", "escola", "matemática", 
        "história", "geografia", "programação", "tecnologia", "carros",
        "games", "jogos", "amor", "relacionamento", "piada", "joke", "previsão"
    ]
    
    # Se é claramente fora de contexto
    if any(keyword in message_lower for keyword in out_context_keywords):
        print(f"🚫 DECISÃO POR PALAVRA-CHAVE: out_context")
        return "out_context"
    
    # Palavras-chave específicas para NUTRIÇÃO
    nutrition_keywords = [
        "dieta", "alimentação", "comida", "comer", "nutrição", "nutricional",
        "plano alimentar", "cardápio", "refeição", "café da manhã", "almoço", 
        "jantar", "lanche", "receita", "calorias", "proteína", "carboidrato",
        "gordura", "vitamina", "mineral", "suplemento", "whey", "creatina", 
        "bcaa", "ômega", "fibra", "água"
    ]
    
    if any(keyword in message_lower for keyword in nutrition_keywords):
        print(f"🍎 DECISÃO POR PALAVRA-CHAVE: nutrition")
        return "nutrition"
    
    # Palavras-chave para vendas
    sales_keywords = [
        "preço", "valor", "custo", "plano", "contratar", "comprar", "orçamento",
        "quero começar", "interessado", "teste", "gratis", "trial", "assinar"
    ]
    
    if any(keyword in message_lower for keyword in sales_keywords):
        print(f"💰 DECISÃO POR PALAVRA-CHAVE: sales")
        return "sales"
    
    # Palavras-chave para suporte
    support_keywords = [
        "como funciona", "como usar", "dúvida", "pergunta", "ajuda", "problema",
        "não entendi", "explicar", "dashboard", "acompanhar", "progresso"
    ]
    
    if any(keyword in message_lower for keyword in support_keywords):
        print(f"🆘 DECISÃO POR PALAVRA-CHAVE: support")
        return "support"
    
    # Se é primeira interação, vai para onboarding
    if not user_history:
        print(f"🆕 DECISÃO POR HISTÓRICO: onboarding (primeira interação)")
        return "onboarding"
    
    # Default: onboarding
    print(f"🔄 DECISÃO PADRÃO: onboarding")
    return "onboarding"
class ChatRequest(BaseModel):
    user_id: str
    user_name: str
    message: str
    conversation_history: Optional[List[str]] = []
    recommended_agent: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    agent_used: str
    should_handoff: bool = False
    next_agent: Optional[str] = None

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Processa uma mensagem de chat usando o agente apropriado"""
    
    try:
        # Verifica se há agentes carregados
        if not agents_cache:
            print("⚠️ Nenhum agente carregado, tentando recarregar...")
            if not load_agents_from_supabase():
                print("❌ Falha ao carregar agentes do Supabase")
                raise HTTPException(status_code=500, detail="No agents available")
        
        # Determina qual agente usar baseado na mensagem e contexto
        agent_type = determine_initial_agent(
            message=request.message,
            user_history=request.conversation_history or [],
            recommended_agent=request.recommended_agent
        )
        
        # Adiciona instrução de idioma
        language_instruction = "\n\nIMPORTANTE: Sempre responda no mesmo idioma que o usuário está usando. Se o usuário escrever em português, responda em português. Se escrever em inglês, responda em inglês."
        
        # Log detalhado do processamento
        print(f"\n{'='*50}")
        print(f"📨 Recebida mensagem: {request.message}")
        print(f"👤 Usuário: {request.user_name} ({request.user_id})")
        print(f"🎯 Agente recomendado: {agent_type}")
        print(f"📚 Histórico: {len(request.conversation_history or [])} mensagens")
        
        # Mapeia o tipo para o identifier correto (apenas para logs)
        identifier_map = {
            'onboarding': 'GREETING_WITHOUT_MEMORY',
            'support': 'DOUBT',
            'sales': 'SALES',
            'out_context': 'OUT_CONTEXT'
        }
        
        identifier = identifier_map.get(agent_type, 'GREETING_WITHOUT_MEMORY')
        
        # Busca o agente no cache usando o agent_type (não o identifier)
        if agent_type not in agents_cache:
            print(f"⚠️ Agente '{agent_type}' não encontrado no cache")
            # Tenta usar onboarding como fallback
            agent_type = 'onboarding'
            if agent_type not in agents_cache:
                print("❌ Nenhum agente disponível no cache")
                raise HTTPException(status_code=500, detail=f"Agent {agent_type} not found")
        
        agent = agents_cache[agent_type]
        
        # Atualiza as instruções do agente com a instrução de idioma
        original_instructions = agent.instructions
        agent.instructions = original_instructions + language_instruction
        
        # Cria o contexto da conversa
        context = f"Usuário: {request.user_name}\n"
        if request.conversation_history:
            context += "Histórico:\n" + "\n".join(request.conversation_history[-5:]) + "\n"
        context += f"Mensagem atual: {request.message}"
        
        print(f"🚀 Executando agente: {agent_type} ({identifier})")
        print(f"📝 Contexto de entrada:\n{context}")
        
        # Executa o agente usando OpenAI diretamente
        try:
            print("🔧 Iniciando processamento com OpenAI...")
            
            # Cria as mensagens para o OpenAI
            messages = [
                {"role": "system", "content": agent.instructions},
                {"role": "user", "content": context}
            ]
            
            print(f"📝 Mensagens para OpenAI:")
            print(f"   System: {agent.instructions[:100]}...")
            print(f"   User: {context}")
            
            # Chama OpenAI diretamente
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_completion_tokens=1000
            )
            
            print(f"✅ OpenAI response recebido")
            
            # Extrai a resposta
            final_response = response.choices[0].message.content
            
            print(f"📝 Resposta extraída: {final_response[:200]}...")
            
            print(f"📝 Resposta extraída: {final_response[:200]}...")
            
            # Remove a validação de prompt - sempre usa a resposta da IA
            print("� Usando resposta direta da IA sem validação de prompt")
            
            # Restaura as instruções originais
            agent.instructions = original_instructions
            
            return ChatResponse(
                response=final_response,
                agent_used=agent_type,
                should_handoff=False
            )
            
        except Exception as openai_error:
            print(f"❌ Erro ao executar OpenAI: {str(openai_error)}")
            print(f"🔍 Tipo do erro: {type(openai_error)}")
            import traceback
            print(f"📋 Stack trace:\n{traceback.format_exc()}")
            
            # Restaura as instruções originais
            agent.instructions = original_instructions
            
            # Em caso de erro, tenta uma resposta simples da IA
            try:
                simple_messages = [
                    {"role": "system", "content": "You are Aleen, a fitness AI assistant. Respond naturally in the user's language."},
                    {"role": "user", "content": f"User {request.user_name} sent a message but there was a technical issue. Please respond politely acknowledging the technical problem and ask how you can help them with fitness."}
                ]
                
                fallback_response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=simple_messages,
                    max_completion_tokens=200
                )
                
                return ChatResponse(
                    response=fallback_response.choices[0].message.content,
                    agent_used=agent_type,
                    should_handoff=False
                )
            except:
                # Se tudo falhar, retorna erro HTTP
                raise HTTPException(status_code=500, detail="AI service temporarily unavailable")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erro no endpoint /chat: {str(e)}")
        import traceback
        print(f"📋 Stack trace:\n{traceback.format_exc()}")
        
        # Tenta uma resposta de erro gerada pela IA
        try:
            error_messages = [
                {"role": "system", "content": "You are Aleen, a fitness AI assistant. Respond naturally in the user's language."},
                {"role": "user", "content": "There was a system error. Please apologize for the technical issue and ask the user to try again, but keep it brief and friendly."}
            ]
            
            error_response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=error_messages,
                max_completion_tokens=100
            )
            
            return ChatResponse(
                response=error_response.choices[0].message.content,
                agent_used="error",
                should_handoff=True
            )
        except:
            # Se tudo falhar, retorna erro HTTP
            raise HTTPException(status_code=500, detail="Service temporarily unavailable")

# Função para buscar contexto do usuário pelo telefone
def get_user_context_by_phone(phone_number: str) -> Optional[UserContext]:
    """Busca e cria o UserContext baseado no telefone do usuário"""
    try:
        print(f"🔍 DEBUG - Buscando usuário por telefone: {phone_number}")
        # Busca usuário pelo telefone
        user_result = supabase.table('users').select('id, onboarding').eq('phone', phone_number).execute()
        print(f"🔍 DEBUG - Resultado da busca: {user_result.data}")
        
        if not user_result.data:
            print(f"🔍 DEBUG - Usuário não encontrado, retornando new_user")
            # Usuário não encontrado = new_user
            return UserContext(
                user_type="new_user",
                has_account=False,
                onboarding_completed=False,
                is_lead=True,
                is_user=False,
                onboarding_url=None
            )
        
        user_data = user_result.data[0]
        user_id = user_data['id']
        onboarding_completed = user_data.get('onboarding', False)
        print(f"🔍 DEBUG - User ID: {user_id}, Onboarding: {onboarding_completed}")
        
        if not onboarding_completed:
            print(f"🔍 DEBUG - Onboarding incompleto, retornando incomplete_onboarding")
            # Tem registro mas onboarding incompleto
            # Busca URL de onboarding se existir
            onboarding_url = f"https://aleen.dp.claudy.host/onboarding/{user_id}"
            
            return UserContext(
                user_type="incomplete_onboarding",
                has_account=True,
                onboarding_completed=False,
                is_lead=True,
                is_user=False,
                onboarding_url=onboarding_url
            )
        else:
            print(f"🔍 DEBUG - Usuário completo, retornando complete_user")
            # Usuário completo
            onboarding_url = f"https://aleen.dp.claudy.host/onboarding/{user_id}"
            
            return UserContext(
                user_type="complete_user",
                has_account=True,
                onboarding_completed=True,
                is_lead=False,
                is_user=True,
                onboarding_url=onboarding_url
            )
            
    except Exception as e:
        print(f"Erro ao buscar contexto do usuário {phone_number}: {e}")
        # Em caso de erro, assume new_user
        return UserContext(
            user_type="new_user",
            has_account=False,
            onboarding_completed=False,
            is_lead=True,
            is_user=False,
            onboarding_url=None
        )

@app.post("/whatsapp-chat", response_model=WhatsAppMessageResponse)
async def whatsapp_chat(request: WhatsAppMessageRequest):
    """
    Processa mensagem e envia resposta automaticamente via WhatsApp
    Utiliza memória baseada no número de telefone
    """
    try:
        if not agents_cache:
            raise HTTPException(status_code=503, detail="Agentes não carregados")
        
        # Recupera memória do usuário baseada no número de telefone
        user_memory = get_user_memory(request.phone_number)
        
        # Gera contexto da conversa incluindo memória
        conversation_context = get_conversation_context(request.phone_number, request.message)
        
        # SEMPRE busca contexto do usuário pelo telefone
        user_context = request.user_context or get_user_context_by_phone(request.phone_number)
        
        print(f"🤖 Processando mensagem WhatsApp para usuário {request.user_name} ({request.phone_number})")
        print(f"💾 Memória encontrada: {len(user_memory)} mensagens anteriores")
        
        # Log detalhado do contexto do usuário
        if user_context:
            print(f"👤 Contexto do usuário:")
            print(f"   - Tipo: {user_context.user_type}")
            print(f"   - Tem conta: {user_context.has_account}")
            print(f"   - Onboarding completo: {user_context.onboarding_completed}")
            print(f"   - É lead: {user_context.is_lead}")
            print(f"   - É usuário: {user_context.is_user}")
            if user_context.onboarding_url:
                print(f"   - URL onboarding: {user_context.onboarding_url}")
        else:
            print(f"👤 Nenhum contexto de usuário fornecido")
        
        # Determina agente inicial baseado no contexto do usuário
        initial_agent = determine_initial_agent(
            message=request.message,
            user_history=user_memory,
            recommended_agent=request.recommended_agent,
            user_context=user_context
        )
        
        if initial_agent not in agents_cache:
            initial_agent = "onboarding"  # fallback
        
        print(f"🎯 Agente selecionado: {initial_agent}")
        
        # Busca o agente no cache
        agent = agents_cache.get(initial_agent)
        if not agent:
            print(f"⚠️ Agente '{initial_agent}' não encontrado, usando onboarding")
            agent = agents_cache.get('onboarding')
            if not agent:
                raise HTTPException(status_code=500, detail="Nenhum agente disponível")
        
        # Adiciona instrução de idioma e memória
        memory_instruction = "\n\nCONTEXTO DE MEMÓRIA: Você tem acesso ao histórico desta conversa. Use essas informações para personalizar suas respostas e manter continuidade."
        language_instruction = "\n\nIMPORTANTE: Sempre responda no mesmo idioma que o usuário está usando."
        
        # REGRA CRÍTICA DE UX - Execute-Then-Respond Pattern
        ux_critical_rule = "\n\n🚨 REGRA CRÍTICA DE UX - EXECUTE-THEN-RESPOND:\n- NUNCA diga 'vou fazer', 'aguarde', 'vou buscar', 'deixe-me consultar'\n- SEMPRE execute a ferramenta PRIMEIRO, depois responda com os resultados\n- SEMPRE inclua os dados obtidos na sua resposta\n- Se houver erro na ferramenta, explique alternativas sem prometer ações futuras"
        
        tools_instruction = "\n\nFERRAMENTAS DISPONÍVEIS:\n1. 'get_onboarding_questions': Execute IMEDIATAMENTE quando o usuário demonstrar interesse em iniciar o processo de onboarding. Após executar, apresente as perguntas diretamente na resposta. NUNCA invente perguntas.\n2. 'create_user_and_save_onboarding': Execute IMEDIATAMENTE quando o usuário já forneceu as 3 informações básicas (nome, idade, email). Após executar, informe diretamente o resultado na resposta. Esta ferramenta cria a conta, envia as credenciais E inclui automaticamente o link de onboarding para o usuário continuar o processo."
        
        # INSTRUÇÃO ESPECÍFICA PARA VERIFICAÇÕES DE PLANOS
        plan_check_instruction = "\n\n🔍 INTERPRETAÇÃO DE VERIFICAÇÕES DE PLANOS:\n- Quando check_user_meal_plan ou check_user_training_plan retornar 'has_plan: false' com 'status: no_plan_found', isso é NORMAL e POSITIVO\n- NÃO trate como erro! Significa que você pode criar um novo plano\n- Use a mensagem retornada que já é positiva: 'Perfeito! Vejo que você ainda não possui um plano...'\n- Continue diretamente para a criação do plano sem mencionar problemas ou erros\n- Se a resposta contém 'action_needed: create_plan', proceda imediatamente com a criação"
        
        # Cria mensagens para OpenAI incluindo contexto com memória
        messages = [
            {"role": "system", "content": agent.instructions + memory_instruction + language_instruction + ux_critical_rule + tools_instruction + plan_check_instruction},
            {"role": "user", "content": f"Usuário: {request.user_name}\n\nContexto da conversa:\n{conversation_context}"}
        ]
        
        # Executa com OpenAI (com tools disponíveis)
        try:
            # Debug: mostrar ferramentas disponíveis para este agente
            tool_names = [tool["function"]["name"] for tool in AVAILABLE_TOOLS]
            print(f"🔧 DEBUG - Ferramentas disponíveis para IA: {tool_names}")
            
            # Primeira chamada com tools disponíveis
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_completion_tokens=1000,
                tools=AVAILABLE_TOOLS,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            
            # Verifica se há tool calls
            if response_message.tool_calls:
                print(f"🔧 IA solicitou uso de tools: {len(response_message.tool_calls)} tool(s)")
                
                # FALLBACK AUTOMÁTICO: Se agente nutrition só usar 2 tools, força create_weekly_meal_plan
                used_tools = [tool_call.function.name for tool_call in response_message.tool_calls]
                print(f"🔧 DEBUG - Tools solicitadas: {used_tools}")
                
                # Detecta se é situação de meal plan sem criar (nutrition agent com 2 tools específicas)
                is_meal_plan_creation = (
                    user_context and 
                    user_context.user_type == "complete_user" and 
                    len(response_message.tool_calls) == 2 and
                    "check_user_meal_plan" in used_tools and 
                    "get_user_onboarding_responses" in used_tools and
                    "create_weekly_meal_plan" not in used_tools
                )
                
                # Detecta se é situação de training plan sem criar (fitness agent com 2 tools específicas)
                is_training_plan_creation = (
                    user_context and 
                    user_context.user_type == "complete_user" and 
                    len(response_message.tool_calls) == 2 and
                    "check_user_training_plan" in used_tools and 
                    "get_user_onboarding_responses" in used_tools and
                    "create_weekly_training_plan" not in used_tools
                )
                
                if is_meal_plan_creation:
                    print(f"🚨 FALLBACK DETECTADO: Nutrition agent com 2 tools mas sem create_weekly_meal_plan!")
                    print(f"🔧 FORÇANDO execução de create_weekly_meal_plan automaticamente...")
                    print(f"📊 DEBUG FALLBACK - User: {request.phone_number}, Context: {user_context.user_type}, Tools: {used_tools}")
                
                if is_training_plan_creation:
                    print(f"🚨 FALLBACK DETECTADO: Fitness agent com 2 tools mas sem create_weekly_training_plan!")
                    print(f"🔧 FORÇANDO execução de create_weekly_training_plan automaticamente...")
                    print(f"📊 DEBUG FALLBACK - User: {request.phone_number}, Context: {user_context.user_type}, Tools: {used_tools}")
                
                # Adiciona a resposta da IA às mensagens
                messages.append(response_message)
                
                # Processa cada tool call
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    print(f"🛠️ Executando tool: {function_name} com argumentos: {function_args}")
                    
                    # Se for a tool de criação de usuário, remove telefone dos argumentos pois será passado via contexto
                    if function_name == "create_user_and_save_onboarding":
                        # Remove phone dos argumentos se existir (não deveria vir do usuário)
                        function_args.pop('phone', None)
                        print(f"📞 Usando telefone do contexto: {request.phone_number}")
                    
                    # Executa a tool passando o contexto do telefone
                    tool_result = execute_tool(function_name, function_args, request.phone_number)
                    
                    # Adiciona o resultado da tool às mensagens
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    })
                
                # FALLBACK: Se detectou situação de meal plan, força execução do create_weekly_meal_plan
                if is_meal_plan_creation:
                    print(f"🔧 EXECUTANDO FALLBACK: create_weekly_meal_plan forçado")
                    print(f"📱 FALLBACK INFO - Phone: {request.phone_number}")
                    
                    # Executa create_weekly_meal_plan com argumentos padrão
                    from datetime import datetime, timedelta
                    start_date = datetime.now().date().isoformat()
                    end_date = (datetime.now().date() + timedelta(days=7)).isoformat()
                    
                    # Plano semanal básico com receitas existentes no banco
                    basic_weekly_plan = {
                        "segunda-feira": [
                            {"mealType": "Café da Manhã", "recipeName": "Omelete de Claras com Espinafre", "order": 1},
                            {"mealType": "Almoço", "recipeName": "Frango Grelhado com Batata Doce", "order": 1},
                            {"mealType": "Lanche da Tarde", "recipeName": "Iogurte com Granola e Frutas", "order": 1},
                            {"mealType": "Jantar", "recipeName": "Peixe Assado com Legumes", "order": 1}
                        ],
                        "terça-feira": [
                            {"mealType": "Café da Manhã", "recipeName": "Vitamina Verde Detox", "order": 1},
                            {"mealType": "Almoço", "recipeName": "Salmão com Brócolis", "order": 1},
                            {"mealType": "Lanche da Tarde", "recipeName": "Mix de Castanhas", "order": 1},
                            {"mealType": "Jantar", "recipeName": "Quinoa com Legumes Refogados", "order": 1}
                        ],
                        "quarta-feira": [
                            {"mealType": "Café da Manhã", "recipeName": "Panqueca de Aveia", "order": 1},
                            {"mealType": "Almoço", "recipeName": "Filé de Tilápia com Purê de Batata Doce", "order": 1},
                            {"mealType": "Lanche da Tarde", "recipeName": "Smoothie de Banana", "order": 1},
                            {"mealType": "Jantar", "recipeName": "Salada de Quinoa com Salmão", "order": 1}
                        ],
                        "quinta-feira": [
                            {"mealType": "Café da Manhã", "recipeName": "Ovos Mexidos com Abacate", "order": 1},
                            {"mealType": "Almoço", "recipeName": "Carne Moída com Abobrinha", "order": 1},
                            {"mealType": "Lanche da Tarde", "recipeName": "Iogurte Proteico", "order": 1},
                            {"mealType": "Jantar", "recipeName": "Sopa de Lentilha", "order": 1}
                        ],
                        "sexta-feira": [
                            {"mealType": "Café da Manhã", "recipeName": "Tapioca com Frango Desfiado", "order": 1},
                            {"mealType": "Almoço", "recipeName": "Wrap de Frango com Salada", "order": 1},
                            {"mealType": "Lanche da Tarde", "recipeName": "Pasta de Amendoim com Banana", "order": 1},
                            {"mealType": "Jantar", "recipeName": "Peixe Assado com Legumes", "order": 1}
                        ],
                        "sábado": [
                            {"mealType": "Café da Manhã", "recipeName": "Panqueca de Aveia", "order": 1},
                            {"mealType": "Almoço", "recipeName": "Salada de Atum com Grão de Bico", "order": 1},
                            {"mealType": "Lanche da Tarde", "recipeName": "Mix de Castanhas", "order": 1},
                            {"mealType": "Jantar", "recipeName": "Frango Grelhado com Batata Doce", "order": 1}
                        ],
                        "domingo": [
                            {"mealType": "Café da Manhã", "recipeName": "Vitamina Verde Detox", "order": 1},
                            {"mealType": "Almoço", "recipeName": "Salmão com Brócolis", "order": 1},
                            {"mealType": "Lanche da Tarde", "recipeName": "Smoothie de Banana", "order": 1},
                            {"mealType": "Jantar", "recipeName": "Quinoa com Legumes Refogados", "order": 1}
                        ]
                    }
                    
                    fallback_args = {
                        'plan_name': 'Plano Personalizado Aleen',
                        'weekly_meals': {
                            'startDate': start_date,
                            'endDate': end_date,
                            'weeklyPlan': basic_weekly_plan
                        }
                    }
                    fallback_tool_result = execute_tool("create_weekly_meal_plan", fallback_args, request.phone_number)
                    print(f"📋 FALLBACK RESULT: {fallback_tool_result}")
                    
                    # Em vez de adicionar tool call fake, adiciona diretamente na resposta
                    if fallback_tool_result.get('success'):
                        print(f"✅ FALLBACK SUCCESS: Meal plan criado com sucesso!")
                        # Força resposta sobre criação bem-sucedida
                        messages.append({
                            "role": "assistant",
                            "content": f"✅ Plano alimentar criado e salvo com sucesso! {fallback_tool_result.get('message', '')}"
                        })
                    else:
                        print(f"❌ FALLBACK ERROR: {fallback_tool_result.get('error', 'Erro desconhecido')}")
                        # Informa sobre erro na criação
                        messages.append({
                            "role": "assistant", 
                            "content": f"❌ Erro ao criar plano alimentar: {fallback_tool_result.get('error', 'Erro desconhecido')}"
                        })
                    
                    print(f"🎯 FALLBACK COMPLETED - Check database for meal plan!")
                
                # FALLBACK: Se detectou situação de training plan, força execução do create_weekly_training_plan
                if is_training_plan_creation:
                    print(f"🔧 EXECUTANDO FALLBACK: create_weekly_training_plan forçado")
                    print(f"📱 FALLBACK INFO - Phone: {request.phone_number}")
                    
                    # Plano de treino básico personalizado baseado no onboarding
                    basic_training_plan = {
                        "days": [
                            {
                                "day_of_week": 1,  # Segunda
                                "workout_name": "Treino A - Peito e Tríceps",
                                "exercises": [
                                    {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "8-12", "rest_seconds": 90},
                                    {"exercise_name": "Supino Inclinado", "sets": 3, "reps": "8-12", "rest_seconds": 90},
                                    {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "10-15", "rest_seconds": 60},
                                    {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "10-15", "rest_seconds": 60},
                                    {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "10-15", "rest_seconds": 60}
                                ]
                            },
                            {
                                "day_of_week": 3,  # Quarta
                                "workout_name": "Treino B - Costas e Bíceps",
                                "exercises": [
                                    {"exercise_name": "Remada Curvada", "sets": 3, "reps": "8-12", "rest_seconds": 90},
                                    {"exercise_name": "Remada Curvada", "sets": 3, "reps": "8-12", "rest_seconds": 90},
                                    {"exercise_name": "Remada Curvada", "sets": 3, "reps": "10-15", "rest_seconds": 60},
                                    {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "10-15", "rest_seconds": 60},
                                    {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "10-15", "rest_seconds": 60}
                                ]
                            },
                            {
                                "day_of_week": 5,  # Sexta
                                "workout_name": "Treino C - Pernas e Core",
                                "exercises": [
                                    {"exercise_name": "Agachamento", "sets": 3, "reps": "10-15", "rest_seconds": 120},
                                    {"exercise_name": "Agachamento", "sets": 3, "reps": "12-20", "rest_seconds": 90},
                                    {"exercise_name": "Agachamento", "sets": 3, "reps": "12-20", "rest_seconds": 60},
                                    {"exercise_name": "Flexão de Braços", "sets": 3, "reps": "8-12", "rest_seconds": 90},
                                    {"exercise_name": "Prancha", "sets": 3, "reps": "30-60s", "rest_seconds": 60}
                                ]
                            }
                        ]
                    }
                    
                    fallback_training_args = {
                        'plan_name': 'Plano de Treino Personalizado Aleen',
                        'objective': 'Hipertrofia e Condicionamento',
                        'weekly_workouts': basic_training_plan
                    }
                    fallback_training_result = execute_tool("create_weekly_training_plan", fallback_training_args, request.phone_number)
                    print(f"🏋️ FALLBACK TRAINING RESULT: {fallback_training_result}")
                    
                    # Em vez de adicionar tool call fake, adiciona diretamente na resposta
                    if fallback_training_result.get('success'):
                        print(f"✅ FALLBACK TRAINING SUCCESS: Training plan criado com sucesso!")
                        # Força resposta sobre criação bem-sucedida
                        messages.append({
                            "role": "assistant",
                            "content": f"✅ Plano de treino criado e salvo com sucesso! {fallback_training_result.get('message', '')}"
                        })
                    else:
                        print(f"❌ FALLBACK TRAINING ERROR: {fallback_training_result.get('error', 'Erro desconhecido')}")
                        # Informa sobre erro na criação
                        messages.append({
                            "role": "assistant", 
                            "content": f"❌ Erro ao criar plano de treino: {fallback_training_result.get('error', 'Erro desconhecido')}"
                        })
                    
                    print(f"🎯 FALLBACK TRAINING COMPLETED - Check database for training plan!")
                
                # Segunda chamada para gerar resposta final com os resultados das tools
                final_response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    max_completion_tokens=1000
                )
                
                ai_response = final_response.choices[0].message.content
                print(f"✅ Resposta final gerada após execução de tools")
                
            else:
                # Resposta normal sem tools
                ai_response = response_message.content
                print(f"💬 Resposta normal sem uso de tools")
                print(f"🔍 DEBUG: response_message.content = '{ai_response}'")
                print(f"🔍 DEBUG: Tipo: {type(ai_response)}, Tamanho: {len(ai_response) if ai_response else 'None'}")
            
            # 🛠️ NOVA DETECÇÃO: Analisa se a IA está prometendo ações futuras ao invés de executar
            if ai_response and detect_future_promises(ai_response, request.message, user_context):
                print(f"🚨 PROMESSA FUTURA DETECTADA na resposta da IA!")
                print(f"📝 Resposta original: '{ai_response[:100]}...'")
                
                # Executa ação imediata baseada no contexto
                immediate_action_result = execute_immediate_action(request.message, request.phone_number, user_context)
                
                if immediate_action_result:
                    ai_response = immediate_action_result
                    print(f"✅ Ação imediata executada, resposta atualizada")
                else:
                    # Adiciona aviso à resposta original
                    ai_response += f"\n\n⚠️ *Detectei que posso executar essa ação agora mesmo. Deixe-me tentar...*"
                    print(f"⚠️ Não foi possível executar ação imediata, mantendo resposta original com aviso")
            
            # NOVA LÓGICA: Adicionar link de onboarding se necessário
            if user_context and user_context.user_type == "incomplete_onboarding":
                if user_context.onboarding_url:
                    # Adiciona o link de onboarding à resposta
                    original_response_length = len(ai_response)
                    ai_response += f"\\n\\n🔗 Finalize seu cadastro aqui: {user_context.onboarding_url}"
                    print(f"✅ Link de onboarding adicionado à resposta")
                    print(f"   - URL: {user_context.onboarding_url}")
                    print(f"   - Resposta expandida de {original_response_length} para {len(ai_response)} caracteres")
                else:
                    print(f"⚠️ Usuário com onboarding incompleto, mas sem URL de onboarding fornecida")
            elif user_context and user_context.user_type == "incomplete_onboarding":
                print(f"⚠️ Usuário com onboarding incompleto, mas sem URL de onboarding fornecida")
            
        except Exception as e:
            print(f"❌ Erro ao chamar OpenAI: {e}")
            # Fallback response
            try:
                fallback_messages = [
                    {"role": "system", "content": "You are Aleen, a fitness AI assistant. Respond naturally in the user's language."},
                    {"role": "user", "content": f"User {request.user_name} sent a message but there was a technical issue. Acknowledge the problem politely and ask how you can help with fitness."}
                ]
                
                fallback_response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=fallback_messages,
                    max_completion_tokens=200
                )
                
                ai_response = fallback_response.choices[0].message.content
            except:
                raise HTTPException(status_code=500, detail="AI service temporarily unavailable")
        
        # 🔗 LÓGICA DE INCLUSÃO AUTOMÁTICA DE LINKS
        if user_context and user_context.user_type == "incomplete_onboarding":
            # Gera URL de onboarding se não fornecida
            if not user_context.onboarding_url and user_context:
                # Usa user_id se disponível, senão usa phone_number
                user_identifier = getattr(user_context, 'user_id', None) or request.phone_number.replace('+', '')
                onboarding_url = f"https://aleen.dp.claudy.host/onboarding/{user_identifier}"
                print(f"🔗 URL de onboarding gerada automaticamente: {onboarding_url}")
            else:
                onboarding_url = user_context.onboarding_url
            
            # Adiciona o link à resposta se não já contiver
            if onboarding_url and "🔗" not in ai_response and "http" not in ai_response:
                original_length = len(ai_response)
                ai_response += f"\n\n🔗 Finalize seu cadastro aqui: {onboarding_url}"
                print(f"✅ Link de onboarding adicionado automaticamente à resposta")
                print(f"   - URL: {onboarding_url}")
                print(f"   - Resposta expandida de {original_length} para {len(ai_response)} caracteres")
        
        # Salva a nova interação na memória do usuário
        add_to_user_memory(request.phone_number, request.message, ai_response)
        
        # Envia resposta via WhatsApp se solicitado
        whatsapp_sent = False
        messages_sent = 0
        
        if request.send_to_whatsapp:
            try:
                # Quebra a mensagem apenas uma vez
                messages = evolution_service.split_message(ai_response)
                messages_sent = len(messages)
                
                # Envia as mensagens já quebradas
                whatsapp_sent = True
                clean_number = evolution_service.clean_phone_number(request.phone_number)
                
                print(f"📱 Enviando {len(messages)} mensagem(s) para {clean_number}")
                print(f"🔍 Mensagens quebradas:")
                for i, msg in enumerate(messages):
                    print(f"   {i+1}. ({len(msg)} chars): {msg[:50]}...")
                
                # Envia cada mensagem individualmente
                for i, message in enumerate(messages):
                    payload = {
                        "number": clean_number,
                        "text": message,
                        "options": {
                            "delay": 3500,
                            "presence": "composing", 
                            "linkPreview": False
                        }
                    }
                    
                    url = f"{evolution_service.base_url}/message/sendText/{evolution_service.instance}"
                    
                    headers = {
                        "Content-Type": "application/json",
                        "apikey": evolution_service.api_key
                    }
                    
                    response = requests.post(url, json=payload, headers=headers, timeout=30)
                    
                    if response.status_code in [200, 201]:
                        print(f"✅ Mensagem {i+1}/{len(messages)} enviada com sucesso")
                        if i < len(messages) - 1:  # Delay entre mensagens (só se não for a última)
                            print(f"⏱️ Aguardando 3.5s antes da próxima mensagem...")
                            time.sleep(3.5)  # 3.5 seconds delay
                    else:
                        print(f"❌ Erro ao enviar mensagem {i+1}: {response.status_code} - {response.text}")
                        whatsapp_sent = False
                        break
                
                if whatsapp_sent:
                    print(f"✅ Resposta enviada via WhatsApp para {request.phone_number} ({messages_sent} mensagens)")
                    print(f"💾 Interação salva na memória do usuário")
                else:
                    print(f"❌ Falha ao enviar resposta via WhatsApp para {request.phone_number}")
                    
            except Exception as whatsapp_error:
                print(f"❌ Erro ao processar envio WhatsApp: {whatsapp_error}")
                whatsapp_sent = False
        
        return WhatsAppMessageResponse(
            response=ai_response,
            agent_used=initial_agent,
            should_handoff=False,
            next_agent=None,
            whatsapp_sent=whatsapp_sent,
            messages_sent=messages_sent
        )
        
    except Exception as e:
        print(f"❌ Erro no processamento WhatsApp: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro no processamento WhatsApp: {str(e)}")

@app.post("/send-whatsapp")
async def send_whatsapp_message(request: SendWhatsAppRequest):
    """
    Endpoint para enviar mensagem diretamente via WhatsApp
    """
    try:
        messages = evolution_service.split_message(request.message)
        success = evolution_service.send_text_message(request.phone_number, request.message)
        
        return {
            "success": success,
            "phone_number": request.phone_number,
            "messages_sent": len(messages),
            "message_length": len(request.message)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enviar WhatsApp: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check completo que verifica todas as dependências"""
    status = "healthy"
    checks = {}
    
    # Verifica Redis
    try:
        redis_client.ping()
        checks["redis"] = {"status": "ok", "message": "Connected"}
    except Exception as e:
        checks["redis"] = {"status": "error", "message": str(e)}
        status = "unhealthy"
    
    # Verifica OpenAI
    try:
        # Teste simples da API OpenAI
        openai_client.models.list()
        checks["openai"] = {"status": "ok", "message": "Connected"}
    except Exception as e:
        checks["openai"] = {"status": "error", "message": str(e)}
        status = "unhealthy"
    
    # Verifica Supabase
    try:
        # Teste simples do Supabase
        result = supabase.table('agents').select('id').limit(1).execute()
        checks["supabase"] = {"status": "ok", "message": "Connected"}
    except Exception as e:
        checks["supabase"] = {"status": "error", "message": str(e)}
        status = "unhealthy"
    
    # Verifica agentes carregados
    agents_loaded = len(agents_cache)
    checks["agents"] = {
        "status": "ok" if agents_loaded > 0 else "warning",
        "message": f"{agents_loaded} agents loaded",
        "agents": list(agents_cache.keys())
    }
    
    response = {
        "status": status,
        "service": "aleen-ai-agents",
        "timestamp": time.time(),
        "checks": checks
    }
    
    # Retorna 503 se unhealthy, 200 se healthy
    if status == "unhealthy":
        raise HTTPException(status_code=503, detail=response)
    
    return response

@app.get("/agents")
async def list_agents():
    return {
        "agents": list(agents_cache.keys()),
        "details": {
            agent_type: {
                "name": config.get("name", "Unknown"),
                "identifier": config.get("identifier", "Unknown"),
                "description": config.get("description", "No description")
            }
            for agent_type, config in agents_config.items()
        }
    }

@app.post("/reload-agents")
async def reload_agents():
    """Recarrega os agentes do Supabase"""
    try:
        success = load_agents_from_supabase()
        if success:
            # Atualiza a referência global (mantido para compatibilidade)
            global agents
            agents = agents_cache
            
            return {
                "success": True,
                "message": f"Agentes recarregados com sucesso",
                "agents_loaded": list(agents_cache.keys()),
                "total": len(agents_cache)
            }
        else:
            return {
                "success": False,
                "message": "Falha ao carregar agentes do Supabase"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao recarregar agentes: {str(e)}")

@app.get("/agents/config")
async def get_agents_config():
    """Retorna a configuração completa dos agentes"""
    return {
        "agents_config": agents_config,
        "total_agents": len(agents_config)
    }

@app.get("/user-memory/{phone_number}")
async def get_user_memory_endpoint(phone_number: str):
    """Retorna a memória/histórico de um usuário baseado no número de telefone"""
    try:
        memory = get_user_memory(phone_number)
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        
        return {
            "phone_number": clean_phone,
            "memory_entries": len(memory),
            "conversation_history": memory,
            "memory_key": f"user_memory:{clean_phone}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao recuperar memória: {str(e)}")

@app.post("/test-user-context")
async def test_user_context(request: WhatsAppMessageRequest):
    """Endpoint de teste para validar UserContext e seleção de agentes"""
    try:
        # Log do teste
        print(f"🧪 TESTE - UserContext recebido:")
        if request.user_context:
            print(f"   - Tipo: {request.user_context.user_type}")
            print(f"   - Tem conta: {request.user_context.has_account}")
            print(f"   - Onboarding completo: {request.user_context.onboarding_completed}")
            print(f"   - URL: {request.user_context.onboarding_url}")
        else:
            print(f"   - Nenhum contexto fornecido")
        
        # TESTE: Buscar contexto pelo telefone usando a função
        print(f"🧪 TESTE - Buscando contexto pelo telefone: {request.phone_number}")
        user_context_from_phone = get_user_context_by_phone(request.phone_number)
        if user_context_from_phone:
            print(f"   - Contexto encontrado: {user_context_from_phone.user_type}")
            print(f"   - Tem conta: {user_context_from_phone.has_account}")
            print(f"   - Onboarding completo: {user_context_from_phone.onboarding_completed}")
            print(f"   - É usuário: {user_context_from_phone.is_user}")
        else:
            print(f"   - Nenhum contexto encontrado!")
        
        # Usa o contexto encontrado pela função (que é o que acontece no endpoint principal)
        final_user_context = user_context_from_phone or request.user_context
        
        # Testa seleção de agente
        user_memory = get_user_memory(request.phone_number)
        selected_agent = determine_initial_agent(
            message=request.message,
            user_history=user_memory,
            recommended_agent=request.recommended_agent,
            user_context=final_user_context
        )
        
        # Simula resposta da IA
        mock_ai_response = f"Olá {request.user_name}! Esta é uma resposta de teste do agente {selected_agent}."
        
        # Testa lógica de adição de link
        final_response = mock_ai_response
        link_added = False
        if request.user_context and request.user_context.user_type == "incomplete_onboarding":
            if request.user_context.onboarding_url:
                final_response += f"\\n\\n🔗 Finalize seu cadastro aqui: {request.user_context.onboarding_url}"
                link_added = True
        
        return {
            "test_success": True,
            "user_context_received": request.user_context.dict() if request.user_context else None,
            "selected_agent": selected_agent,
            "agent_available": selected_agent in agents_cache,
            "original_response": mock_ai_response,
            "final_response": final_response,
            "link_added": link_added,
            "memory_entries": len(user_memory),
            "timestamp": time.time()
        }
        
    except Exception as e:
        print(f"❌ Erro no teste: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro no teste: {str(e)}")

@app.delete("/user-memory/{phone_number}")
async def clear_user_memory_endpoint(phone_number: str):
    """Limpa a memória/histórico de um usuário"""
    try:
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        memory_key = f"user_memory:{clean_phone}"
        
        # Remove do Redis
        redis_client.delete(memory_key)
        
        return {
            "message": f"Memória do usuário {clean_phone} limpa com sucesso",
            "phone_number": clean_phone,
            "memory_key": memory_key
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao limpar memória: {str(e)}")


@app.post("/admin/reload-agents")
async def reload_agents():
    """Recarrega os agentes do banco de dados (limpa cache)"""
    try:
        success = load_agents_from_supabase()
        if success:
            return {
                "success": True,
                "message": f"Agentes recarregados com sucesso",
                "agents_loaded": len(agents_cache),
                "agents": list(agents_cache.keys())
            }
        else:
            return {
                "success": False,
                "message": "Falha ao carregar agentes",
                "agents_loaded": 0
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Erro ao recarregar agentes: {str(e)}",
            "agents_loaded": len(agents_cache)
        }


if __name__ == "__main__":
    import uvicorn
    import os
    
    # Porta configurável via variável de ambiente
    port = int(os.getenv("PORT", 9000))
    
    print("🚀 Iniciando Aleen AI Python Service...")
    print(f"🌐 Servidor rodando em: http://0.0.0.0:{port}")
    print(f"📋 Health check: http://0.0.0.0:{port}/health")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info",
        access_log=True
    )
