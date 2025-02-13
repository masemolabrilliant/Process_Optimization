# src/validator.py

import json
from jsonschema import Draft7Validator
from typing import Any, Dict

def load_schema(schema_file: str) -> Dict[str, Any]:
    """Load a JSON schema from a file."""
    with open(schema_file, 'r') as f:
        schema = json.load(f)
    return schema

def validate_json(data: Any, schema: Dict[str, Any]) -> bool:
    """Validate JSON data against a schema."""
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        for error in errors:
            path = '.'.join([str(p) for p in error.path])
            print(f"Validation error at '{path}': {error.message}")
        return False
    return True
