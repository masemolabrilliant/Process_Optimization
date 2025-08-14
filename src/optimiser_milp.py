# src/optimiser_milp.py
"""
MILP/CP-SAT optimizer that packs jobs as EARLY as possible while respecting:
- working hours (multi-day horizon, no work outside the daily window)
- precedence (predecessors must finish first)
- single-equipment capacity
- single-technician assignment with full-skill coverage (no overlaps per tech)
- limited tool quantities via cumulative resource
- material stock as total quantities (no time dimension)

Primary objective:  minimize makespan (finish as early as possible overall)
Secondary:          minimize number of used days / prefer earlier days
Tertiary:           minimize the sum of start times (pack earlier within days)

The solver *does not* intentionally leave gaps. If jobs spill to another day,
they are scheduled at that next day's morning window, subject to constraints.
"""
from __future__ import annotations

import os
import json
import math
import datetime as dt
from typing import Dict, Any, List, Tuple, Set, DefaultDict
from collections import defaultdict

from ortools.sat.python import cp_model

# Project root & data loader
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

from src.data_handler import load_and_validate_data  # DB-backed loader


# ------------------------------ time helpers ------------------------------

WORKDAY_START = dt.time.fromisoformat("08:00")
WORKDAY_END   = dt.time.fromisoformat("17:00")
WORKDAYS = {0, 1, 2, 3, 4}  # Monday..Friday

def _to_dt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)

