# src/precheck.py
import datetime
from typing import Dict, List, Tuple

WORKDAY_START = datetime.time(8, 0)
WORKDAY_END   = datetime.time(17, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Mon–Fri

def _daily_work_hours() -> float:
    return (
        datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_END) -
        datetime.datetime.combine(datetime.date(2000, 1, 1), WORKDAY_START)
    ).total_seconds() / 3600.0

def precheck_jobs(data: Dict) -> Tuple[List[Dict], List[Dict]]:
    """
    Returns (unscheduled, feasible_jobs)

    Each unscheduled item:
      { job_id, description, duration, equipment_id, required_skills, required_tools, required_materials, reason: [..] }
    """
    jobs   = data['jobs']
    techs  = data['technicians']
    tools  = data['tools']
    mats   = data['materials']

    tool_caps = {t['tool_id']: int(t['quantity']) for t in tools}
    mat_caps  = {m['material_id']: int(m['quantity']) for m in mats}
    day_len   = _daily_work_hours()

    unscheduled: List[Dict] = []
    feasible:    List[Dict] = []

    for job in jobs:
        reasons = []

        # Tools
        for req in job.get('required_tools', []):
            needed = int(req['quantity'])
            avail  = tool_caps.get(req['tool_id'], 0)
            if needed > avail:
                reasons.append(f"Needs {needed} of tool {req['tool_id']}, only {avail} available.")

        # Materials
        for req in job.get('required_materials', []):
            needed = int(req['quantity'])
            avail  = mat_caps.get(req['material_id'], 0)
            if needed > avail:
                reasons.append(f"Needs {needed} of material {req['material_id']}, only {avail} available.")

        # Skills (at least one technician has ALL required skills)
        req_skills = set(job.get('required_skills', []))
        eligible = [t for t in techs if req_skills.issubset(set(t.get('skills', [])))]
        if not eligible and req_skills:
            reasons.append("No matching technicians with required skills.")

        # Duration > single workday (no split allowed before optimization)
        dur = float(job.get('duration', 0))
        if dur > day_len:
            reasons.append(
                f"Duration {dur}h exceeds workday length {int(day_len)}h "
                f"({WORKDAY_START.strftime('%H:%M')}-{WORKDAY_END.strftime('%H:%M')})."
            )

        record = {
            'job_id': job['job_id'],
            'description': job.get('description', ''),
            'duration': dur,
            'equipment_id': job['equipment_id'],
            'required_skills': job.get('required_skills', []),
            'required_tools': job.get('required_tools', []),
            'required_materials': job.get('required_materials', [])
        }

        if reasons:
            record['reason'] = reasons
            unscheduled.append(record)
        else:
            feasible.append(job)

    return unscheduled, feasible
