# src/optimiser_ortools.py

import sys
import os
import json
import datetime
from datetime import timedelta
from ortools.sat.python import cp_model
from typing import Any, List, Dict, Tuple

# Add the root directory to the system path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.data_handler import load_and_validate_data

DATA_DIR = 'data'
WORKDAY_START = datetime.time(8, 0)
WORKDAY_END   = datetime.time(17, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Mon–Fri


def _datetime_to_minutes(dt: datetime.datetime, t0: datetime.datetime) -> int:
    return int((dt - t0).total_seconds() // 60)


def _minutes_to_datetime(minutes: int, t0: datetime.datetime) -> datetime.datetime:
    return t0 + timedelta(minutes=minutes)


def _generate_working_windows(t_start: datetime.datetime, t_end: datetime.datetime) -> List[Tuple[int, int]]:
    """Return [(start_min, end_min), ...] windows that reflect working hours & days."""
    current = t_start
    windows: List[Tuple[int, int]] = []
    while current < t_end:
        if current.weekday() in WORKDAYS:
            day_start = datetime.datetime.combine(current.date(), WORKDAY_START)
            day_end   = datetime.datetime.combine(current.date(), WORKDAY_END)
            # Clip to global window
            if day_start < t_start:
                day_start = t_start
            if day_end > t_end:
                day_end = t_end
            if day_start < day_end:
                windows.append((_datetime_to_minutes(day_start, t_start),
                                _datetime_to_minutes(day_end,   t_start)))
        current += timedelta(days=1)
    return windows


def _save_optimized_schedule(schedule: List[Dict[str, Any]], optimizer_name: str = "OR-Tools") -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, f'optimized_schedule_{optimizer_name.lower()}.json')
    with open(filepath, 'w') as f:
        json.dump(schedule, f, indent=4, default=str)
    print(f"\n✅ Optimized schedule saved to {filepath}")


def _save_unscheduled_jobs(jobs: List[Dict[str, Any]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "unscheduled_jobs_ortools.json")
    with open(filepath, 'w') as f:
        json.dump(jobs, f, indent=4)
    print(f"📄 Unscheduled jobs saved to {filepath}")


def optimize_schedule() -> List[Dict[str, Any]]:
    print("\n=== OR-Tools Optimization Starting ===")
    print("Loading and validating all data...")

    data = load_and_validate_data()
    jobs_data        = data['jobs']
    technicians_data = data['technicians']
    tools_data       = data['tools']
    materials_data   = data['materials']
    equipment_data   = data['equipment']

    # Global scheduling horizon
    t_start = datetime.datetime.strptime(data.get('t_start', '2023-12-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
    t_end   = datetime.datetime.strptime(data.get('t_end',   '2023-12-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

    # ======== PRECHECK: filter unfeasible jobs (tools, materials, skills, and NEW: duration>day) ========
    print("\nValidating job feasibility...")

    # capacities
    tool_caps = {tool["tool_id"]: tool["quantity"] for tool in tools_data}
    material_caps = {mat["material_id"]: mat["quantity"] for mat in materials_data}

    # compute single-day work span (hours)
    daily_hours = (
        datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_END) -
        datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_START)
    ).total_seconds() / 3600.0

    unfeasible_jobs: List[Dict[str, Any]] = []
    filtered_jobs:  List[Dict[str, Any]] = []

    for job in jobs_data:
        reasons: List[str] = []

        # Tools
        for req in job.get("required_tools", []):
            avail = tool_caps.get(req["tool_id"], 0)
            if req["quantity"] > avail:
                reasons.append(f"Needs {req['quantity']} of tool {req['tool_id']}, only {avail} available.")

        # Materials (total stock style — if your logic is per-time, this stays as a coarse precheck)
        for req in job.get("required_materials", []):
            avail = material_caps.get(req["material_id"], 0)
            if req["quantity"] > avail:
                reasons.append(f"Needs {req['quantity']} of material {req['material_id']}, only {avail} available.")

        # Skills (at least one tech shares a required skill)
        required_skills = set(job.get('required_skills', []))
        matching_techs = [
            tech for tech in technicians_data
            if required_skills & set(tech.get('skills', []))
        ]
        if not matching_techs:
            reasons.append("No matching technicians with required skills.")

        # NEW: Duration vs single-day work window (NO SPLIT)
        dur = float(job.get("duration", 0))
        if dur > daily_hours:
            reasons.append(
                f"Duration {dur}h exceeds workday length {int(daily_hours)}h "
                f"({WORKDAY_START.strftime('%H:%M')}-{WORKDAY_END.strftime('%H:%M')})."
            )

        if reasons:
            unfeasible_jobs.append({"job_id": job["job_id"], "reason": reasons})
        else:
            filtered_jobs.append(job)

    # Log and save unfeasible
    if unfeasible_jobs:
        print(f"⚠️  Skipping {len(unfeasible_jobs)} job(s) due to constraints:")
        for item in unfeasible_jobs:
            print(f"   • {item['job_id']}: {', '.join(item['reason'])}")
        _save_unscheduled_jobs(unfeasible_jobs)

    # If nothing feasible, exit nicely
    if not filtered_jobs:
        print("❌ No feasible jobs remain after pre-checks. Optimization will not run.")
        _save_optimized_schedule([], "OR-Tools")
        return []

    print(f"\nProceeding with {len(filtered_jobs)} feasible job(s) "
          f"out of {len(filtered_jobs) + len(unfeasible_jobs)} total.")

    # ======== BUILD CP-SAT MODEL ========
    model = cp_model.CpModel()
    total_minutes = int((t_end - t_start).total_seconds() // 60)
    working_windows = _generate_working_windows(t_start, t_end)

    print("\nTime parameters:")
    print(f"  - Start: {t_start}")
    print(f"  - End:   {t_end}")
    print(f"  - Total minutes: {total_minutes}")
    print(f"  - Working windows (mins from t_start): {working_windows}")

    # Job time vars
    job_vars: Dict[str, Tuple[cp_model.IntVar, cp_model.IntVar]] = {}
    for job in filtered_jobs:
        job_id = job['job_id']
        duration_min = int(float(job['duration']) * 60)

        start = model.NewIntVar(0, total_minutes, f'start_{job_id}')
        end   = model.NewIntVar(0, total_minutes, f'end_{job_id}')
        model.Add(end - start == duration_min)

        # Force job to fit ENTIRELY within at least one working window (no splitting)
        in_any_window = []
        for w_start, w_end in working_windows:
            in_w = model.NewBoolVar(f'{job_id}_in_window_{w_start}_{w_end}')
            model.Add(start >= w_start).OnlyEnforceIf(in_w)
            model.Add(end   <= w_end  ).OnlyEnforceIf(in_w)
            in_any_window.append(in_w)
        model.Add(sum(in_any_window) >= 1)

        job_vars[job_id] = (start, end)

    # Equipment NoOverlap
    print("\nAdding equipment constraints...")
    for equip in equipment_data:
        equip_id = equip['equipment_id']
        equip_jobs = [j for j in filtered_jobs if j['equipment_id'] == equip_id]
        if not equip_jobs:
            continue
        intervals = [
            model.NewIntervalVar(
                job_vars[j['job_id']][0],
                int(float(j['duration']) * 60),
                job_vars[j['job_id']][1],
                f'interval_{j["job_id"]}'
            )
            for j in equip_jobs
        ]
        model.AddNoOverlap(intervals)
        print(f"  - Equipment {equip_id}: {len(equip_jobs)} job(s)")

    # Technician optional intervals & NoOverlap per tech
    print("\nAdding technician constraints...")
    tech_assignment: Dict[str, Dict[str, cp_model.BoolVar]] = {}
    for tech in technicians_data:
        tech_id = tech['tech_id']
        tech_assignment[tech_id] = {}
        tech_intervals = []

        for job in filtered_jobs:
            job_id = job['job_id']
            # eligible if intersection of skills is non-empty
            if set(tech.get('skills', [])) & set(job.get('required_skills', [])):
                assigned = model.NewBoolVar(f'tech_{tech_id}_assigned_to_{job_id}')
                tech_assignment[tech_id][job_id] = assigned
                interval = model.NewOptionalIntervalVar(
                    job_vars[job_id][0],
                    int(float(job['duration']) * 60),
                    job_vars[job_id][1],
                    assigned,
                    f'tech_{tech_id}_interval_{job_id}'
                )
                tech_intervals.append(interval)

        if tech_intervals:
            model.AddNoOverlap(tech_intervals)
            print(f"  - Technician {tech_id}: can cover {len(tech_intervals)} potential job(s)")

    # Each job must have at least one eligible technician assigned
    print("\nAdding technician assignment constraints (>=1 per job)...")
    for job in filtered_jobs:
        job_id = job['job_id']
        candidates = [
            tech_assignment[tech['tech_id']][job_id]
            for tech in technicians_data
            if job_id in tech_assignment.get(tech['tech_id'], {})
        ]
        if candidates:
            model.Add(sum(candidates) >= 1)
        else:
            # Should not happen due to precheck, but guard anyway
            print(f"  ⚠️ Job {job_id} unexpectedly has no eligible technicians in model.")

    # Tool capacity via cumulative
    print("\nAdding tool capacity constraints...")
    for tool in tools_data:
        tool_id = tool['tool_id']
        cap = int(tool['quantity'])
        uses_intervals = []
        demands = []
        for job in filtered_jobs:
            for req in job.get('required_tools', []):
                if req['tool_id'] == tool_id:
                    uses_intervals.append(
                        model.NewIntervalVar(
                            job_vars[job['job_id']][0],
                            int(float(job['duration']) * 60),
                            job_vars[job['job_id']][1],
                            f'tool_{tool_id}_interval_{job["job_id"]}'
                        )
                    )
                    demands.append(int(req['quantity']))
        if uses_intervals:
            model.AddCumulative(uses_intervals, demands, cap)
            print(f"  - Tool {tool_id}: {len(uses_intervals)} use(s), cap {cap}")

    # Material stock (simple total usage ≤ stock)
    print("\nAdding material stock constraints...")
    for material in materials_data:
        material_id = material['material_id']
        cap = int(material['quantity'])
        total_use = 0
        for job in filtered_jobs:
            for req in job.get('required_materials', []):
                if req['material_id'] == material_id:
                    total_use += int(req['quantity'])
        model.Add(total_use <= cap)
        print(f"  - Material {material_id}: usage {total_use} / cap {cap}")

    # Precedence: job must start after predecessor ends (only if predecessor survives filtering)
    print("\nAdding precedence constraints...")
    count_prec = 0
    for job in filtered_jobs:
        for pred in job.get('precedence', []):
            if pred in job_vars:  # only add if predecessor is in the model
                model.Add(job_vars[job['job_id']][0] >= job_vars[pred][1])
                count_prec += 1
    print(f"  - Added {count_prec} precedence relation(s)")

    # Objective: minimize makespan
    makespan = model.NewIntVar(0, total_minutes, 'makespan')
    model.AddMaxEquality(makespan, [end for (_, end) in job_vars.values()])
    model.Minimize(makespan)

    # ======== SOLVE ========
    print("\nSolving...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300.0  # 5 minutes
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True

    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("\n❌ No solution found.")
        print("   Possible reasons:")
        print("   - Not enough technicians for the required skills")
        print("   - Resource constraints too tight")
        print("   - Time limit too short")
        return []

    print("\n✅ Solution found!" if status == cp_model.OPTIMAL else "\n⚠️ Feasible solution found (not necessarily optimal)")
    print(f"  - Makespan: {solver.Value(makespan)} minutes ({solver.Value(makespan)/60:.2f} hours)")
    print(f"  - Objective value: {solver.ObjectiveValue()}")
    print(f"  - Wall time: {solver.WallTime():.2f} seconds")

    # Build schedule result
    optimized_schedule: List[Dict[str, Any]] = []
    for job in filtered_jobs:
        job_id = job['job_id']
        start_dt = _minutes_to_datetime(solver.Value(job_vars[job_id][0]), t_start)
        end_dt   = _minutes_to_datetime(solver.Value(job_vars[job_id][1]), t_start)

        assigned_techs = [
            tech['tech_id'] for tech in technicians_data
            if (job_id in tech_assignment.get(tech['tech_id'], {})) and
               (solver.Value(tech_assignment[tech['tech_id']][job_id]) == 1)
        ]

        optimized_schedule.append({
            'job_id': job_id,
            'equipment_id': job['equipment_id'],
            'scheduled_start_time': start_dt.strftime('%Y-%m-%dT%H:%M:%S'),
            'scheduled_end_time':   end_dt.strftime('%Y-%m-%dT%H:%M:%S'),
            'duration_hours': float(job['duration']),
            'assigned_technicians': assigned_techs
        })

    _save_optimized_schedule(optimized_schedule, "OR-Tools")

    # Stats
    scheduled_ids   = [j['job_id'] for j in optimized_schedule]
    unscheduled_ids = [u['job_id'] for u in unfeasible_jobs]

    print("\n=== Scheduling Statistics ===")
    print(f"  - Total jobs:      {len(filtered_jobs) + len(unfeasible_jobs)}")
    print(f"  - Scheduled jobs:  {len(scheduled_ids)}")
    print(f"  - Unscheduled:     {len(unscheduled_ids)}")
    if unscheduled_ids:
        print("  - Unscheduled list:")
        for u in unfeasible_jobs:
            print(f"    · {u['job_id']}: {', '.join(u['reason'])}")

    return optimized_schedule


if __name__ == "__main__":
    optimize_schedule()
