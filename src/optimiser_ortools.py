# src/optimiser_ortools.py

import sys
import os
# Add the root directory to the system path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from ortools.sat.python import cp_model
from src.data_handler import load_json, load_and_validate_data  # To load the existing schedule and other data
import datetime
import json
from datetime import timedelta
from typing import Any, List, Dict, Tuple

# Data paths
DATA_DIR = 'data'
SCHEDULE_FILE = 'schedule.json'

# Define working hours
WORKDAY_START = datetime.time(8, 0)
WORKDAY_END = datetime.time(17, 0)
WORKDAYS = set([0, 1, 2, 3, 4])  # Monday=0, ..., Friday=4

# Maximum number of splits allowed per job
MAX_SPLITS = 5

def datetime_to_minutes(dt: datetime.datetime, t_start: datetime.datetime) -> int:
    return int((dt - t_start).total_seconds() / 60)

def minutes_to_datetime(minutes: int, t_start: datetime.datetime) -> datetime.datetime:
    return t_start + timedelta(minutes=minutes)

def generate_working_windows(t_start: datetime.datetime, t_end: datetime.datetime) -> List[Tuple[int, int]]:
    current = t_start
    working_windows = []
    while current < t_end:
        if current.weekday() in WORKDAYS:
            day_start = datetime.datetime.combine(current.date(), WORKDAY_START)
            day_end = datetime.datetime.combine(current.date(), WORKDAY_END)
            if day_start < t_start:
                day_start = t_start
            if day_end > t_end:
                day_end = t_end
            if day_start < day_end:
                start_min = datetime_to_minutes(day_start, t_start)
                end_min = datetime_to_minutes(day_end, t_start)
                working_windows.append((start_min, end_min))
        current += timedelta(days=1)
    return working_windows

def save_optimized_schedule(schedule, optimizer_name):
    filename = f'optimized_schedule_{optimizer_name.lower()}.json'
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(schedule, f, indent=4)
    print(f"\nOptimized schedule saved to {filepath}")

# def optimize_schedule():
#     print("Loading and validating all data...")
#     try:
#         data = load_and_validate_data()
#     except Exception as e:
#         print(f"Error loading data: {e}")
#         return

#     # Extract preprocessed data
#     jobs_data = data['jobs']
#     technicians_data = data['technicians']
#     tools_data = data['tools']
#     materials_data = data['materials']
#     equipment_data = data['equipment']

#     # Initialize the CP-SAT model
#     model = cp_model.CpModel()

#     # Define time parameters
#     t_start = datetime.datetime.strptime(data.get('t_start', '2023-12-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
#     t_end = datetime.datetime.strptime(data.get('t_end', '2023-12-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')
#     total_minutes = datetime_to_minutes(t_end, t_start)

#     # Generate working windows
#     working_windows = generate_working_windows(t_start, t_end)

#     # Create job variables
#     job_vars = {}
#     for job in jobs_data:
#         job_id = job['job_id']
#         duration = int(job['duration'] * 60)  # Convert hours to minutes
        
#         # Create variables for each possible split
#         splits = []
#         for s in range(MAX_SPLITS):
#             start = model.NewIntVar(0, total_minutes, f'start_{job_id}_{s}')
#             end = model.NewIntVar(0, total_minutes, f'end_{job_id}_{s}')
#             duration_var = model.NewIntVar(0, duration, f'duration_{job_id}_{s}')
#             is_used = model.NewBoolVar(f'is_used_{job_id}_{s}')
            
#             # Link the variables
#             model.Add(end == start + duration_var)
#             model.Add(duration_var == 0).OnlyEnforceIf(is_used.Not())
#             model.Add(duration_var > 0).OnlyEnforceIf(is_used)
            
#             splits.append((start, end, duration_var, is_used))
        
#         job_vars[job_id] = splits

#         # Ensure total duration matches the job's required duration
#         model.Add(sum(split[2] for split in splits) == duration)

#         # Ensure splits are in order
#         for s in range(MAX_SPLITS - 1):
#             model.Add(splits[s][1] <= splits[s+1][0]).OnlyEnforceIf(splits[s][3], splits[s+1][3])

#     # Add constraints
#     # ... (previous code remains the same)

