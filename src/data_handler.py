# src/data_handler.py

import json
import os
from typing import Any, Dict, List
from src.validator import load_schema, validate_json

# Determine the absolute path to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
SCHEMA_DIR = os.path.join(PROJECT_ROOT, 'schemas')

def load_json(filename: str) -> Any:
    """Load JSON data from a file."""
    # Construct the absolute file path
    filepath = os.path.join(DATA_DIR, filename)
    # Check if the file exists before trying to open it
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Error: File '{filepath}' not found.")
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data

def validate_data(data: Any, schema_filename: str) -> bool:
    """Validate data against the corresponding schema."""
    schema_path = os.path.join(SCHEMA_DIR, schema_filename)
    schema = load_schema(schema_path)
    is_valid = validate_json(data, schema)
    return is_valid

def preprocess_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Preprocess the data as needed."""
    # Create lookup dictionaries for quick access
    data['equipment_dict'] = {equip['equipment_id']: equip for equip in data['equipment']}
    data['technicians_dict'] = {tech['tech_id']: tech for tech in data['technicians']}
    data['tools_dict'] = {tool['tool_id']: tool for tool in data['tools']}
    data['materials_dict'] = {mat['material_id']: mat for mat in data['materials']}
    data['jobs_dict'] = {job['job_id']: job for job in data['jobs']}

    return data

def check_data_consistency(data: Dict[str, Any]) -> bool:
    """Check consistency across data files."""
    valid = True

    # Check that job equipment_ids reference valid equipment
    equipment_ids = set(data['equipment_dict'].keys())
    for job in data['jobs']:
        if job['equipment_id'] not in equipment_ids:
            print(f"Error: Job '{job['job_id']}' references unknown equipment_id '{job['equipment_id']}'.")
            valid = False

    # Check that required_skills in jobs are valid
    all_skills = set()
    for tech in data['technicians']:
        all_skills.update(tech['skills'])
    for job in data['jobs']:
        for skill in job['required_skills']:
            if skill not in all_skills:
                print(f"Warning: Job '{job['job_id']}' requires unknown skill '{skill}'.")
                # Depending on policy, might set valid = False here
                # For now, we'll just warn

    # Check that tool_ids in jobs reference valid tools
    tool_ids = set(data['tools_dict'].keys())
    for job in data['jobs']:
        for tool_req in job['required_tools']:
            if tool_req['tool_id'] not in tool_ids:
                print(f"Error: Job '{job['job_id']}' requires unknown tool_id '{tool_req['tool_id']}'.")
                valid = False

    # Check that material_ids in jobs reference valid materials
    material_ids = set(data['materials_dict'].keys())
    for job in data['jobs']:
        for mat_req in job['required_materials']:
            if mat_req['material_id'] not in material_ids:
                print(f"Error: Job '{job['job_id']}' requires unknown material_id '{mat_req['material_id']}'.")
                valid = False

    # Check that job precedences reference valid job_ids
    job_ids = set(data['jobs_dict'].keys())
    for job in data['jobs']:
        for pred_id in job['precedence']:
            if pred_id not in job_ids:
                print(f"Error: Job '{job['job_id']}' has unknown predecessor job_id '{pred_id}'.")
                valid = False

    return valid

def load_and_validate_data() -> Dict[str, Any]:
    """Load and validate all data files."""
    data_files = {
        'equipment': ('equipment.json', 'equipment_schema.json'),
        'technicians': ('technicians.json', 'technicians_schema.json'),
        'tools': ('tools.json', 'tools_schema.json'),
        'materials': ('materials.json', 'materials_schema.json'),
        'jobs': ('jobs.json', 'jobs_schema.json')
    }

    data = {}
    for key, (data_file, schema_file) in data_files.items():
        print(f"Loading {data_file}...")
        try:
            data_content = load_json(data_file)
        except FileNotFoundError:
            print(f"Error: File '{data_file}' not found in directory '{DATA_DIR}'.")
            raise

        print(f"Validating {data_file}...")
        is_valid = validate_data(data_content, schema_file)
        if is_valid:
            data[key] = data_content
            print(f"{data_file} loaded and validated successfully.")
        else:
            raise ValueError(f"Validation failed for {data_file}.")

    # Preprocess data
    data = preprocess_data(data)

    # Check data consistency across files
    print("Checking data consistency across files...")
    is_consistent = check_data_consistency(data)
    if not is_consistent:
        raise ValueError("Data consistency checks failed.")

    print("All data loaded, validated, and preprocessed successfully.")
    return data

if __name__ == '__main__':
    try:
        data = load_and_validate_data()
        # Data is now ready for further processing
    except ValueError as e:
        print(f"Data loading failed: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
