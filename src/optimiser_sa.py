import sys
import os
import json
import random
import datetime
from datetime import timedelta
from typing import List, Dict, Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.data_handler import load_and_validate_data

DATA_DIR = 'data'

# === Working Hours Constants ===
WORKDAY_START = datetime.time(8, 0)
WORKDAY_END = datetime.time(17, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Monday-Friday

def daily_work_hours():
    return (datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_END) -
            datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_START)).total_seconds() / 3600.0

def is_working_hour(dt: datetime.datetime) -> bool:
    return dt.weekday() in WORKDAYS and WORKDAY_START <= dt.time() < WORKDAY_END

def next_working_hour(dt: datetime.datetime) -> datetime.datetime:
    limit = dt + timedelta(days=30)
    while not is_working_hour(dt):
        dt += timedelta(hours=1)
        if dt > limit:
            raise ValueError("Exceeded safe bounds searching for working hour")
    return dt

def save_optimized_schedule(schedule, optimizer_name):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f'optimized_schedule_{optimizer_name.lower()}.json'
    with open(filepath := os.path.join(DATA_DIR, filename), 'w') as f:
        json.dump(schedule, f, indent=4, default=str)
    print(f"\n✅ Optimized schedule saved to {filepath}")

def save_unscheduled_jobs(jobs, optimizer_name):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f'unscheduled_jobs_{optimizer_name.lower()}.json'
    with open(filepath := os.path.join(DATA_DIR, filename), 'w') as f:
        json.dump(jobs, f, indent=4)
    print(f"📄 Unscheduled jobs saved to {filepath}")

# === Core Functions ===

def generate_initial_solution(jobs, techs, t_start, t_end):
    schedule = []
    for job in jobs:
        max_tries = 100
        for _ in range(max_tries):
            try:
                start = next_working_hour(
                    t_start + timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600)))
                )
                end = start + timedelta(hours=job['duration'])
                if end <= t_end and is_working_hour(end - timedelta(minutes=1)):
                    break
            except Exception as e:
                print(f"⚠️ Could not find working slot for job {job['job_id']}: {e}")
                start = t_start
                end = start + timedelta(hours=job['duration'])

        available_techs = [tech for tech in techs if set(job['required_skills']).issubset(set(tech['skills']))]
        assigned = random.sample(available_techs, min(2, len(available_techs))) if available_techs else []
        schedule.append({
            'job_id': job['job_id'],
            'equipment_id': job['equipment_id'],
            'scheduled_start_time': start,
            'scheduled_end_time': end,
            'assigned_technicians': [tech['tech_id'] for tech in assigned]
        })
    return schedule

def evaluate(schedule, jobs, equip, techs, tools, mats, t_start, t_end):
    penalty = 0
    equip_usage = {e['equipment_id']: [] for e in equip}
    tech_usage = {t['tech_id']: [] for t in techs}
    tool_count = {tool['tool_id']: 0 for tool in tools}
    material_count = {mat['material_id']: 0 for mat in mats}

    for job in schedule:
        start, end = job['scheduled_start_time'], job['scheduled_end_time']
        if start < t_start or end > t_end:
            penalty += 1000

        cur = start
        while cur < end:
            if not is_working_hour(cur):
                penalty += 10
            cur += timedelta(hours=1)

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
        return any(intervals[i][1] > intervals[i+1][0] for i in range(len(intervals)-1))

    if any(check_overlap(u) for u in equip_usage.values()):
        penalty += 100
    if any(check_overlap(u) for u in tech_usage.values()):
        penalty += 100

    for tool in tools:
        if tool_count[tool['tool_id']] > tool['quantity']:
            penalty += 50 * (tool_count[tool['tool_id']] - tool['quantity'])
    for mat in mats:
        if material_count[mat['material_id']] > mat['quantity']:
            penalty += 50 * (material_count[mat['material_id']] - mat['quantity'])

    makespan = (max(job['scheduled_end_time'] for job in schedule) -
                min(job['scheduled_start_time'] for job in schedule)).total_seconds() / 3600
    return makespan + penalty

