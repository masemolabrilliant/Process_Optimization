# import os
# import sys
# import json
# import random
# import datetime
# from copy import deepcopy
# from typing import List, Dict, Any

# # Set up project path
# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# sys.path.append(PROJECT_ROOT)

# from src.data_handler import load_and_validate_data

# DATA_DIR = 'data'

# WORKDAY_START = datetime.time(8, 0)
# WORKDAY_END = datetime.time(17, 0)
# WORKDAYS = {0, 1, 2, 3, 4}  # Monday to Friday

# def is_working_hour(dt: datetime.datetime) -> bool:
#     return dt.weekday() in WORKDAYS and WORKDAY_START <= dt.time() < WORKDAY_END

# def next_working_hour(dt: datetime.datetime) -> datetime.datetime:
#     limit = dt + datetime.timedelta(days=30)  # prevent infinite loop
#     while not is_working_hour(dt):
#         dt += datetime.timedelta(hours=1)
#         if dt > limit:
#             raise ValueError("Exceeded safe bounds searching for working hour")
#     return dt

# def save_optimized_schedule(schedule, optimizer_name):
#     try:
#         filename = f'optimized_schedule_{optimizer_name.lower()}.json'
#         filepath = os.path.join(DATA_DIR, filename)
#         with open(filepath, 'w') as f:
#             json.dump(schedule, f, indent=4)
#         print(f"\nOptimized schedule saved to {filepath}")
#     except Exception as e:
#         print(f"Error saving optimized schedule: {e}")

# def generate_initial_solution(jobs, technicians, t_start, t_end):
#     print("Generating initial solution...")
#     schedule = []
#     for job in jobs:
#         max_tries = 100
#         for _ in range(max_tries):
#             try:
#                 start = next_working_hour(t_start + datetime.timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600))))
#                 end = start + datetime.timedelta(hours=job['duration'])
#                 if end <= t_end and is_working_hour(end - datetime.timedelta(minutes=1)):
#                     break
#             except Exception as e:
#                 print(f"Warning: Failed finding slot for job {job['job_id']}: {e}")
#                 start = t_start
#                 end = t_start + datetime.timedelta(hours=job['duration'])
#         valid_techs = [tech['tech_id'] for tech in technicians if set(job['required_skills']).issubset(set(tech['skills']))]
#         assigned = random.sample(valid_techs, min(2, len(valid_techs))) if valid_techs else []
#         schedule.append({
#             'job_id': job['job_id'],
#             'equipment_id': job['equipment_id'],
#             'scheduled_start_time': start,
#             'scheduled_end_time': end,
#             'assigned_technicians': assigned
#         })
#     return schedule

# def evaluate(schedule, jobs, equipment, technicians, tools, materials, t_start, t_end):
#     penalty = 0
#     equip_usage = {e['equipment_id']: [] for e in equipment}
#     tech_usage = {t['tech_id']: [] for t in technicians}
#     tool_count = {tool['tool_id']: 0 for tool in tools}
#     material_count = {mat['material_id']: 0 for mat in materials}

#     for job in schedule:
#         start, end = job['scheduled_start_time'], job['scheduled_end_time']
#         if start < t_start or end > t_end:
#             penalty += 1000

#         cur = start
#         while cur < end:
#             if not is_working_hour(cur):
#                 penalty += 1
#             cur += datetime.timedelta(hours=1)

#         equip_usage[job['equipment_id']].append((start, end))
#         for tech in job['assigned_technicians']:
#             tech_usage[tech].append((start, end))

#         job_data = next(j for j in jobs if j['job_id'] == job['job_id'])
#         for tool in job_data['required_tools']:
#             tool_count[tool['tool_id']] += tool['quantity']
#         for mat in job_data['required_materials']:
#             material_count[mat['material_id']] += mat['quantity']

#     def check_overlap(intervals):
#         intervals.sort()
#         for i in range(len(intervals)-1):
#             if intervals[i][1] > intervals[i+1][0]:
#                 return True
#         return False

