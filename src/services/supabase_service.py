"""
Supabase Service
Gerencia todas as operações com o banco de dados Supabase
"""
from supabase import create_client, Client
import os
from typing import Dict, Any, Optional

class SupabaseService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.client: Client = None
            self._initialize()
            self._initialized = True
    
    def _initialize(self):
        """Inicializa conexão com Supabase"""
        try:
            print("🔧 [SUPABASE] Inicializando conexão...")
            
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
            
            if not url or not key:
                print("⚠️ [SUPABASE] Variáveis de ambiente não encontradas")
                print("🔧 [SUPABASE] Necessárias: SUPABASE_URL e (SUPABASE_SERVICE_ROLE_KEY ou SUPABASE_ANON_KEY)")
                print(f"🔍 [SUPABASE] URL encontrada: {'✅' if url else '❌'}")
                print(f"🔍 [SUPABASE] SERVICE_ROLE_KEY: {'✅' if os.getenv('SUPABASE_SERVICE_ROLE_KEY') else '❌'}")
                print(f"🔍 [SUPABASE] ANON_KEY: {'✅' if os.getenv('SUPABASE_ANON_KEY') else '❌'}")
                self.client = None
                return
            
            print(f"🔗 [SUPABASE] Conectando em: {url[:30]}...")
            self.client = create_client(url, key)
            print("✅ [SUPABASE] Conexão estabelecida com sucesso")
            
        except Exception as e:
            print(f"❌ [SUPABASE] Falha na inicialização: {str(e)}")
            raise
    
    def get_client(self) -> Client:
        """Retorna cliente Supabase"""
        if not self.client:
            self._initialize()
        return self.client
    
    def health_check(self) -> Dict[str, Any]:
        """Verifica saúde da conexão"""
        try:
            print("🏥 [SUPABASE] Executando health check...")
            
            # Teste simples de conexão
            result = self.client.table('users').select('id').limit(1).execute()
            
            print("✅ [SUPABASE] Health check passou - conexão OK")
            return {
                "status": "healthy",
                "connected": True,
                "message": "Conexão com Supabase OK",
                "test_query": "users table accessible"
            }
        except Exception as e:
            print(f"❌ [SUPABASE] Health check falhou: {str(e)}")
            return {
                "status": "unhealthy", 
                "connected": False,
                "error": str(e)
            }

# Instância global
supabase_service = SupabaseService()

# Exporta também a classe para flexibilidade
__all__ = ['SupabaseService', 'supabase_service']
