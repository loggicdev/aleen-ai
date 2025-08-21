import os
import re
import time
import sys
import json
import requests
import secrets
import string
import traceback
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
    }
]

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
                "message": "Usuário não possui plano alimentar ativo",
                "user_id": user_id,
                "onboarding_completed": True
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
            
            # Adiciona instrução de idioma responsivo
            language_instruction = """

INSTRUÇÃO CRÍTICA DE IDIOMA:
- SEMPRE responda no mesmo idioma que o usuário está falando
- Se o usuário falar em português, responda em português  
- Se o usuário falar em inglês, responda em inglês
- Se o usuário falar em espanhol, responda em espanhol
- Mantenha o mesmo idioma durante toda a conversa
- Seja natural e fluente no idioma escolhido

"""
            
            final_prompt = base_prompt + language_instruction
            
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
        
        # USUÁRIO COMPLETO: Prioridade para verificar nutrição
        elif user_context.user_type == "complete_user":
            print(f"✅ USUÁRIO COMPLETO - direcionando para NUTRITION para verificar plano alimentar")
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
        # Busca usuário pelo telefone
        user_result = supabase.table('users').select('id, onboarding, auth_user_id').eq('phone', phone_number).execute()
        
        if not user_result.data:
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
        auth_user_id = user_data.get('auth_user_id')
        
        if not onboarding_completed:
            # Tem registro mas onboarding incompleto
            # Busca URL de onboarding se existir
            onboarding_url = f"https://aleen.dp.claudy.host/onboarding/{auth_user_id}" if auth_user_id else None
            
            return UserContext(
                user_type="incomplete_onboarding",
                has_account=True,
                onboarding_completed=False,
                is_lead=True,
                is_user=False,
                onboarding_url=onboarding_url
            )
        else:
            # Usuário completo
            onboarding_url = f"https://aleen.dp.claudy.host/onboarding/{auth_user_id}" if auth_user_id else None
            
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
        
        # Cria mensagens para OpenAI incluindo contexto com memória
        messages = [
            {"role": "system", "content": agent.instructions + memory_instruction + language_instruction + ux_critical_rule + tools_instruction},
            {"role": "user", "content": f"Usuário: {request.user_name}\n\nContexto da conversa:\n{conversation_context}"}
        ]
        
        # Executa com OpenAI (com tools disponíveis)
        try:
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
        
        # Testa seleção de agente
        user_memory = get_user_memory(request.phone_number)
        selected_agent = determine_initial_agent(
            message=request.message,
            user_history=user_memory,
            recommended_agent=request.recommended_agent,
            user_context=request.user_context
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