def perturb(schedule, t_start, t_end, jobs, techs):
    new_schedule = [dict(j) for j in schedule]
    i = random.randint(0, len(new_schedule) - 1)
    job_data = next(j for j in jobs if j['job_id'] == new_schedule[i]['job_id'])
    max_tries = 100
    for _ in range(max_tries):
        try:
            start = next_working_hour(
                t_start + timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600)))
            )
            end = start + timedelta(hours=job_data['duration'])
            if end <= t_end and is_working_hour(end - timedelta(minutes=1)):
                break
        except Exception:
            start = t_start
            end = t_start + timedelta(hours=job_data['duration'])
    new_schedule[i]['scheduled_start_time'] = start
    new_schedule[i]['scheduled_end_time'] = end
    return new_schedule

# === Main Optimizer ===
def optimize_schedule():
    print("Loading and validating all data...")
    data = load_and_validate_data()
    jobs, techs, equip, tools, mats = data['jobs'], data['technicians'], data['equipment'], data['tools'], data['materials']
    t_start = datetime.datetime.strptime(data.get('t_start', '2025-07-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
    t_end = datetime.datetime.strptime(data.get('t_end', '2025-07-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

    daily_hours = daily_work_hours()
    unscheduled, feasible_jobs = [], []

    for job in jobs:
        reasons = []
        # Resource checks
        for req in job['required_tools']:
            if req['quantity'] > next((t['quantity'] for t in tools if t['tool_id'] == req['tool_id']), 0):
                reasons.append(f"Needs {req['quantity']} of tool {req['tool_id']} (not enough).")
        for req in job['required_materials']:
            if req['quantity'] > next((m['quantity'] for m in mats if m['material_id'] == req['material_id']), 0):
                reasons.append(f"Needs {req['quantity']} of material {req['material_id']} (not enough).")
        if not any(set(job['required_skills']).issubset(set(t['skills'])) for t in techs):
            reasons.append("No matching technicians.")
        # Working hours check
        if job['duration'] > daily_hours:
            reasons.append(f"Duration {job['duration']}h exceeds workday length {int(daily_hours)}h.")

        if reasons:
            unscheduled.append({"job_id": job['job_id'], "reason": reasons})
        else:
            feasible_jobs.append(job)

    if unscheduled:
        save_unscheduled_jobs(unscheduled, "sa")

    if not feasible_jobs:
        save_optimized_schedule([], 'SA')
        print("❌ No feasible jobs remain after pre-checks.")
        return []

    print("Starting Simulated Annealing optimization...")
    current = generate_initial_solution(feasible_jobs, techs, t_start, t_end)
    best = current
    T, T_min, alpha = 100.0, 1e-2, 0.95
    current_score = evaluate(current, feasible_jobs, equip, techs, tools, mats, t_start, t_end)
    best_score = current_score

    iteration = 0
    while T > T_min:
        for _ in range(50):
            iteration += 1
            candidate = perturb(current, t_start, t_end, feasible_jobs, techs)
            cand_score = evaluate(candidate, feasible_jobs, equip, techs, tools, mats, t_start, t_end)
            if cand_score < current_score or random.random() < pow(2.718, (current_score - cand_score) / T):
                current, current_score = candidate, cand_score
                if current_score < best_score:
                    best, best_score = current, current_score
                    print(f"New best score at iteration {iteration}: {best_score:.2f}")
        T *= alpha

    for job in best:
        job['scheduled_start_time'] = job['scheduled_start_time'].strftime('%Y-%m-%dT%H:%M:%S')
        job['scheduled_end_time'] = job['scheduled_end_time'].strftime('%Y-%m-%dT%H:%M:%S')

    save_optimized_schedule(best, 'SA')
    return best

if __name__ == "__main__":
    optimize_schedule()
