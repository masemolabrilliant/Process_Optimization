# # src/data_handler.py

# import json
# import os
# from typing import Any, Dict, List
# from src.validator import load_schema, validate_json

# # Determine the absolute path to the project root
# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
# SCHEMA_DIR = os.path.join(PROJECT_ROOT, 'schemas')

# def load_json(filename: str) -> Any:
#     """Load JSON data from a file."""
#     # Construct the absolute file path
#     filepath = os.path.join(DATA_DIR, filename)
#     # Check if the file exists before trying to open it
#     if not os.path.exists(filepath):
#         raise FileNotFoundError(f"Error: File '{filepath}' not found.")
#     with open(filepath, 'r') as f:
#         data = json.load(f)
#     return data

# def validate_data(data: Any, schema_filename: str) -> bool:
#     """Validate data against the corresponding schema."""
#     schema_path = os.path.join(SCHEMA_DIR, schema_filename)
#     schema = load_schema(schema_path)
#     is_valid = validate_json(data, schema)
#     return is_valid

# def preprocess_data(data: Dict[str, Any]) -> Dict[str, Any]:
#     """Preprocess the data as needed."""
#     # Create lookup dictionaries for quick access
#     data['equipment_dict'] = {equip['equipment_id']: equip for equip in data['equipment']}
#     data['technicians_dict'] = {tech['tech_id']: tech for tech in data['technicians']}
#     data['tools_dict'] = {tool['tool_id']: tool for tool in data['tools']}
#     data['materials_dict'] = {mat['material_id']: mat for mat in data['materials']}
#     data['jobs_dict'] = {job['job_id']: job for job in data['jobs']}

#     return data

# def check_data_consistency(data: Dict[str, Any]) -> bool:
#     """Check consistency across data files."""
#     valid = True

#     # Check that job equipment_ids reference valid equipment
#     equipment_ids = set(data['equipment_dict'].keys())
#     for job in data['jobs']:
#         if job['equipment_id'] not in equipment_ids:
#             print(f"Error: Job '{job['job_id']}' references unknown equipment_id '{job['equipment_id']}'.")
#             valid = False

#     # Check that required_skills in jobs are valid
#     all_skills = set()
#     for tech in data['technicians']:
#         all_skills.update(tech['skills'])
#     for job in data['jobs']:
#         for skill in job['required_skills']:
#             if skill not in all_skills:
#                 print(f"Warning: Job '{job['job_id']}' requires unknown skill '{skill}'.")
#                 # Depending on policy, might set valid = False here
#                 # For now, we'll just warn

#     # Check that tool_ids in jobs reference valid tools
#     tool_ids = set(data['tools_dict'].keys())
#     for job in data['jobs']:
#         for tool_req in job['required_tools']:
#             if tool_req['tool_id'] not in tool_ids:
#                 print(f"Error: Job '{job['job_id']}' requires unknown tool_id '{tool_req['tool_id']}'.")
#                 valid = False

#     # Check that material_ids in jobs reference valid materials
#     material_ids = set(data['materials_dict'].keys())
#     for job in data['jobs']:
#         for mat_req in job['required_materials']:
#             if mat_req['material_id'] not in material_ids:
#                 print(f"Error: Job '{job['job_id']}' requires unknown material_id '{mat_req['material_id']}'.")
#                 valid = False

#     # Check that job precedences reference valid job_ids
#     job_ids = set(data['jobs_dict'].keys())
#     for job in data['jobs']:
#         for pred_id in job['precedence']:
#             if pred_id not in job_ids:
#                 print(f"Error: Job '{job['job_id']}' has unknown predecessor job_id '{pred_id}'.")
#                 valid = False

#     return valid

# def load_and_validate_data() -> Dict[str, Any]:
#     """Load and validate all data files."""
#     data_files = {
#         'equipment': ('equipment.json', 'equipment_schema.json'),
#         'technicians': ('technicians.json', 'technicians_schema.json'),
#         'tools': ('tools.json', 'tools_schema.json'),
#         'materials': ('materials.json', 'materials_schema.json'),
#         'jobs': ('jobs.json', 'jobs_schema.json')
#     }

#     data = {}
#     for key, (data_file, schema_file) in data_files.items():
#         print(f"Loading {data_file}...")
#         try:
#             data_content = load_json(data_file)
#         except FileNotFoundError:
#             print(f"Error: File '{data_file}' not found in directory '{DATA_DIR}'.")
#             raise

#         print(f"Validating {data_file}...")
#         is_valid = validate_data(data_content, schema_file)
#         if is_valid:
#             data[key] = data_content
#             print(f"{data_file} loaded and validated successfully.")
#         else:
#             raise ValueError(f"Validation failed for {data_file}.")

#     # Preprocess data
#     data = preprocess_data(data)

#     # Check data consistency across files
#     print("Checking data consistency across files...")
#     is_consistent = check_data_consistency(data)
#     if not is_consistent:
#         raise ValueError("Data consistency checks failed.")

#     print("All data loaded, validated, and preprocessed successfully.")
#     return data

# if __name__ == '__main__':
#     try:
#         data = load_and_validate_data()
#         # Data is now ready for further processing
#     except ValueError as e:
#         print(f"Data loading failed: {e}")
#     except Exception as e:
#         print(f"An error occurred: {e}")




































