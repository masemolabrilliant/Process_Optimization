import sys, os, random, datetime, json
from typing import List, Dict, Any, Tuple
import numpy as np

# Add the project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.data_handler import load_and_validate_data
# from src.email_sender import notify_technicians

DATA_DIR = 'data'

POPULATION_SIZE = 100
GENERATIONS = 100
MUTATION_RATE = 0.1
CROSSOVER_RATE = 0.8

# ===== Working hours (single-day, no splitting) =====
WORKDAY_START = datetime.time(8, 0)
WORKDAY_END   = datetime.time(17, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Monday–Friday

def save_optimized_schedule(schedule, optimizer_name):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f'optimized_schedule_{optimizer_name.lower()}.json'
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(schedule, f, indent=4, default=str)
    print(f"\n✅ Optimized schedule saved to {filepath}")

def daily_work_hours() -> float:
    return (
        datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_END)
        - datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_START)
    ).total_seconds() / 3600.0

# ===== GA Implementation =====

class GeneticAlgorithm:
    def __init__(self, jobs, techs, equip, tools, mats, t_start, t_end):
        self.jobs = jobs
        self.technicians = techs
        self.equipment = equip
        self.tools = tools
        self.materials = mats
        self.t_start = t_start
        self.t_end = t_end

    def is_working_hour(self, dt: datetime.datetime) -> bool:
        return dt.weekday() in WORKDAYS and WORKDAY_START <= dt.time() < WORKDAY_END

    def next_working_hour(self, dt: datetime.datetime) -> datetime.datetime:
        while not self.is_working_hour(dt):
            dt += datetime.timedelta(hours=1)
            if dt.time() < WORKDAY_START:
                dt = dt.replace(hour=WORKDAY_START.hour, minute=WORKDAY_START.minute)
            elif dt.time() >= WORKDAY_END:
                dt += datetime.timedelta(days=1)
                dt = dt.replace(hour=WORKDAY_START.hour, minute=WORKDAY_START.minute)
        return dt

    def generate_individual(self) -> List[Dict[str, Any]]:
        schedule = []
        for job in self.jobs:
            start_time = self.next_working_hour(
                self.t_start + datetime.timedelta(minutes=random.randint(0, int((self.t_end - self.t_start).total_seconds() / 60)))
            )
            end_time = start_time + datetime.timedelta(hours=float(job['duration']))

            # Keep sliding until the job fits fully inside a workday and global window
            while not self.is_working_hour(end_time - datetime.timedelta(minutes=1)) or end_time > self.t_end:
                start_time = self.next_working_hour(start_time + datetime.timedelta(hours=1))
                end_time = start_time + datetime.timedelta(hours=float(job['duration']))
                if start_time >= self.t_end:
                    # fallback: place at earliest working hour possible
                    start_time = self.next_working_hour(self.t_start)
                    end_time = start_time + datetime.timedelta(hours=float(job['duration']))

            eligible = [t for t in self.technicians if set(job.get('required_skills', [])) <= set(t.get('skills', []))]
            assigned = random.sample(eligible, min(len(eligible), 2)) if eligible else []
            schedule.append({
                'job_id': job['job_id'],
                'equipment_id': job['equipment_id'],
                'scheduled_start_time': start_time,
                'scheduled_end_time': end_time,
                'assigned_technicians': [t['tech_id'] for t in assigned]
            })
        return schedule

    def fitness(self, individual: List[Dict[str, Any]]) -> float:
        total_violation = 0
        equipment_usage = {e['equipment_id']: [] for e in self.equipment}
        technician_usage = {t['tech_id']: [] for t in self.technicians}
        tool_usage = {tool['tool_id']: 0 for tool in self.tools}
        material_usage = {m['material_id']: 0 for m in self.materials}

        for job in individual:
            s, e = job['scheduled_start_time'], job['scheduled_end_time']
            if s < self.t_start or e > self.t_end:
                total_violation += 1000

            cur = s
            while cur < e:
                if not self.is_working_hour(cur):
                    total_violation += 1
                cur += datetime.timedelta(hours=1)

            equipment_usage[job['equipment_id']].append((s, e))
            for tech_id in job['assigned_technicians']:
                technician_usage[tech_id].append((s, e))

            job_data = next(j for j in self.jobs if j['job_id'] == job['job_id'])
            for req in job_data.get('required_tools', []):
                tool_usage[req['tool_id']] += int(req['quantity'])
            for req in job_data.get('required_materials', []):
                material_usage[req['material_id']] += int(req['quantity'])

        # Overlaps
        def has_overlap(arr):
            arr.sort(key=lambda x: x[0])
            return any(arr[i][1] > arr[i+1][0] for i in range(len(arr)-1))

        for lst in list(equipment_usage.values()) + list(technician_usage.values()):
            if has_overlap(lst):
                total_violation += 1

        # resource caps
        for tool in self.tools:
            if tool_usage[tool['tool_id']] > int(tool['quantity']):
                total_violation += tool_usage[tool['tool_id']] - int(tool['quantity'])
        for mat in self.materials:
            if material_usage[mat['material_id']] > int(mat['quantity']):
                total_violation += material_usage[mat['material_id']] - int(mat['quantity'])

        makespan = max(j['scheduled_end_time'] for j in individual) - min(j['scheduled_start_time'] for j in individual)
        # Higher fitness is better
        return 1.0 / (makespan.total_seconds() / 3600.0 + total_violation * 100.0)

    def crossover(self, p1, p2):
        if random.random() > CROSSOVER_RATE:
            return p1, p2
        cut = random.randint(1, len(p1) - 1)
        return p1[:cut] + p2[cut:], p2[:cut] + p1[cut:]

    def mutate(self, individual):
        for i in range(len(individual)):
            if random.random() < MUTATION_RATE:
                job_sched = individual[i]
                job_data = next(j for j in self.jobs if j['job_id'] == job_sched['job_id'])
                dur = float(job_data['duration'])
                shift = datetime.timedelta(hours=random.randint(-12, 12))
                new_start = self.next_working_hour(job_sched['scheduled_start_time'] + shift)
                new_end = new_start + datetime.timedelta(hours=dur)
                while not self.is_working_hour(new_end - datetime.timedelta(minutes=1)) or new_end > self.t_end:
                    new_start = self.next_working_hour(new_start + datetime.timedelta(hours=1))
                    new_end = new_start + datetime.timedelta(hours=dur)
                    if new_start >= self.t_end:
                        new_start = self.next_working_hour(self.t_start)
                        new_end = new_start + datetime.timedelta(hours=dur)
                job_sched['scheduled_start_time'] = new_start
                job_sched['scheduled_end_time'] = new_end

                eligible = [t for t in self.technicians if set(job_data.get('required_skills', [])) <= set(t.get('skills', []))]
                job_sched['assigned_technicians'] = [t['tech_id'] for t in random.sample(eligible, min(2, len(eligible)))] if eligible else []
        return individual

    def select_parents(self, population):
        k = 5
        t1, t2 = random.sample(population, k), random.sample(population, k)
        return max(t1, key=self.fitness), max(t2, key=self.fitness)

    def optimize(self):
        population = [self.generate_individual() for _ in range(POPULATION_SIZE)]
        for g in range(GENERATIONS):
            new_pop = []
            for _ in range(POPULATION_SIZE // 2):
                p1, p2 = self.select_parents(population)
                c1, c2 = self.crossover(p1, p2)
                new_pop.extend([self.mutate(c1), self.mutate(c2)])
            population = new_pop
            best = max(population, key=self.fitness)
            print(f"Generation {g + 1}: Best Fitness = {self.fitness(best)}")
        return max(population, key=self.fitness)

def optimize_schedule():
    data = load_and_validate_data()
    jobs = data['jobs']
    techs = data['technicians']
    equip = data['equipment']
    tools = data['tools']
    mats = data['materials']
    t_start = datetime.datetime.strptime(data.get('t_start', '2025-07-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
    t_end   = datetime.datetime.strptime(data.get('t_end',   '2025-07-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

    # ===== Precheck: resources, skills, and working-hours duration =====
    tool_caps = {tool['tool_id']: int(tool['quantity']) for tool in tools}
    mat_caps  = {m['material_id']: int(m['quantity']) for m in mats}
    day_len   = daily_work_hours()

    unscheduled = []
    feasible_jobs = []
    for job in jobs:
        reasons = []
        # tools
        for req in job.get('required_tools', []):
            avail = tool_caps.get(req['tool_id'], 0)
            if int(req['quantity']) > avail:
                reasons.append(f"Needs {req['quantity']} of tool {req['tool_id']}, only {avail} available.")
        # materials
        for req in job.get('required_materials', []):
            avail = mat_caps.get(req['material_id'], 0)
            if int(req['quantity']) > avail:
                reasons.append(f"Needs {req['quantity']} of material {req['material_id']}, only {avail} available.")
        # skills
        eligible = [t for t in techs if set(job.get('required_skills', [])) <= set(t.get('skills', []))]
        if not eligible:
            reasons.append("No matching technicians with required skills.")
        # working-hours duration (no split)
        dur = float(job.get('duration', 0))
        if dur > day_len:
            reasons.append(
                f"Duration {dur}h exceeds workday length {int(day_len)}h "
                f"({WORKDAY_START.strftime('%H:%M')}-{WORKDAY_END.strftime('%H:%M')})."
            )

        if reasons:
            unscheduled.append({"job_id": job["job_id"], "reason": reasons})
        else:
            feasible_jobs.append(job)

    if unscheduled:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "unscheduled_jobs_ga.json"), "w") as f:
            json.dump(unscheduled, f, indent=4)
        print("⚠️ Some jobs were moved to unscheduled due to constraints:")
        for item in unscheduled:
            print(f"   • {item['job_id']}: {', '.join(item['reason'])}")

    if not feasible_jobs:
        print("❌ No feasible jobs remain after pre-checks. Optimization not attempted.")
        save_optimized_schedule([], 'GA')
        return []

    # ===== Run GA on feasible jobs only =====
    ga = GeneticAlgorithm(feasible_jobs, techs, equip, tools, mats, t_start, t_end)
    best_schedule = ga.optimize()

    # Convert datetimes for JSON
    for j in best_schedule:
        j['scheduled_start_time'] = j['scheduled_start_time'].strftime('%Y-%m-%dT%H:%M:%S')
        j['scheduled_end_time']   = j['scheduled_end_time'].strftime('%Y-%m-%dT%H:%M:%S')

    save_optimized_schedule(best_schedule, "GA")

    # stats
    print("\n=== Scheduling Statistics (GA) ===")
    print(f"  - Total jobs:     {len(jobs)}")
    print(f"  - Scheduled jobs: {len(best_schedule)}")
    print(f"  - Unscheduled:    {len(unscheduled)}")
    if unscheduled:
        for u in unscheduled:
            print(f"    · {u['job_id']}: {', '.join(u['reason'])}")

    return best_schedule

if __name__ == "__main__":
    optimize_schedule()
