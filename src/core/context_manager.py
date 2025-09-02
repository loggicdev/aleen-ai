"""
Context Manager
Gerencia contexto de conversação e análise de usuários
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
import redis
import os

class ContextManager:
    def __init__(self):
        self.redis_client = None
        self._initialize_redis()
    
    def _initialize_redis(self):
        """Inicializa conexão Redis"""
        try:
            print("🔧 [REDIS] Inicializando conexão...")
            
            host = os.getenv('REDIS_HOST', 'localhost')
            port = int(os.getenv('REDIS_PORT', 6379))
            password = os.getenv('REDIS_PASSWORD')
            
            print(f"🔗 [REDIS] Conectando em {host}:{port}")
            
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                password=password,
                decode_responses=True
            )
            
            # Testa conexão
            self.redis_client.ping()
            print("✅ [REDIS] Context Manager inicializado com sucesso")
            
        except Exception as e:
            print(f"❌ [REDIS] Falha na inicialização: {str(e)}")
            print("⚠️ [REDIS] Sistema continuará sem cache de contexto")
    
    def save_conversation_context(self, phone_number: str, context_data: Dict[str, Any], ttl: int = 3600):
        """Salva contexto da conversa no Redis"""
        try:
            print(f"💾 [CONTEXT] Salvando contexto para {phone_number}")
            
            key = f"context:{phone_number}"
            
            # Adiciona timestamp
            context_data['timestamp'] = datetime.now().isoformat()
            context_data['phone'] = phone_number
            
            # Log do que está sendo salvo
            print(f"📦 [CONTEXT] Dados: {len(str(context_data))} chars, TTL: {ttl}s")
            
            if self.redis_client:
                self.redis_client.setex(
                    key, 
                    ttl, 
                    json.dumps(context_data, ensure_ascii=False)
                )
                print(f"✅ [CONTEXT] Contexto salvo com sucesso para {phone_number}")
            else:
                print(f"⚠️ [CONTEXT] Redis indisponível - contexto não salvo")
            
            return True
            
        except Exception as e:
            print(f"❌ [CONTEXT] Erro ao salvar contexto: {str(e)}")
            return False
    
    def get_conversation_context(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Recupera contexto da conversa"""
        try:
            key = f"context:{phone_number}"
            context_str = self.redis_client.get(key)
            
            if context_str:
                context = json.loads(context_str)
                print(f"📖 Contexto recuperado para {phone_number}")
                return context
            
            print(f"📭 Nenhum contexto encontrado para {phone_number}")
            return None
            
        except Exception as e:
            print(f"❌ Erro ao recuperar contexto: {str(e)}")
            return None
    
    def update_conversation_history(self, phone_number: str, message: str, role: str = "user"):
        """Atualiza histórico de conversa"""
        try:
            context = self.get_conversation_context(phone_number) or {}
            
            if 'history' not in context:
                context['history'] = []
            
            # Adiciona nova mensagem
            context['history'].append({
                'role': role,
                'content': message,
                'timestamp': datetime.now().isoformat()
            })
            
            # Mantém apenas últimas 20 mensagens
            context['history'] = context['history'][-20:]
            
            self.save_conversation_context(phone_number, context)
            return True
            
        except Exception as e:
            print(f"❌ Erro ao atualizar histórico: {str(e)}")
            return False
    
    def analyze_user_intent(self, message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Analisa intenção do usuário baseado na mensagem e contexto"""
        print(f"🧠 [INTENT] Analisando intenção: '{message[:50]}...'")
        
        message_lower = message.lower().strip()
        
        # Palavras-chave para diferentes domínios
        fitness_keywords = ['treino', 'exercicio', 'musculacao', 'academia', 'workout', 'fitness']
        nutrition_keywords = ['comida', 'receita', 'dieta', 'alimentacao', 'cardapio', 'refeicao', 'meal']
        onboarding_keywords = ['cadastro', 'registro', 'perfil', 'dados', 'informacoes']
        
        intent_analysis = {
            'domain': 'general',
            'confidence': 0.0,
            'keywords_found': [],
            'suggested_agent': 'assistant',
            'context_relevant': bool(context)
        }
        
        # Análise de domínio
        if any(keyword in message_lower for keyword in fitness_keywords):
            intent_analysis.update({
                'domain': 'fitness',
                'confidence': 0.8,
                'suggested_agent': 'fitness_trainer',
                'keywords_found': [kw for kw in fitness_keywords if kw in message_lower]
            })
            print(f"🏋️ [INTENT] Domínio detectado: FITNESS (confiança: 0.8)")
            
        elif any(keyword in message_lower for keyword in nutrition_keywords):
            intent_analysis.update({
                'domain': 'nutrition',
                'confidence': 0.8,
                'suggested_agent': 'nutritionist',
                'keywords_found': [kw for kw in nutrition_keywords if kw in message_lower]
            })
            print(f"🥗 [INTENT] Domínio detectado: NUTRITION (confiança: 0.8)")
            
        elif any(keyword in message_lower for keyword in onboarding_keywords):
            intent_analysis.update({
                'domain': 'onboarding',
                'confidence': 0.9,
                'suggested_agent': 'onboarding_assistant',
                'keywords_found': [kw for kw in onboarding_keywords if kw in message_lower]
            })
            print(f"📝 [INTENT] Domínio detectado: ONBOARDING (confiança: 0.9)")
        else:
            print(f"❓ [INTENT] Domínio: GENERAL (sem keywords específicas)")
        
        print(f"🎯 [INTENT] Agente sugerido: {intent_analysis['suggested_agent']}")
        return intent_analysis
    
    def clear_context(self, phone_number: str):
        """Limpa contexto do usuário"""
        try:
            key = f"context:{phone_number}"
            self.redis_client.delete(key)
            print(f"🗑️ Contexto limpo para {phone_number}")
            return True
        except Exception as e:
            print(f"❌ Erro ao limpar contexto: {str(e)}")
            return False

# Instância global
context_manager = ContextManager()