# src/data_handler.py

from __future__ import annotations
import datetime as _dt
from typing import Dict, Any, List

from sqlalchemy.orm import joinedload

# Import your DB models
from src.models import (
    db, Job, Technician, Equipment, Tool, Material,
)

def _as_int(x, default=0) -> int:
    try:
        return int(x)
    except Exception:
        return int(default)

def _as_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def _iso(dt: _dt.datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M:%S')

def _compute_window(
    planning_start: _dt.datetime | str | None,
    planning_days: int,
    workday_start: str,
    workday_end: str
) -> tuple[str, str]:
    """
    Return ISO strings (YYYY-MM-DDTHH:MM:SS) for t_start/t_end.
    """
    if planning_start is None:
        today = _dt.date.today()
        start_time = _dt.time.fromisoformat(workday_start)
        t_start = _dt.datetime.combine(today, start_time)
    elif isinstance(planning_start, str):
        # Accept either date or full datetime strings
        try:
            t_start = _dt.datetime.fromisoformat(planning_start)
        except ValueError:
            # If a date was provided, combine with workday_start
            t_start = _dt.datetime.combine(_dt.date.fromisoformat(planning_start), _dt.time.fromisoformat(workday_start))
    else:
        t_start = planning_start

    # t_end at end-of-day after N days
    end_date = (t_start + _dt.timedelta(days=planning_days)).date()
    t_end = _dt.datetime.combine(end_date, _dt.time.fromisoformat(workday_end))
    return _iso(t_start), _iso(t_end)


def load_and_validate_data(
    planning_start: _dt.datetime | str | None = None,
    planning_days: int = 7,
    workday_start: str = "08:00",
    workday_end: str = "17:00"
) -> Dict[str, Any]:
    """
    Build the in-memory data dict directly from the DATABASE.

    Returns a dict with the exact shape expected by the optimizers:
      {
        't_start': 'YYYY-MM-DDTHH:MM:SS',
        't_end':   'YYYY-MM-DDTHH:MM:SS',
        'jobs': [
          {
            'job_id': 'J001',
            'description': '...',
            'duration': 4,  # hours (int)
            'equipment_id': 'EQ1',
            'required_skills': ['Welding', ...],
            'required_tools': [{'tool_id': 'T01', 'quantity': 2}, ...],
            'required_materials': [{'material_id': 'M01', 'quantity': 5}, ...],
            'precedence': ['J000', 'J099']  # predecessors that must finish first
          }, ...
        ],
        'technicians': [
          {'tech_id': 'T001', 'name': '...', 'skills': [...], 'hourly_rate': 350.0, 'email': '...'}, ...
        ],
        'tools':      [{'tool_id': 'T01', 'quantity': 10}, ...],
        'materials':  [{'material_id': 'M01', 'quantity': 20}, ...],
        'equipment':  [{'equipment_id': 'EQ1'}, ...],
      }
    """
    # ----- Planning window -----
    t_start, t_end = _compute_window(planning_start, planning_days, workday_start, workday_end)

    # ----- JOBS + relationships -----
    jobs: List[Job] = Job.query.options(
        joinedload(Job.skills),
        joinedload(Job.tools),
        joinedload(Job.materials),
        joinedload(Job.preceded_by),   # rows where SOME OTHER job precedes THIS job
    ).all()

    jobs_payload: List[Dict[str, Any]] = []
    for j in jobs:
        job_dict = {
            'job_id': j.job_id,
            'description': j.description,
            'duration': _as_int(j.duration),
            'equipment_id': j.equipment_id,
            'required_skills': [js.skill for js in j.skills],
            'required_tools': [
                {'tool_id': jt.tool_id, 'quantity': _as_int(jt.quantity)}
                for jt in j.tools
            ],
            'required_materials': [
                {'material_id': jm.material_id, 'quantity': _as_int(jm.quantity)}
                for jm in j.materials
            ],
            # PREDECESSORS (must finish before this job starts):
            # use edge.job_id (the *other* job that points to this job),
            # not precedes_job_id (which would be "whom THIS job precedes").
            'precedence': [edge.job_id for edge in j.preceded_by],
        }
        jobs_payload.append(job_dict)

    # ----- TECHNICIANS (+ skills) -----
    techs: List[Technician] = Technician.query.options(
        joinedload(Technician.skills)
    ).all()

    technicians_payload: List[Dict[str, Any]] = [{
        'tech_id': t.tech_id,
        'name': t.name,
        'skills': [ts.skill for ts in t.skills],
        'hourly_rate': _as_float(t.hourly_rate or 0.0),
        'email': t.email,
    } for t in techs]

    # ----- RESOURCES -----
    tools_payload = [{'tool_id': tt.tool_id, 'quantity': _as_int(tt.quantity or 0)} for tt in Tool.query.all()]
    materials_payload = [{'material_id': mm.material_id, 'quantity': _as_int(mm.quantity or 0)} for mm in Material.query.all()]
    equipment_payload = [{'equipment_id': e.equipment_id} for e in Equipment.query.all()]

    data: Dict[str, Any] = {
        't_start': t_start,
        't_end':   t_end,
        'jobs': jobs_payload,
        'technicians': technicians_payload,
        'tools': tools_payload,
        'materials': materials_payload,
        'equipment': equipment_payload,
    }
    return data
