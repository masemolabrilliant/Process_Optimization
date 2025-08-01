import os
import sys
import json
import random
import datetime
from copy import deepcopy
from typing import List, Dict, Any

# Set up project path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.data_handler import load_and_validate_data

DATA_DIR = 'data'

WORKDAY_START = datetime.time(8, 0)
WORKDAY_END = datetime.time(17, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Monday to Friday

def is_working_hour(dt: datetime.datetime) -> bool:
    return dt.weekday() in WORKDAYS and WORKDAY_START <= dt.time() < WORKDAY_END

def next_working_hour(dt: datetime.datetime) -> datetime.datetime:
    limit = dt + datetime.timedelta(days=30)  # prevent infinite loop
    while not is_working_hour(dt):
        dt += datetime.timedelta(hours=1)
        if dt > limit:
            raise ValueError("Exceeded safe bounds searching for working hour")
    return dt

def save_optimized_schedule(schedule, optimizer_name):
    try:
        filename = f'optimized_schedule_{optimizer_name.lower()}.json'
        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, 'w') as f:
            json.dump(schedule, f, indent=4)
        print(f"\nOptimized schedule saved to {filepath}")
    except Exception as e:
        print(f"Error saving optimized schedule: {e}")

def generate_initial_solution(jobs, technicians, t_start, t_end):
    print("Generating initial solution...")
    schedule = []
    for job in jobs:
        max_tries = 100
        for _ in range(max_tries):
            try:
                start = next_working_hour(t_start + datetime.timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600))))
                end = start + datetime.timedelta(hours=job['duration'])
                if end <= t_end and is_working_hour(end - datetime.timedelta(minutes=1)):
                    break
            except Exception as e:
                print(f"Warning: Failed finding slot for job {job['job_id']}: {e}")
                start = t_start
                end = t_start + datetime.timedelta(hours=job['duration'])
        valid_techs = [tech['tech_id'] for tech in technicians if set(job['required_skills']).issubset(set(tech['skills']))]
        assigned = random.sample(valid_techs, min(2, len(valid_techs))) if valid_techs else []
        schedule.append({
            'job_id': job['job_id'],
            'equipment_id': job['equipment_id'],
            'scheduled_start_time': start,
            'scheduled_end_time': end,
            'assigned_technicians': assigned
        })
    return schedule

def evaluate(schedule, jobs, equipment, technicians, tools, materials, t_start, t_end):
    penalty = 0
    equip_usage = {e['equipment_id']: [] for e in equipment}
    tech_usage = {t['tech_id']: [] for t in technicians}
    tool_count = {tool['tool_id']: 0 for tool in tools}
    material_count = {mat['material_id']: 0 for mat in materials}

    for job in schedule:
        start, end = job['scheduled_start_time'], job['scheduled_end_time']
        if start < t_start or end > t_end:
            penalty += 1000

        cur = start
        while cur < end:
            if not is_working_hour(cur):
                penalty += 1
            cur += datetime.timedelta(hours=1)

        equip_usage[job['equipment_id']].append((start, end))
        for tech in job['assigned_technicians']:
            tech_usage[tech].append((start, end))

        job_data = next(j for j in jobs if j['job_id'] == job['job_id'])
        for tool in job_data['required_tools']:
            tool_count[tool['tool_id']] += tool['quantity']
        for mat in job_data['required_materials']:
            material_count[mat['material_id']] += mat['quantity']

    def check_overlap(intervals):
        intervals.sort()
        for i in range(len(intervals)-1):
            if intervals[i][1] > intervals[i+1][0]:
                return True
        return False

    for usage in equip_usage.values():
        if check_overlap(usage):
            penalty += 100
    for usage in tech_usage.values():
        if check_overlap(usage):
            penalty += 100

    for tool in tools:
        if tool_count[tool['tool_id']] > tool['quantity']:
            penalty += 50 * (tool_count[tool['tool_id']] - tool['quantity'])
    for mat in materials:
        if material_count[mat['material_id']] > mat['quantity']:
            penalty += 50 * (material_count[mat['material_id']] - mat['quantity'])

    makespan = (max(job['scheduled_end_time'] for job in schedule) - min(job['scheduled_start_time'] for job in schedule)).total_seconds() / 3600
    return makespan + penalty

def perturb(schedule, t_start, t_end, jobs, technicians):
    new_schedule = deepcopy(schedule)
    i = random.randint(0, len(new_schedule) - 1)
    job_data = next(j for j in jobs if j['job_id'] == new_schedule[i]['job_id'])
    max_tries = 100
    for _ in range(max_tries):
        try:
            start = next_working_hour(t_start + datetime.timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600))))
            end = start + datetime.timedelta(hours=job_data['duration'])
            if end <= t_end and is_working_hour(end - datetime.timedelta(minutes=1)):
                break
        except Exception:
            start = t_start
            end = t_start + datetime.timedelta(hours=job_data['duration'])
    new_schedule[i]['scheduled_start_time'] = start
    new_schedule[i]['scheduled_end_time'] = end
    return new_schedule

def optimize_schedule():
    try:
        print("Loading data...")
        data = load_and_validate_data()
        jobs, techs, equip, tools, mats = data['jobs'], data['technicians'], data['equipment'], data['tools'], data['materials']
        t_start = datetime.datetime.strptime(data.get('t_start', '2025-07-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
        t_end = datetime.datetime.strptime(data.get('t_end', '2025-07-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

        print("Starting Simulated Annealing optimization...")
        current = generate_initial_solution(jobs, techs, t_start, t_end)
        best = current
        T, T_min, alpha = 100.0, 1e-2, 0.95
        current_score = evaluate(current, jobs, equip, techs, tools, mats, t_start, t_end)
        best_score = current_score
        print(f"Initial solution score: {current_score:.2f}")

        iteration = 0
        while T > T_min:
            print(f"\nTemperature: {T:.2f}")
            for inner in range(50):
                iteration += 1
                candidate = perturb(current, t_start, t_end, jobs, techs)
                cand_score = evaluate(candidate, jobs, equip, techs, tools, mats, t_start, t_end)
                if cand_score < current_score or random.random() < pow(2.718, (current_score - cand_score) / T):
                    current = candidate
                    current_score = cand_score
                    if current_score < best_score:
                        best = current
                        best_score = current_score
                        print(f"New best score at iteration {iteration}: {best_score:.2f}")
            T *= alpha

        for job in best:
            job['scheduled_start_time'] = job['scheduled_start_time'].strftime('%Y-%m-%dT%H:%M:%S')
            job['scheduled_end_time'] = job['scheduled_end_time'].strftime('%Y-%m-%dT%H:%M:%S')
        save_optimized_schedule(best, 'SA')
        print("\nOptimization with Simulated Annealing completed.")
        return best

    except Exception as e:
        print(f"Optimization failed: {e}")
        return None

if __name__ == "__main__":
    optimize_schedule()
