#!/usr/bin/env python3
from datetime import datetime, timedelta

def test_timezone_calculation():
    """Testa o cálculo de timezone e dias da semana"""
    
    # Simula UTC atual
    utc_now = datetime.utcnow()
    print(f"UTC agora: {utc_now}")
    print(f"UTC weekday: {utc_now.weekday()} (0=segunda, 6=domingo)")
    
    # São Paulo é UTC-3
    timezone_offset = -3
    current_time = utc_now + timedelta(hours=timezone_offset)
    print(f"São Paulo agora: {current_time}")
    print(f"SP weekday: {current_time.weekday()}")
    
    # Array dos dias
    days_pt = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
    today = days_pt[current_time.weekday()]
    tomorrow = days_pt[(current_time.weekday() + 1) % 7]
    
    print(f"Hoje: {today}")
    print(f"Amanhã: {tomorrow}")
    
    # Verifica se está correto
    print(f"\n🎯 VERIFICAÇÃO:")
    print(f"Esperado hoje: quarta-feira")
    print(f"Calculado hoje: {today}")
    print(f"Esperado amanhã: quinta-feira") 
    print(f"Calculado amanhã: {tomorrow}")
    
    # Verifica treinos
    user_schedule = ['segunda-feira', 'quarta-feira', 'sexta-feira']
    
    print(f"\n💪 TREINOS:")
    print(f"Hoje ({today}) tem treino: {'SIM' if today in user_schedule else 'NÃO'}")
    print(f"Amanhã ({tomorrow}) tem treino: {'SIM' if tomorrow in user_schedule else 'NÃO'}")

if __name__ == "__main__":
    test_timezone_calculation()