#     for usage in equip_usage.values():
#         if check_overlap(usage):
#             penalty += 100
#     for usage in tech_usage.values():
#         if check_overlap(usage):
#             penalty += 100

#     for tool in tools:
#         if tool_count[tool['tool_id']] > tool['quantity']:
#             penalty += 50 * (tool_count[tool['tool_id']] - tool['quantity'])
#     for mat in materials:
#         if material_count[mat['material_id']] > mat['quantity']:
#             penalty += 50 * (material_count[mat['material_id']] - mat['quantity'])

#     makespan = (max(job['scheduled_end_time'] for job in schedule) - min(job['scheduled_start_time'] for job in schedule)).total_seconds() / 3600
#     return makespan + penalty

# def perturb(schedule, t_start, t_end, jobs, technicians):
#     new_schedule = deepcopy(schedule)
#     i = random.randint(0, len(new_schedule) - 1)
#     job_data = next(j for j in jobs if j['job_id'] == new_schedule[i]['job_id'])
#     max_tries = 100
#     for _ in range(max_tries):
#         try:
#             start = next_working_hour(t_start + datetime.timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600))))
#             end = start + datetime.timedelta(hours=job_data['duration'])
#             if end <= t_end and is_working_hour(end - datetime.timedelta(minutes=1)):
#                 break
#         except Exception:
#             start = t_start
#             end = t_start + datetime.timedelta(hours=job_data['duration'])
#     new_schedule[i]['scheduled_start_time'] = start
#     new_schedule[i]['scheduled_end_time'] = end
#     return new_schedule

# def optimize_schedule():
#     try:
#         print("Loading data...")
#         data = load_and_validate_data()
#         jobs, techs, equip, tools, mats = data['jobs'], data['technicians'], data['equipment'], data['tools'], data['materials']
#         t_start = datetime.datetime.strptime(data.get('t_start', '2025-07-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
#         t_end = datetime.datetime.strptime(data.get('t_end', '2025-07-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

#         print("Starting Simulated Annealing optimization...")
#         current = generate_initial_solution(jobs, techs, t_start, t_end)
#         best = current
#         T, T_min, alpha = 100.0, 1e-2, 0.95
#         current_score = evaluate(current, jobs, equip, techs, tools, mats, t_start, t_end)
#         best_score = current_score
#         print(f"Initial solution score: {current_score:.2f}")

#         iteration = 0
#         while T > T_min:
#             print(f"\nTemperature: {T:.2f}")
#             for inner in range(50):
#                 iteration += 1
#                 candidate = perturb(current, t_start, t_end, jobs, techs)
#                 cand_score = evaluate(candidate, jobs, equip, techs, tools, mats, t_start, t_end)
#                 if cand_score < current_score or random.random() < pow(2.718, (current_score - cand_score) / T):
#                     current = candidate
#                     current_score = cand_score
#                     if current_score < best_score:
#                         best = current
#                         best_score = current_score
#                         print(f"New best score at iteration {iteration}: {best_score:.2f}")
#             T *= alpha

#         for job in best:
#             job['scheduled_start_time'] = job['scheduled_start_time'].strftime('%Y-%m-%dT%H:%M:%S')
#             job['scheduled_end_time'] = job['scheduled_end_time'].strftime('%Y-%m-%dT%H:%M:%S')
#         save_optimized_schedule(best, 'SA')
#         print("\nOptimization with Simulated Annealing completed.")
#         return best

#     except Exception as e:
#         print(f"Optimization failed: {e}")
#         return None

# if __name__ == "__main__":
#     optimize_schedule()

















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

def save_optimized_schedule(schedule, optimizer_name):
    filename = f'optimized_schedule_{optimizer_name.lower()}.json'
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(schedule, f, indent=4)
    print(f"\nOptimized schedule saved to {filepath}")

