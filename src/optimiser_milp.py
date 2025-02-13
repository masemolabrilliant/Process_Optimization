import sys
import os
# Add the root directory to the system path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

import datetime
from typing import List, Dict, Tuple
from pulp import *
from src.data_handler import load_json, load_and_validate_data

# Data paths
DATA_DIR = 'data'

# Define working hours
WORKDAY_START = datetime.time(8, 0)
WORKDAY_END = datetime.time(17, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Monday to Friday

def is_working_hour(dt: datetime.datetime) -> bool:
    return dt.weekday() in WORKDAYS and WORKDAY_START <= dt.time() < WORKDAY_END

def save_optimized_schedule(schedule, optimizer_name):
    filename = f'optimized_schedule_{optimizer_name.lower()}.json'
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(schedule, f, indent=4)
    print(f"\nOptimized schedule saved to {filepath}")

def optimize_schedule():
    # Load data
    data = load_and_validate_data()
    
    # Extract data into usable structures
    jobs = data['jobs']
    technicians = data['technicians']
    equipment = data['equipment']
    tools = data['tools']
    materials = data['materials']
    
    # Define the scheduling horizon
    t_start = datetime.datetime.strptime(data.get('t_start', '2023-12-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
    t_end = datetime.datetime.strptime(data.get('t_end', '2023-12-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')
    
    # Discretize the time horizon into hourly intervals
    time_slots = []
    current_time = t_start
    while current_time < t_end:
        time_slots.append(current_time)
        current_time += datetime.timedelta(hours=1)
    
    # Create lists of IDs
    job_ids = [job['job_id'] for job in jobs]
    tech_ids = [tech['tech_id'] for tech in technicians]
    equip_ids = [equip['equipment_id'] for equip in equipment]
    tool_ids = [tool['tool_id'] for tool in tools]
    material_ids = [material['material_id'] for material in materials]
    
    # Initialize the problem
    prob = LpProblem("Maintenance_Scheduling", LpMinimize)
    
    # Decision variables
    x = LpVariable.dicts("job_start", 
                         ((j, t) for j in job_ids for t in range(len(time_slots))), 
                         cat='Binary')
    
    y = LpVariable.dicts("tech_assignment", 
                         ((j, k, t) for j in job_ids for k in tech_ids for t in range(len(time_slots))), 
                         cat='Binary')
    
    # Objective function: Minimize makespan
    makespan = LpVariable("makespan", lowBound=0)
    prob += makespan
    
    for j in job_ids:
        job = next(job for job in jobs if job['job_id'] == j)
        prob += makespan >= lpSum([t * x[j, t] for t in range(len(time_slots))]) + job['duration']
    
    # Constraints
    
    # 1. Each job must start exactly once
    for j in job_ids:
        prob += lpSum([x[j, t] for t in range(len(time_slots))]) == 1
    
    # 2. Jobs must finish within the scheduling horizon and respect working hours
    for j in job_ids:
        job = next(job for job in jobs if job['job_id'] == j)
        for t in range(len(time_slots)):
            if not all(is_working_hour(time_slots[t + d]) for d in range(job['duration']) if t + d < len(time_slots)):
                prob += x[j, t] == 0
    
    # 3. Equipment constraints
    for e in equip_ids:
        for t in range(len(time_slots)):
            prob += lpSum([x[j, t_start] 
                           for j in job_ids 
                           for t_start in range(max(0, t - int(next(job for job in jobs if job['job_id'] == j)['duration']) + 1), t + 1) 
                           if next(job for job in jobs if job['job_id'] == j)['equipment_id'] == e]) <= 1
    
    # 4. Technician assignment and skill coverage
    for j in job_ids:
        job = next(job for job in jobs if job['job_id'] == j)
        required_skills = set(job['required_skills'])
        for t in range(len(time_slots)):
            # Ensure that all required skills are covered by assigned technicians
            for skill in required_skills:
                prob += lpSum([y[j, k, t] for k in tech_ids if skill in next(tech for tech in technicians if tech['tech_id'] == k)['skills']]) >= x[j, t]
            
            # Ensure at least one technician is assigned when the job starts
            prob += lpSum([y[j, k, t] for k in tech_ids]) >= x[j, t]
            
            # Ensure no more technicians than required skills are assigned
            prob += lpSum([y[j, k, t] for k in tech_ids]) <= len(required_skills) * x[j, t]
    
    # 5. Technician availability (only during working hours)
    for k in tech_ids:
        for t in range(len(time_slots)):
            if is_working_hour(time_slots[t]):
                prob += lpSum([y[j, k, t_start]
                               for j in job_ids 
                               for t_start in range(max(0, t - int(next(job for job in jobs if job['job_id'] == j)['duration']) + 1), t + 1)]) <= 1
            else:
                prob += lpSum([y[j, k, t] for j in job_ids]) == 0
    
    # 6. Precedence constraints
    for j in job_ids:
        job = next(job for job in jobs if job['job_id'] == j)
        for p in job['precedence']:
            prob += lpSum([t * x[j, t] for t in range(len(time_slots))]) >= \
                    lpSum([t * x[p, t] for t in range(len(time_slots))]) + \
                    next(pred_job for pred_job in jobs if pred_job['job_id'] == p)['duration']
    
    # 7. Tool constraints (only during working hours)
    for tool in tools:
        for t in range(len(time_slots)):
            if is_working_hour(time_slots[t]):
                prob += lpSum([x[j, t_start] * next((req['quantity'] for req in job['required_tools'] if req['tool_id'] == tool['tool_id']), 0)
                               for j in job_ids 
                               for job in jobs if job['job_id'] == j
                               for t_start in range(max(0, t - int(job['duration']) + 1), t + 1)]) <= tool['quantity']
    
    # 8. Material constraints
    for material in materials:
        prob += lpSum([x[j, t] * next((req['quantity'] for req in job['required_materials'] if req['material_id'] == material['material_id']), 0)
                       for j in job_ids
                       for job in jobs if job['job_id'] == j
                       for t in range(len(time_slots))]) <= material['quantity']
    
    # Solve the problem
    solver = pulp.PULP_CBC_CMD(msg=True, timeLimit=600)  # 10 minutes time limit
    prob.solve(solver)
    
    # Extract the results
    if LpStatus[prob.status] == "Optimal" or LpStatus[prob.status] == "Feasible":
        schedule = []
        for j in job_ids:
            job = next(job for job in jobs if job['job_id'] == j)
            start_time = next((time_slots[t] for t in range(len(time_slots)) if value(x[j, t]) == 1), None)
            if start_time:
                end_time = start_time + datetime.timedelta(hours=job['duration'])
                assigned_techs = list(set([k for k in tech_ids for t in range(len(time_slots)) if value(y[j, k, t]) == 1]))
                
                schedule.append({
                    'job_id': j,
                    'equipment_id': job['equipment_id'],
                    'scheduled_start_time': start_time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'scheduled_end_time': end_time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'assigned_technicians': assigned_techs
                })
        
        # Save the optimized schedule
        save_optimized_schedule(schedule, "MILP")
        
        print(f"Optimal schedule found with makespan: {value(makespan)} hours")
        return schedule
    else:
        print(f"No optimal solution found. Status: {LpStatus[prob.status]}")
        return None

if __name__ == "__main__":
    optimize_schedule()