#     # 1. Equipment constraints
#     equipment_usage = {equip['equipment_id']: [] for equip in equipment_data}
#     for job in jobs_data:
#         job_id = job['job_id']
#         equip_id = job['equipment_id']
#         for s, split in enumerate(job_vars[job_id]):
#             start, end, duration, is_used = split
#             interval = model.NewOptionalIntervalVar(
#                 start, 
#                 duration,
#                 model.NewIntVar(0, total_minutes, f'end_{job_id}_split{s}'),
#                 is_used,
#                 f'equip_{equip_id}_{job_id}_split{s}'
#             )
#             equipment_usage[equip_id].append(interval)

#     for equip_id, usage in equipment_usage.items():
#         model.AddNoOverlap(usage)

#     # 2. Technician constraints
#     technician_usage = {tech['tech_id']: [] for tech in technicians_data}
#     for job in jobs_data:
#         job_id = job['job_id']
#         required_skills = set(job['required_skills'])
#         for tech in technicians_data:
#             if set(tech['skills']).intersection(required_skills):
#                 for s, split in enumerate(job_vars[job_id]):
#                     start, end, duration, is_used = split
#                     interval = model.NewOptionalIntervalVar(
#                         start, 
#                         duration,
#                         model.NewIntVar(0, total_minutes, f'tech_end_{tech["tech_id"]}_{job_id}_split{s}'),
#                         is_used,
#                         f'tech_{tech["tech_id"]}_{job_id}_split{s}'
#                     )
#                     technician_usage[tech['tech_id']].append(interval)

#     for tech_id, usage in technician_usage.items():
#         model.AddNoOverlap(usage)

#     # 3. Tool constraints
#     tool_usage = {tool['tool_id']: [] for tool in tools_data}
#     for job in jobs_data:
#         job_id = job['job_id']
#         for tool_req in job['required_tools']:
#             tool_id = tool_req['tool_id']
#             quantity = tool_req['quantity']
#             for s, split in enumerate(job_vars[job_id]):
#                 start, end, duration, is_used = split
#                 interval = model.NewOptionalIntervalVar(
#                     start, 
#                     duration,
#                     model.NewIntVar(0, total_minutes, f'tool_end_{tool_id}_{job_id}_split{s}'),
#                     is_used,
#                     f'tool_{tool_id}_{job_id}_split{s}'
#                 )
#                 tool_usage[tool_id].append((interval, quantity))

#     for tool_id, usage in tool_usage.items():
#         tool_capacity = next(tool['quantity'] for tool in tools_data if tool['tool_id'] == tool_id)
#         intervals = [u[0] for u in usage]
#         demands = [u[1] for u in usage]
#         model.AddCumulative(intervals, demands, tool_capacity)

#     # ... (rest of the code remains the same)

#     # 4. Material constraints
#     for job in jobs_data:
#         job_id = job['job_id']
#         for mat_req in job['required_materials']:
#             mat_id = mat_req['material_id']
#             quantity = mat_req['quantity']
#             material = next(m for m in materials_data if m['material_id'] == mat_id)
#             model.Add(sum(split[2] for split in job_vars[job_id]) * quantity <= material['quantity'] * total_minutes)

#     # 5. Precedence constraints
#     for job in jobs_data:
#         job_id = job['job_id']
#         for pred_id in job['precedence']:
#             model.Add(job_vars[pred_id][-1][1] <= job_vars[job_id][0][0]).OnlyEnforceIf(job_vars[job_id][0][3])

#     # ... (previous code remains the same)

#     # 6. Working windows constraints
#     for job_id, splits in job_vars.items():
#         for split in splits:
#             start, end, duration, is_used = split
#             window_constraints = []
#             for w_start, w_end in working_windows:
#                 in_window = model.NewBoolVar(f'{job_id}_in_window_{w_start}_{w_end}')
#                 model.Add(start >= w_start).OnlyEnforceIf(in_window)
#                 model.Add(end <= w_end).OnlyEnforceIf(in_window)
#                 window_constraints.append(in_window)
            
#             # The job split must be in at least one working window if it's used
#             model.Add(sum(window_constraints) >= 1).OnlyEnforceIf(is_used)
#             model.Add(sum(window_constraints) == 0).OnlyEnforceIf(is_used.Not())

#     # ... (rest of the code remains the same)

#     # Objective: Minimize makespan and maximize scheduled jobs
#     makespan = model.NewIntVar(0, total_minutes, 'makespan')
#     model.AddMaxEquality(makespan, [split[1] for splits in job_vars.values() for split in splits])
    