def generate_initial_solution(jobs, techs, t_start, t_end):
    # Very basic: assign jobs randomly, within time window, to available technicians
    schedule = []
    for job in jobs:
        job_start = t_start + timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600) - int(job['duration'])))
        job_end = job_start + timedelta(hours=job['duration'])
        available_techs = [tech for tech in techs if set(job['required_skills']).issubset(set(tech['skills']))]
        assigned_techs = random.sample(available_techs, min(len(available_techs), max(1, len(job['required_skills']))))
        schedule.append({
            "job_id": job['job_id'],
            "equipment_id": job['equipment_id'],
            "scheduled_start_time": job_start,
            "scheduled_end_time": job_end,
            "assigned_technicians": [tech['tech_id'] for tech in assigned_techs]
        })
    return schedule

def perturb(schedule, t_start, t_end, jobs, techs):
    # Randomly change one job's start time and/or assigned techs
    schedule = [dict(j) for j in schedule]
    idx = random.randint(0, len(schedule) - 1)
    job = jobs[idx]
    job_duration = job['duration']
    schedule[idx]['scheduled_start_time'] = t_start + timedelta(hours=random.randint(0, int((t_end - t_start).total_seconds() // 3600) - int(job_duration)))
    schedule[idx]['scheduled_end_time'] = schedule[idx]['scheduled_start_time'] + timedelta(hours=job_duration)
    available_techs = [tech for tech in techs if set(job['required_skills']).issubset(set(tech['skills']))]
    schedule[idx]['assigned_technicians'] = [tech['tech_id'] for tech in random.sample(available_techs, min(len(available_techs), max(1, len(job['required_skills']))))]
    return schedule

def evaluate(schedule, jobs, equip, techs, tools, mats, t_start, t_end):
    # Penalty for overlap, resource overuse, out-of-window
    penalty = 0
    # Track resource usage per time
    tool_caps = {tool['tool_id']: tool['quantity'] for tool in tools}
    mat_caps = {mat['material_id']: mat['quantity'] for mat in mats}
    tool_usage = {tid: [] for tid in tool_caps}
    mat_usage = {mid: [] for mid in mat_caps}
    equip_usage = {}
    tech_usage = {}
    for j, job in enumerate(jobs):
        js = schedule[j]['scheduled_start_time']
        je = schedule[j]['scheduled_end_time']
        # Tool usage per job
        for req in job['required_tools']:
            tool_usage[req['tool_id']].append((js, je, req['quantity']))
        for req in job['required_materials']:
            mat_usage[req['material_id']].append((js, je, req['quantity']))
        # Equipment overlap
        equip_id = job['equipment_id']
        if equip_id not in equip_usage: equip_usage[equip_id] = []
        equip_usage[equip_id].append((js, je))
        # Technician overlap
        for tech_id in schedule[j]['assigned_technicians']:
            if tech_id not in tech_usage: tech_usage[tech_id] = []
            tech_usage[tech_id].append((js, je))

        # Out of window
        if js < t_start or je > t_end:
            penalty += 1000
    # Penalize overlap for equip, techs
    for usage in list(equip_usage.values()) + list(tech_usage.values()):
        times = sorted(usage)
        for i in range(len(times) - 1):
            if times[i][1] > times[i+1][0]:
                penalty += 1000
    # Penalize overuse of tools/materials at any time
    for tu in tool_usage.values():
        times = []
        for s, e, q in tu:
            times.append((s, q))
            times.append((e, -q))
        times.sort()
        current = 0
        for t, delta in times:
            current += delta
            if current > tool_caps[list(tool_usage.keys())[0]]:
                penalty += 1000 * (current - tool_caps[list(tool_usage.keys())[0]])
    for mu in mat_usage.values():
        times = []
        for s, e, q in mu:
            times.append((s, q))
            times.append((e, -q))
        times.sort()
        current = 0
        for t, delta in times:
            current += delta
            if current > mat_caps[list(mat_usage.keys())[0]]:
                penalty += 1000 * (current - mat_caps[list(mat_usage.keys())[0]])
    # Makespan
    end_times = [s['scheduled_end_time'] for s in schedule]
    if end_times:
        makespan = max(end_times) - t_start
        penalty += makespan.total_seconds() / 3600
    return penalty

def optimize_schedule():
    try:
        print("Loading and validating all data...")
        data = load_and_validate_data()
        jobs, techs, equip, tools, mats = data['jobs'], data['technicians'], data['equipment'], data['tools'], data['materials']
        t_start = datetime.datetime.strptime(data.get('t_start', '2025-07-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
        t_end = datetime.datetime.strptime(data.get('t_end', '2025-07-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

        # === Pre-check jobs for feasibility
        tool_caps = {tool['tool_id']: tool['quantity'] for tool in tools}
        mat_caps = {mat['material_id']: mat['quantity'] for mat in mats}
        unscheduled = []
        feasible_jobs = []
        for job in jobs:
            reasons = []
            # Tools
            for req in job['required_tools']:
                avail = tool_caps.get(req['tool_id'], 0)
                if req['quantity'] > avail:
                    reasons.append(f"Needs {req['quantity']} of tool {req['tool_id']}, only {avail} available.")
            # Materials
            for req in job['required_materials']:
                avail = mat_caps.get(req['material_id'], 0)
                if req['quantity'] > avail:
                    reasons.append(f"Needs {req['quantity']} of material {req['material_id']}, only {avail} available.")
            # Skills
            valid_techs = [tech for tech in techs if set(job['required_skills']).issubset(set(tech['skills']))]
            if not valid_techs:
                reasons.append("No matching technicians with required skills.")
            if reasons:
                unscheduled.append({"job_id": job['job_id'], "reason": reasons})
            else:
                feasible_jobs.append(job)

        if unscheduled:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, "unscheduled_jobs_sa.json"), "w") as f:
                json.dump(unscheduled, f, indent=4)
            print("⚠️ The following jobs were removed due to impossible resource requirements or missing skills:")
            for item in unscheduled:
                print(f"- Job {item['job_id']}: {', '.join(item['reason'])}")

        if not feasible_jobs:
            print("No feasible jobs remain after pre-checks. Optimization not attempted.")
            save_optimized_schedule([], 'SA')
            return []

        print("Starting Simulated Annealing optimization...")
        current = generate_initial_solution(feasible_jobs, techs, t_start, t_end)
        best = current
        T, T_min, alpha = 100.0, 1e-2, 0.95
        current_score = evaluate(current, feasible_jobs, equip, techs, tools, mats, t_start, t_end)
        best_score = current_score
        print(f"Initial solution score: {current_score:.2f}")

        iteration = 0
        while T > T_min:
            print(f"\nTemperature: {T:.2f}")
            for inner in range(50):
                iteration += 1
                candidate = perturb(current, t_start, t_end, feasible_jobs, techs)
                cand_score = evaluate(candidate, feasible_jobs, equip, techs, tools, mats, t_start, t_end)
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

        scheduled_job_ids = [job['job_id'] for job in best]
        unscheduled_ids = [item['job_id'] for item in unscheduled]
        print("\n=== Scheduling Statistics ===")
        print(f"Total jobs: {len(jobs)}")
        print(f"Scheduled jobs: {len(scheduled_job_ids)}")
        print(f"Unscheduled jobs: {len(unscheduled_ids)}")
        if unscheduled_ids:
            print("Unscheduled jobs and reasons:")
            for item in unscheduled:
                print(f"- {item['job_id']}: {', '.join(item['reason'])}")
        if best:
            print(f"Scheduling rate: {len(scheduled_job_ids)/len(jobs)*100:.2f}%")
            print(f"Best score: {best_score:.2f}")

        print("\nOptimization with Simulated Annealing completed.")
        return best

    except Exception as e:
        print(f"Optimization failed: {e}")
        return None

if __name__ == "__main__":
    optimize_schedule()
