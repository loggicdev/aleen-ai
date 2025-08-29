"""
Agent Service
Gerencia carregamento e operações com agentes do banco de dados
"""
from typing import Dict, List, Optional
from .supabase_service import SupabaseService

class AgentService:
    def __init__(self, supabase_service: SupabaseService):
        self.supabase = supabase_service
        self.loaded_agents: Dict[str, Dict] = {}
    
    def load_agents_from_database(self) -> Dict[str, Dict]:
        """Carrega todos os agentes ativos do banco de dados"""
        try:
            result = self.supabase.client.table('agents').select('*').eq('is_active', True).execute()
            
            agents_dict = {}
            for agent_data in result.data:
                # Mapeia o agente para o formato esperado
                agent_key = agent_data['prompt_key'] or agent_data['name'].lower().replace(' ', '_')
                agents_dict[agent_key] = {
                    'name': agent_data['name'],
                    'prompt': agent_data['prompt'],
                    'type': agent_data['type'],
                    'is_active': agent_data['is_active']
                }
            
            self.loaded_agents = agents_dict
            print(f"Carregados {len(agents_dict)} agentes do Supabase:")
            for key, agent in agents_dict.items():
                print(f"  - {key}: {agent['name']} ({agent['type']})")
            
            return agents_dict
            
        except Exception as e:
            print(f"Erro ao carregar agentes do banco: {e}")
            return {}
    
    def get_agent_by_key(self, agent_key: str) -> Optional[Dict]:
        """Busca agente específico por chave"""
        return self.loaded_agents.get(agent_key)
    
    def get_agents_by_type(self, agent_type: str) -> List[Dict]:
        """Busca agentes por tipo"""
        return [agent for agent in self.loaded_agents.values() if agent['type'] == agent_type]
    
    def reload_agents(self) -> Dict[str, Dict]:
        """Recarrega agentes do banco (endpoint de reload)"""
        return self.load_agents_from_database()