#     total_scheduled = sum(split[3] for splits in job_vars.values() for split in splits)
#     model.Maximize(total_scheduled * total_minutes - makespan)

#     # Solve the problem
#     solver = cp_model.CpSolver()
#     solver.parameters.max_time_in_seconds = 300.0  # 5 minutes limit
#     status = solver.Solve(model)

#     # Process results
#     if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
#         optimized_schedule = []
#         for job in jobs_data:
#             job_id = job['job_id']
#             job_splits = []
#             for s, split in enumerate(job_vars[job_id]):
#                 if solver.Value(split[3]):  # if this split is used
#                     start_time = minutes_to_datetime(solver.Value(split[0]), t_start)
#                     end_time = minutes_to_datetime(solver.Value(split[1]), t_start)
#                     job_splits.append({
#                         'split_id': s + 1,
#                         'scheduled_start_time': start_time.strftime('%Y-%m-%dT%H:%M:%S'),
#                         'scheduled_end_time': end_time.strftime('%Y-%m-%dT%H:%M:%S'),
#                         'duration_minutes': solver.Value(split[1]) - solver.Value(split[0])
#                     })
#             if job_splits:
#                 assigned_technicians = [
#                     tech['tech_id'] for tech in technicians_data
#                     if set(tech['skills']).intersection(set(job['required_skills']))
#                 ]
#                 optimized_schedule.append({
#                     'job_id': job_id,
#                     'equipment_id': job['equipment_id'],
#                     'assigned_technicians': assigned_technicians,
#                     'splits': job_splits
#                 })

#         # Save the optimized schedule
#         optimized_schedule_path = os.path.join(DATA_DIR, 'optimized_schedule.json')
#         with open(optimized_schedule_path, 'w') as f:
#             json.dump(optimized_schedule, f, indent=4)
#         print(f"\nOptimized schedule saved to {optimized_schedule_path}")

#         # Calculate and print statistics
#         total_jobs = len(jobs_data)
#         scheduled_jobs = len(optimized_schedule)
#         print(f"\nTotal jobs: {total_jobs}")
#         print(f"Scheduled jobs: {scheduled_jobs}")
#         print(f"Scheduling rate: {scheduled_jobs/total_jobs*100:.2f}%")
#         print(f"Makespan: {solver.Value(makespan)} minutes")

#     else:
#         print("No optimal or feasible solution found.")

#     return optimized_schedule if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE else None

