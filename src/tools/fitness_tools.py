"""
Fitness Tools
Ferramentas relacionadas a treinos e exercícios
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from ..services.supabase_service import SupabaseService

class FitnessTools:
    def __init__(self, supabase_service: SupabaseService):
        self.supabase = supabase_service
    
    def get_user_timezone_offset(self, phone_number: str) -> int:
        """Obtém o offset de timezone baseado na localização do usuário no onboarding"""
        try:
            # Busca usuário
            user_result = self.supabase.client.table('users').select('id').eq('phone', phone_number).execute()
            if not user_result.data:
                return -3  # Default Brasil se não encontrar usuário
            
            user_id = user_result.data[0]['id']
            
            # Busca resposta da pergunta de localização (step 20, field_name 'location')
            location_response = self.supabase.client.table('onboarding_responses').select('response_value').eq('user_id', user_id).execute()
            
            if not location_response.data:
                return -3  # Default Brasil se não tiver onboarding
            
            # Procura pela resposta de location
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
            
            return -3  # Default Brasil
            
        except Exception as e:
            print(f"Erro ao buscar timezone: {str(e)}")
            return -3  # Default Brasil em caso de erro

    def check_user_training_plan(self, phone_number: str) -> Dict:
        """Verifica se o usuário já possui um plano de treino ativo"""
        try:
            # Busca usuário pelo telefone
            user_result = self.supabase.client.table('users').select('id, onboarding').eq('phone', phone_number).execute()
            
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
            plan_result = self.supabase.client.table('training_plans').select('*').eq('user_id', user_id).eq('is_active', True).execute()
            
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

    def get_user_workout_plan_details(self, phone_number: str) -> Dict:
        """Busca detalhes completos do plano de treino do usuário"""
        try:
            print(f"🔍 DEBUG: Buscando plano para telefone: {phone_number}")
            
            # Busca usuário
            user_result = self.supabase.client.table('users').select('id').eq('phone', phone_number).execute()
            print(f"🔍 DEBUG: User result: {user_result.data}")
            
            if not user_result.data:
                print("❌ DEBUG: Usuário não encontrado")
                return {"error": "Usuário não encontrado"}
            
            user_id = user_result.data[0]['id']
            print(f"🔍 DEBUG: User ID encontrado: {user_id}")
            
            # Busca plano ativo
            plan_result = self.supabase.client.table('training_plans').select('*').eq('user_id', user_id).eq('is_active', True).execute()
            print(f"🔍 DEBUG: Plan result: {plan_result.data}")
            
            if not plan_result.data:
                print("❌ DEBUG: Nenhum plano ativo encontrado")
                return {"error": "Nenhum plano de treino ativo encontrado"}
            
            plan = plan_result.data[0]
            print(f"🔍 DEBUG: Plano encontrado: {plan['name']}, ID: {plan['id']}")
            
            # Busca todos os treinos do plano COM EXERCÍCIOS COMPLETOS
            workouts_result = self.supabase.client.table('plan_workouts').select('''
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
            print(f"🔍 DEBUG: Workouts result: {len(workouts_result.data)} workouts encontrados")
            
            for workout in workouts_result.data:
                print(f"🔍 DEBUG: Workout - Dia: {workout['day_of_week']}, Template: {workout.get('workout_templates', {}).get('name', 'N/A')}")
            
            # CALCULA PRÓXIMO TREINO BASEADO NO DIA ATUAL
            print("🔍 DEBUG: Iniciando cálculo do próximo treino...")
            
            # Busca timezone do usuário (IGUAL NUTRIÇÃO!)
            timezone_offset = self.get_user_timezone_offset(phone_number)
            current_time = datetime.utcnow() + timedelta(hours=timezone_offset)
            current_weekday = current_time.weekday()  # 0=segunda, 1=terça, 2=quarta, 3=quinta, 4=sexta, 5=sábado, 6=domingo
            print(f"🔍 DEBUG: Timezone offset: {timezone_offset}")
            print(f"🔍 DEBUG: Current time: {current_time}, Weekday: {current_weekday}")
            
            # Mapeia número para texto
            days_map = {
                0: "segunda-feira",
                1: "terça-feira", 
                2: "quarta-feira",
                3: "quinta-feira",
                4: "sexta-feira",
                5: "sábado",
                6: "domingo"
            }
            
            current_day_name = days_map[current_weekday]
            print(f"🔍 DEBUG: Dia atual: {current_day_name}")
            
            # Encontra próximo treino
            next_workout = None
            next_workout_day = None
            days_until_next = None
            
            print("🔍 DEBUG: Procurando treino para hoje...")
            # Primeiro verifica se hoje tem treino
            for workout in workouts_result.data:
                print(f"🔍 DEBUG: Comparando '{workout['day_of_week']}' com '{current_day_name}'")
                if workout['day_of_week'] == current_day_name:
                    next_workout = workout
                    next_workout_day = "hoje"
                    days_until_next = 0
                    print(f"✅ DEBUG: Treino encontrado para hoje: {workout.get('workout_templates', {}).get('name', 'N/A')}")
                    break
            
            # Se hoje não tem, procura os próximos dias
            if not next_workout:
                print("🔍 DEBUG: Hoje não tem treino, procurando próximos dias...")
                for days_ahead in range(1, 8):  # Próximos 7 dias
                    target_weekday = (current_weekday + days_ahead) % 7
                    target_day_name = days_map[target_weekday]
                    print(f"🔍 DEBUG: Verificando {target_day_name} (dias à frente: {days_ahead})")
                    
                    for workout in workouts_result.data:
                        if workout['day_of_week'] == target_day_name:
                            next_workout = workout
                            if days_ahead == 1:
                                next_workout_day = "amanhã"
                            else:
                                next_workout_day = target_day_name
                            days_until_next = days_ahead
                            print(f"✅ DEBUG: Próximo treino encontrado: {target_day_name} - {workout.get('workout_templates', {}).get('name', 'N/A')}")
                            break
                    
                    if next_workout:
                        break
            
            result = {
                "success": True,
                "plan_details": plan,
                "workouts": workouts_result.data,
                "total_workouts": len(workouts_result.data),
                "plan_name": plan['name'],
                "objective": plan['objective'],
                "current_day": current_day_name,
                "next_workout": next_workout,
                "next_workout_day": next_workout_day,
                "days_until_next": days_until_next
            }
            
            print(f"✅ DEBUG: Resultado final - Próximo treino: {next_workout_day}")
            return result
            
        except Exception as e:
            print(f"❌ DEBUG: ERRO CAPTURADO: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"error": f"Erro ao buscar detalhes do plano: {str(e)}"}

# Instância global (será injetada)
fitness_tools = None