def _minutes_from(t: dt.datetime, origin: dt.datetime) -> int:
    return int((t - origin).total_seconds() // 60)

def _minutes_to_dt(origin: dt.datetime, minutes: int) -> dt.datetime:
    return origin + dt.timedelta(minutes=minutes)

def _build_working_days(t_start: dt.datetime, t_end: dt.datetime) -> List[Tuple[int, int, int]]:
    """
    Return list of (day_index, day_start_min, day_end_min) relative to t_start.
    Only includes Mon-Fri. Clips first/last day to [t_start, t_end].
    """
    days: List[Tuple[int,int,int]] = []
    cur = t_start
    idx = 0
    while cur < t_end:
        if cur.weekday() in WORKDAYS:
            d_start = dt.datetime.combine(cur.date(), WORKDAY_START)
            d_end   = dt.datetime.combine(cur.date(), WORKDAY_END)
            if d_start < t_start:
                d_start = t_start
            if d_end > t_end:
                d_end = t_end
            if d_start < d_end:
                days.append((idx, _minutes_from(d_start, t_start), _minutes_from(d_end, t_start)))
        # step to next calendar day at same time of day as cur
        cur = dt.datetime.combine((cur + dt.timedelta(days=1)).date(), cur.time())
        idx += 1
    return days

# ------------------------------ core optimizer ------------------------------

def optimize_schedule(save: bool = True, max_time_s: int = 30) -> List[Dict[str, Any]]:
    data = load_and_validate_data()
    t_start = _to_dt(data['t_start'])
    t_end   = _to_dt(data['t_end'])

    # Working day windows (minutes from t_start)
    day_windows = _build_working_days(t_start, t_end)
    if not day_windows:
        raise RuntimeError("No working windows inside planning horizon.")
    horizon = day_windows[-1][2]  # last day end (minutes from t_start)
    day_len = (dt.datetime.combine(dt.date.today(), WORKDAY_END) - 
               dt.datetime.combine(dt.date.today(), WORKDAY_START)).seconds // 60

    # Index entities
    jobs = data['jobs']
    techs = data['technicians']
    tools = {t['tool_id']: int(t.get('quantity', 0)) for t in data.get('tools', [])}
    materials = {m['material_id']: int(m.get('quantity', 0)) for m in data.get('materials', [])}

    # Pre-filter jobs: duration must fit within a workday
    filtered_jobs: List[Dict[str, Any]] = []
    unfeasible: List[Dict[str, Any]] = []
    for j in jobs:
        dur_min = int(j['duration']) * 60
        reasons = []
        if dur_min > day_len:
            reasons.append(f"duration {j['duration']}h exceeds workday {day_len//60}h")
        # eligible technician check (must have all required skills)
        req_sk = set(j.get('required_skills', []))
        eligible_ts = [t for t in techs if req_sk.issubset(set(t.get('skills', [])))]
        if not eligible_ts:
            reasons.append("no technician has all required skills")
        # tool capacity quick check
        for need in j.get('required_tools', []):
            cap = tools.get(need['tool_id'], 0)
            if int(need['quantity']) > cap:
                reasons.append(f"tool {need['tool_id']} needs {need['quantity']} > cap {cap}")
        # material stock quick check (total)
        for need in j.get('required_materials', []):
            cap = materials.get(need['material_id'], 0)
            if int(need['quantity']) > cap:
                reasons.append(f"material {need['material_id']} needs {need['quantity']} > stock {cap}")

        if reasons:
            unfeasible.append({'job_id': j['job_id'], 'reason': reasons})
        else:
            j = j.copy()
            j['_dur_min'] = dur_min
            j['_eligible_ts'] = [t['tech_id'] for t in eligible_ts]
            filtered_jobs.append(j)

    if not filtered_jobs:
        # nothing scheduleable
        schedule: List[Dict[str, Any]] = []
        if save:
            _save(schedule)
        return schedule

    model = cp_model.CpModel()

    # Vars per job
    start: Dict[str, cp_model.IntVar] = {}
    end: Dict[str, cp_model.IntVar] = {}
    interval: Dict[str, cp_model.IntervalVar] = {}
    # Day assignment literals a[j][k]
    a: Dict[str, List[cp_model.BoolVar]] = {}

    # Tech assignment literals y[j][t]
    y: Dict[str, Dict[str, cp_model.BoolVar]] = defaultdict(dict)
    tech_intervals: DefaultDict[str, List[cp_model.IntervalVar]] = defaultdict(list)

    # Equipment NoOverlap buckets
    equip_intervals: DefaultDict[str, List[cp_model.IntervalVar]] = defaultdict(list)

    # Build day bounds arrays
    day_count = len(day_windows)

    # Create per-job variables and constraints
    for j in filtered_jobs:
        jid = j['job_id']
        dur = j['_dur_min']

        # Time vars
        start[jid] = model.NewIntVar(0, horizon, f"start_{jid}")
        end[jid]   = model.NewIntVar(0, horizon, f"end_{jid}")
        model.Add(end[jid] == start[jid] + dur)
        interval[jid] = model.NewIntervalVar(start[jid], dur, end[jid], f"iv_{jid}")

        # Day selection literals
        a[jid] = []
        # each job must be assigned to exactly one *working* day window that can fit it
        usable_days = 0
        for k, (_, d_start, d_end) in enumerate(day_windows):
            # if job can't fit that day window, skip literal
            if d_end - d_start < dur:
                a[jid].append(None)  # placeholder for indexing
                continue
            lit = model.NewBoolVar(f"a_{jid}_{k}")
            a[jid].append(lit)
            usable_days += 1
            # bound start into [d_start, d_end - dur] when this day is chosen
            model.Add(start[jid] >= d_start).OnlyEnforceIf(lit)
            model.Add(start[jid] <= d_end - dur).OnlyEnforceIf(lit)
        # exactly one usable day must be chosen
        chosen_lits = [lit for lit in a[jid] if lit is not None]
        if not chosen_lits:
            # shouldn't happen due to pre-filter, but guard anyway
            unfeasible.append({'job_id': jid, 'reason': [f"no day can fit duration {dur}min"]})
            # lock job at t_start to avoid orphan; but we will not include it later
            a[jid] = []
            continue
        model.Add(sum(chosen_lits) == 1)

        # Equipment NoOverlap
        eq = j['equipment_id']
        equip_intervals[eq].append(interval[jid])

        # Technician assignment (exactly ONE who covers all skills)
        for t in j['_eligible_ts']:
            y[jid][t] = model.NewBoolVar(f"y_{jid}_{t}")
            # Optional interval for tech capacity using the *same* start/end
            tech_iv = model.NewOptionalIntervalVar(start[jid], dur, end[jid], y[jid][t], f"iv_{jid}_tech_{t}")
            tech_intervals[t].append(tech_iv)
        model.Add(sum(y[jid].values()) == 1)

    # Precedence
    pred_map: Dict[str, Set[str]] = {j['job_id']: set(j.get('precedence', [])) for j in filtered_jobs}
    for j in filtered_jobs:
        jid = j['job_id']
        for p in pred_map[jid]:
            if p in start:  # only if predecessor is scheduleable
                model.Add(start[jid] >= end[p])

    # Tools cumulative
    for tool_id, cap in tools.items():
        if cap <= 0:
            continue
        ivs: List[cp_model.IntervalVar] = []
        demands: List[int] = []
        for j in filtered_jobs:
            # find demand
            d = 0
            for need in j.get('required_tools', []):
                if need['tool_id'] == tool_id:
                    d = int(need['quantity'])
                    break
            if d > 0:
                ivs.append(interval[j['job_id']])
                demands.append(d)
        if ivs:
            model.AddCumulative(ivs, demands, cap)

    # Materials one-shot capacity
    for mat_id, cap in materials.items():
        total_need = sum(int(need['quantity'])
                         for j in filtered_jobs
                         for need in j.get('required_materials', [])
                         if need['material_id'] == mat_id)
        model.Add(total_need <= cap)

    # Technician NoOverlap
    for tech_id, ivs in tech_intervals.items():
        # intervals carry presence literals; NoOverlap respects them
        model.AddNoOverlap(ivs)

    # Equipment NoOverlap
    for eq_id, ivs in equip_intervals.items():
        model.AddNoOverlap(ivs)

    # Day usage indicators and objective terms
    day_used: List[cp_model.BoolVar] = []
    for k, (_, d_start, d_end) in enumerate(day_windows):
        yk = model.NewBoolVar(f"day_used_{k}")
        day_used.append(yk)
        for j in filtered_jobs:
            lits = a[j['job_id']]
            if k < len(lits) and lits[k] is not None:
                # if job chooses this day => that day is used
                model.AddImplication(lits[k], yk)

    # Makespan
    makespan = model.NewIntVar(0, horizon, "makespan")
    model.AddMaxEquality(makespan, [end[j['job_id']] for j in filtered_jobs])

    # Total start time and total day index (earliness pressure)
    total_start = model.NewIntVar(0, horizon * len(filtered_jobs), "total_start")
    model.Add(total_start == sum(start[j['job_id']] for j in filtered_jobs))

    total_days_used = model.NewIntVar(0, len(day_windows), "total_days_used")
    model.Add(total_days_used == sum(day_used))

    # Objective: BIG1*makespan + BIG2*total_days_used + total_start
    BIG1 = horizon * 1000
    BIG2 = horizon  # using minutes so this is smaller than BIG1 but strong
    model.Minimize(BIG1 * makespan + BIG2 * total_days_used + total_start)

    # Solver params
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_time_s)
    solver.parameters.num_search_workers = max(4, os.cpu_count() or 4)
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Return empty schedule; caller can show message
        schedule: List[Dict[str, Any]] = []
        if save:
            _save(schedule)
        return schedule

    # Build solution
    # Map tech assignment
    job_to_tech: Dict[str, str] = {}
    for j in filtered_jobs:
        jid = j['job_id']
        for t, lit in y[jid].items():
            if solver.BooleanValue(lit):
                job_to_tech[jid] = t
                break

    schedule: List[Dict[str, Any]] = []
    for j in filtered_jobs:
        jid = j['job_id']
        s_min = solver.Value(start[jid])
        e_min = solver.Value(end[jid])
        s_dt = _minutes_to_dt(t_start, s_min)
        e_dt = _minutes_to_dt(t_start, e_min)
        schedule.append({
            "job_id": jid,
            "description": j.get("description", ""),
            "equipment_id": j.get("equipment_id"),
            "assigned_technicians": [job_to_tech.get(jid)] if job_to_tech.get(jid) else [],
            "scheduled_start_time": s_dt.isoformat(),
            "scheduled_end_time": e_dt.isoformat(),
            "duration_hours": j['duration']
        })

    # Sort by start time
    schedule.sort(key=lambda r: r["scheduled_start_time"])

    if save:
        _save(schedule)

    return schedule


def _save(schedule: List[Dict[str, Any]], name: str = "milp") -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"optimized_schedule_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, indent=2)

if __name__ == "__main__":
    optimize_schedule()