def optimize_schedule():
    print("Loading and validating all data...")
    data = load_and_validate_data()

    jobs_data = data['jobs']
    technicians_data = data['technicians']
    tools_data = data['tools']
    materials_data = data['materials']
    equipment_data = data['equipment']

    model = cp_model.CpModel()

    # Time parameters
    t_start = datetime.datetime.strptime(data.get('t_start', '2023-12-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
    t_end = datetime.datetime.strptime(data.get('t_end', '2023-12-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')
    total_minutes = int((t_end - t_start).total_seconds() / 60)

    # Generate working windows
    working_windows = generate_working_windows(t_start, t_end)

    # Create job variables
    job_vars = {}
    for job in jobs_data:
        job_id = job['job_id']
        duration = int(job['duration'] * 60)  # Convert hours to minutes
        
        start = model.NewIntVar(0, total_minutes, f'start_{job_id}')
        end = model.NewIntVar(0, total_minutes, f'end_{job_id}')
        
        # Ensure job duration is correct
        model.Add(end - start == duration)
        
        # Ensure job is within working windows
        window_constraints = []
        for w_start, w_end in working_windows:
            is_in_window = model.NewBoolVar(f'{job_id}_in_window_{w_start}_{w_end}')
            model.Add(start >= w_start).OnlyEnforceIf(is_in_window)
            model.Add(end <= w_end).OnlyEnforceIf(is_in_window)
            window_constraints.append(is_in_window)
        model.Add(sum(window_constraints) >= 1)
        
        job_vars[job_id] = (start, end)

    # Equipment constraints
    for equip in equipment_data:
        equip_id = equip['equipment_id']
        equip_jobs = [j for j in jobs_data if j['equipment_id'] == equip_id]
        model.AddNoOverlap([model.NewIntervalVar(job_vars[j['job_id']][0], 
                                                 j['duration'] * 60, 
                                                 job_vars[j['job_id']][1], 
                                                 f'interval_{j["job_id"]}')
                            for j in equip_jobs])

    # Technician constraints and assignment variables
    tech_vars = {}
    tech_assignment_vars = {}
    for tech in technicians_data:
        tech_id = tech['tech_id']
        tech_jobs = []
        tech_assignment_vars[tech_id] = {}
        for job in jobs_data:
            if set(tech['skills']).intersection(set(job['required_skills'])):
                is_assigned = model.NewBoolVar(f'tech_{tech_id}_assigned_to_{job["job_id"]}')
                tech_assignment_vars[tech_id][job['job_id']] = is_assigned
                interval = model.NewOptionalIntervalVar(
                    job_vars[job['job_id']][0],
                    job['duration'] * 60,
                    job_vars[job['job_id']][1],
                    is_assigned,
                    f'tech_{tech_id}_interval_{job["job_id"]}'
                )
                tech_jobs.append(interval)
        model.AddNoOverlap(tech_jobs)
        tech_vars[tech_id] = tech_jobs

    # Ensure correct number of technicians are assigned to each job
    for job in jobs_data:
        job_id = job['job_id']
        model.Add(sum(tech_assignment_vars[tech['tech_id']][job_id]
                      for tech in technicians_data
                      if job_id in tech_assignment_vars[tech['tech_id']]) == 
                  len(job['required_skills']))

    # Tool constraints
    for tool in tools_data:
        tool_id = tool['tool_id']
        tool_capacity = tool['quantity']
        tool_usage = []
        for job in jobs_data:
            for req_tool in job['required_tools']:
                if req_tool['tool_id'] == tool_id:
                    interval = model.NewIntervalVar(
                        job_vars[job['job_id']][0],
                        job['duration'] * 60,
                        job_vars[job['job_id']][1],
                        f'tool_{tool_id}_interval_{job["job_id"]}'
                    )
                    tool_usage.append((interval, req_tool['quantity']))
        model.AddCumulative([u[0] for u in tool_usage], [u[1] for u in tool_usage], tool_capacity)

    # Material constraints
    for material in materials_data:
        material_id = material['material_id']
        material_capacity = material['quantity']
        material_usage = 0
        for job in jobs_data:
            for req_material in job['required_materials']:
                if req_material['material_id'] == material_id:
                    material_usage += req_material['quantity']
        model.Add(material_usage <= material_capacity)

    # Precedence constraints
    for job in jobs_data:
        for pred_id in job['precedence']:
            model.Add(job_vars[job['job_id']][0] >= job_vars[pred_id][1])

    # Objective: Minimize makespan
    makespan = model.NewIntVar(0, total_minutes, 'makespan')
    model.AddMaxEquality(makespan, [end for _, end in job_vars.values()])
    model.Minimize(makespan)

    # Solve the problem
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300.0  # 5 minutes limit
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        optimized_schedule = []
        for job in jobs_data:
            job_id = job['job_id']
            start_time = minutes_to_datetime(solver.Value(job_vars[job_id][0]), t_start)
            end_time = minutes_to_datetime(solver.Value(job_vars[job_id][1]), t_start)
            assigned_technicians = [
                tech['tech_id'] for tech in technicians_data
                if job_id in tech_assignment_vars[tech['tech_id']] and 
                solver.Value(tech_assignment_vars[tech['tech_id']][job_id])
            ]
            optimized_schedule.append({
                'job_id': job_id,
                'equipment_id': job['equipment_id'],
                'scheduled_start_time': start_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'scheduled_end_time': end_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'duration_hours': job['duration'],
                'assigned_technicians': assigned_technicians
            })

        # Save the optimized schedule
        save_optimized_schedule(optimized_schedule, "OR-Tools")

        # Calculate and print statistics
        total_jobs = len(jobs_data)
        scheduled_jobs = len(optimized_schedule)
        print(f"\nTotal jobs: {total_jobs}")
        print(f"Scheduled jobs: {scheduled_jobs}")
        print(f"Scheduling rate: {scheduled_jobs/total_jobs*100:.2f}%")
        print(f"Makespan: {solver.Value(makespan)} minutes")

    else:
        print("No optimal or feasible solution found.")

    return optimized_schedule if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE else None

if __name__ == "__main__":
    optimize_schedule()