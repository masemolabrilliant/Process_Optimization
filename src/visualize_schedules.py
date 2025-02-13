# src/visualize_schedules.py

import json
import os
import plotly.figure_factory as ff
from datetime import datetime

# Define paths to the schedules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
OPTIMIZED_SCHEDULE_FILE = os.path.join(DATA_DIR, 'optimized_schedule.json')

def load_schedule(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def prepare_gantt_data(schedule, label_prefix):
    gantt_data = []
    for job in schedule:
        for split in job['splits']:
            gantt_data.append(dict(
                Task=f"{label_prefix} {job['job_id']} Split {split['split_id']}",
                Start=split['scheduled_start_time'],
                Finish=split['scheduled_end_time'],
                Resource=job['equipment_id']
            ))
    return gantt_data

def main():
    if not os.path.exists(OPTIMIZED_SCHEDULE_FILE):
        print(f"Optimized schedule file not found: {OPTIMIZED_SCHEDULE_FILE}")
        return

    optimized_schedule = load_schedule(OPTIMIZED_SCHEDULE_FILE)
    optimized_gantt = prepare_gantt_data(optimized_schedule, 'Optimized')
    fig = ff.create_gantt(optimized_gantt, index_col='Resource', show_colorbar=True, group_tasks=True, title='Optimized Schedule')
    fig.show()

if __name__ == "__main__":
    main()
