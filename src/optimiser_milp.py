import sys
import os
import json
import datetime
from datetime import timedelta
from typing import Any, List, Dict, Tuple
from ortools.sat.python import cp_model

# Add the root directory to the system path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.data_handler import load_and_validate_data

# Data paths
DATA_DIR = 'data'
SCHEDULE_FILE = 'schedule.json'

# Define working hours
WORKDAY_START = datetime.time(8, 0)
WORKDAY_END = datetime.time(17, 0)
WORKDAYS = set([0, 1, 2, 3, 4])  # Monday=0, ..., Friday=4

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
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f'optimized_schedule_{optimizer_name.lower()}.json'
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(schedule, f, indent=4, default=str)
    print(f"\nOptimized schedule saved to {filepath}")

def save_unscheduled_jobs(jobs, optimizer_name):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f'unscheduled_jobs_{optimizer_name.lower()}.json'
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(jobs, f, indent=4)
    print(f"Unscheduled jobs saved to {filepath}")

def optimize_schedule():
    print("\n=== MILP Optimization Starting ===")
    print("Loading and validating all data...")
    data = load_and_validate_data()

    jobs_data = data['jobs']
    technicians_data = data['technicians']
    tools_data = data['tools']
    materials_data = data['materials']
    equipment_data = data['equipment']

    t_start = datetime.datetime.strptime(data.get('t_start', '2023-12-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
    t_end = datetime.datetime.strptime(data.get('t_end', '2023-12-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

    # ==== RESOURCE PRECHECK & JOB FILTERING ====
    unfeasible_jobs = []
    filtered_jobs = []
    tool_caps = {tool["tool_id"]: tool["quantity"] for tool in tools_data}
    material_caps = {mat["material_id"]: mat["quantity"] for mat in materials_data}

    print("\nValidating job feasibility...")
    for job in jobs_data:
        reasons = []
        # Check tools
        for req in job["required_tools"]:
            avail = tool_caps.get(req["tool_id"], 0)
            if req["quantity"] > avail:
                reasons.append(f"Needs {req['quantity']} of tool {req['tool_id']}, only {avail} available.")
        
        # Check materials
        for req in job["required_materials"]:
            avail = material_caps.get(req["material_id"], 0)
            if req["quantity"] > avail:
                reasons.append(f"Needs {req['quantity']} of material {req['material_id']}, only {avail} available.")
        
        # Check technicians
        required_skills = set(job['required_skills'])
        matching_techs = [
            tech for tech in technicians_data
            if required_skills & set(tech['skills'])
        ]
        if not matching_techs:
            reasons.append("No matching technicians with required skills.")

        if reasons:
            unfeasible_jobs.append({"job_id": job["job_id"], "reason": reasons})
        else:
            filtered_jobs.append(job)

    # Inform about skipped jobs
    if unfeasible_jobs:
        print(f"⚠️ Skipping {len(unfeasible_jobs)} jobs due to resource constraints:")
        for item in unfeasible_jobs[:5]:  # Show first 5 to avoid flooding console
            print(f"- Job {item['job_id']}: {', '.join(item['reason'])}")
        if len(unfeasible_jobs) > 5:
            print(f"... and {len(unfeasible_jobs)-5} more")
        save_unscheduled_jobs(unfeasible_jobs, "milp")

    jobs_data = filtered_jobs  # Only use feasible jobs!

    # Handle empty job list after filtering
    if not jobs_data:
        print("❌ No feasible jobs remain after pre-checks. Optimization not attempted.")
        save_optimized_schedule([], "MILP")
        return []

    print(f"\nProceeding with {len(jobs_data)} feasible jobs out of {len(jobs_data)+len(unfeasible_jobs)} total")

    # Initialize model
    model = cp_model.CpModel()
    total_minutes = int((t_end - t_start).total_seconds() / 60)
    working_windows = generate_working_windows(t_start, t_end)

    print(f"\nTime parameters:")
    print(f"- Start: {t_start}")
    print(f"- End: {t_end}")
    print(f"- Total minutes: {total_minutes}")
    print(f"- Working windows: {working_windows}")

    # ==== CREATE VARIABLES AND CONSTRAINTS ====
    print("\nCreating variables and constraints...")

    # Job variables
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
    print("\nAdding equipment constraints...")
    for equip in equipment_data:
        equip_id = equip['equipment_id']
        equip_jobs = [j for j in jobs_data if j['equipment_id'] == equip_id]
        if equip_jobs:
            intervals = [
                model.NewIntervalVar(
                    job_vars[j['job_id']][0], 
                    j['duration'] * 60, 
                    job_vars[j['job_id']][1], 
                    f'interval_{j["job_id"]}'
                ) for j in equip_jobs
            ]
            model.AddNoOverlap(intervals)
            print(f"- Equipment {equip_id}: {len(equip_jobs)} jobs")

    # Technician constraints
    print("\nAdding technician constraints...")
    tech_assignment_vars = {}
    for tech in technicians_data:
        tech_id = tech['tech_id']
        tech_assignment_vars[tech_id] = {}
        tech_intervals = []
        
        for job in jobs_data:
            job_id = job['job_id']
            if set(tech['skills']).intersection(set(job['required_skills'])):
                is_assigned = model.NewBoolVar(f'tech_{tech_id}_assigned_to_{job_id}')
                tech_assignment_vars[tech_id][job_id] = is_assigned
                
                interval = model.NewOptionalIntervalVar(
                    job_vars[job_id][0],
                    int(job['duration'] * 60),
                    job_vars[job_id][1],
                    is_assigned,
                    f'tech_{tech_id}_interval_{job_id}'
                )
                tech_intervals.append(interval)
        
        if tech_intervals:
            model.AddNoOverlap(tech_intervals)
            print(f"- Technician {tech_id}: can work on {len(tech_intervals)} jobs")

    # Ensure each job has at least one technician with required skills
    print("\nAdding technician assignment constraints...")
    for job in jobs_data:
        job_id = job['job_id']
        tech_count = [
            tech_assignment_vars[tech['tech_id']][job_id]
            for tech in technicians_data
            if job_id in tech_assignment_vars[tech['tech_id']]
        ]
        if tech_count:
            model.Add(sum(tech_count) >= 1)  # At least one technician per job
        else:
            print(f"⚠️ Job {job_id} has no eligible technicians - this shouldn't happen after pre-check")

    # Tool constraints
    print("\nAdding tool constraints...")
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
        
        if tool_usage:
            model.AddCumulative([u[0] for u in tool_usage], [u[1] for u in tool_usage], tool_capacity)
            print(f"- Tool {tool_id}: {len(tool_usage)} usages (capacity {tool_capacity})")

    # Material constraints
    print("\nAdding material constraints...")
    for material in materials_data:
        material_id = material['material_id']
        material_capacity = material['quantity']
        material_usage = 0
        
        for job in jobs_data:
            for req_material in job['required_materials']:
                if req_material['material_id'] == material_id:
                    material_usage += req_material['quantity']
        
        model.Add(material_usage <= material_capacity)
        print(f"- Material {material_id}: usage {material_usage} (capacity {material_capacity})")

    # Precedence constraints
    print("\nAdding precedence constraints...")
    precedence_count = 0
    for job in jobs_data:
        for pred_id in job['precedence']:
            if pred_id in job_vars:  # Only add if predecessor exists
                model.Add(job_vars[job['job_id']][0] >= job_vars[pred_id][1])
                precedence_count += 1
    print(f"- Added {precedence_count} precedence constraints")

    # Objective: Minimize makespan
    makespan = model.NewIntVar(0, total_minutes, 'makespan')
    model.AddMaxEquality(makespan, [end for _, end in job_vars.values()])
    model.Minimize(makespan)

    # ==== SOLVE THE PROBLEM ====
    print("\nSolving the problem...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300.0  # 5 minutes limit
    solver.parameters.num_search_workers = 8  # Use multiple cores
    solver.parameters.log_search_progress = True
    
    status = solver.Solve(model)

    # ==== INTERPRET RESULTS ====
    optimized_schedule = []
    if status == cp_model.OPTIMAL:
        print("\n✅ Optimal solution found!")
    elif status == cp_model.FEASIBLE:
        print("\n⚠️ Feasible solution found (not necessarily optimal)")
    else:
        print("\n❌ No solution found")
        print("Possible reasons:")
        print("- Not enough technicians for the required skills")
        print("- Resource constraints are too tight")
        print("- Time limit was too short")
        print(f"Solver status: {status}")
        return []

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("\nSolution statistics:")
        print(f"- Makespan: {solver.Value(makespan)} minutes ({solver.Value(makespan)/60:.2f} hours)")
        print(f"- Objective value: {solver.ObjectiveValue()}")
        print(f"- Wall time: {solver.WallTime():.2f} seconds")
        
        # Build the optimized schedule
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

        save_optimized_schedule(optimized_schedule, "MILP")
        
        # Print scheduling statistics
        scheduled_job_ids = [job['job_id'] for job in optimized_schedule]
        unscheduled_ids = [item['job_id'] for item in unfeasible_jobs]
        
        print("\n=== Scheduling Statistics ===")
        print(f"Total jobs: {len(jobs_data)+len(unfeasible_jobs)}")
        print(f"Scheduled jobs: {len(scheduled_job_ids)}")
        print(f"Unscheduled jobs: {len(unscheduled_ids)}")
        print(f"Scheduling rate: {len(scheduled_job_ids)/(len(jobs_data)+len(unfeasible_jobs))*100:.2f}%")
        
        return optimized_schedule
    else:
        print("\nNo solution found")
        return []

if __name__ == "__main__":
    optimize_schedule()