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



def optimize_schedule():
    print("Loading and validating all data...")
    data = load_and_validate_data()

    jobs_data = data['jobs']
    technicians_data = data['technicians']
    #87866666666666666666666666666666666666666666666666666666

    print("Validating technician-job skill matches...")
    valid_jobs_data = []
    invalid_jobs = []

    for job in jobs_data:
        required_skills = set(job['required_skills'])
        matching_techs = [
            tech for tech in technicians_data
            if required_skills & set(tech['skills'])
        ]
        if not matching_techs:
            invalid_jobs.append(job['job_id'])
        else:
            valid_jobs_data.append(job)

    # Inform about skipped jobs
    if invalid_jobs:
        print(f"⚠️ Skipping jobs with no matching technicians: {invalid_jobs}")

    jobs_data = valid_jobs_data  # Use only valid jobs

    #8799999999999999999999999999999999999999999999999999999

    
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

    
    # Technician constraints and assignment variables (fixed overbooking)
    tech_assignment_vars = {}  # Map: tech_id -> { job_id -> BoolVar }
    for tech in technicians_data:
        tech_id = tech['tech_id']
        tech_assignment_vars[tech_id] = {}

        # Collect all job intervals for this technician
        tech_intervals = []

        for job in jobs_data:
            job_id = job['job_id']

            # Check if technician can work on this job
            if set(tech['skills']).intersection(set(job['required_skills'])):
                is_assigned = model.NewBoolVar(f'tech_{tech_id}_assigned_to_{job_id}')
                tech_assignment_vars[tech_id][job_id] = is_assigned

                # Technician interval linked to job interval
                interval = model.NewOptionalIntervalVar(
                    job_vars[job_id][0],
                    int(job['duration'] * 60),
                    job_vars[job_id][1],
                    is_assigned,
                    f'tech_{tech_id}_interval_{job_id}'
                )
                tech_intervals.append(interval)

        # Ensure this technician is not double-booked
        if tech_intervals:
            model.AddNoOverlap(tech_intervals)

    # Ensure each job has the required number of distinct technicians
    for job in jobs_data:
        job_id = job['job_id']

        # Count distinct technicians assigned to this job
        tech_count = [
            tech_assignment_vars[tech['tech_id']][job_id]
            for tech in technicians_data
            if job_id in tech_assignment_vars[tech['tech_id']]
        ]

        # Job must have at least one technician per required skill (or as needed)
        model.Add(sum(tech_count) >= len(set(job['required_skills'])))


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