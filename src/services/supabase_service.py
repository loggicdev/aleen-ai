"""
Supabase Database Service
Centraliza todas as operações de banco de dados
"""
import os
from supabase import create_client, Client
from typing import Dict, List, Any, Optional

class SupabaseService:
    def __init__(self):
        """Initialize Supabase client"""
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_ANON_KEY')
        self.client: Client = create_client(self.url, self.key)
    
    def get_user_by_phone(self, phone: str) -> Optional[Dict]:
        """Get user by phone number"""
        try:
            result = self.client.table('users').select('*').eq('phone', phone).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting user by phone: {e}")
            return None
    
    def get_agents(self) -> List[Dict]:
        """Get all active agents"""
        try:
            result = self.client.table('agents').select('*').execute()
            return result.data
        except Exception as e:
            print(f"Error getting agents: {e}")
            return []
    
    def save_memory(self, phone: str, message: str, response: str) -> bool:
        """Save conversation to memory"""
        try:
            self.client.table('memory').insert({
                'phone': phone,
                'message': message, 
                'response': response,
                'timestamp': 'now()'
            }).execute()
            return True
        except Exception as e:
            print(f"Error saving memory: {e}")
            return False
    
    def get_memory(self, phone: str, limit: int = 20) -> List[Dict]:
        """Get conversation memory"""
        try:
            result = self.client.table('memory').select('*').eq('phone', phone).order('timestamp', desc=True).limit(limit).execute()
            return result.data
        except Exception as e:
            print(f"Error getting memory: {e}")
            return []

# Global instance
supabase_service = SupabaseService()
