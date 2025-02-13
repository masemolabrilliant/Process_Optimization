# src/compare_schedules.property

import json
import os
from datetime import datetime, timedelta

# Define paths to the schedules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
INITIAL_SCHEDULE_FILE = os.path.join(DATA_DIR, 'schedule.json')
OPTIMIZED_SCHEDULE_FILE = os.path.join(DATA_DIR, 'optimized_schedule.json')

def load_schedule(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def parse_datetime(dt_str):
    return datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')

def compare_schedules(initial, optimized):
    comparison = []
    initial_jobs = {job['job_id']: job for job in initial}
    optimized_jobs = {job['job_id']: job for job in optimized}
    
    all_job_ids = set(initial_jobs.keys()).union(set(optimized_jobs.keys()))
    
    for job_id in all_job_ids:
        initial_job = initial_jobs.get(job_id)
        optimized_job = optimized_jobs.get(job_id)
        
        if not initial_job:
            comparison.append({
                'job_id': job_id,
                'initial_start': None,
                'initial_end': None,
                'optimized_start': optimized_job['scheduled_start_time'],
                'optimized_end': optimized_job['scheduled_end_time']
            })
            continue
        
        if not optimized_job:
            comparison.append({
                'job_id': job_id,
                'initial_start': initial_job['scheduled_start_time'],
                'initial_end': initial_job['scheduled_end_time'],
                'optimized_start': None,
                'optimized_end': None
            })
            continue
        
        comparison.append({
            'job_id': job_id,
            'initial_start': initial_job['scheduled_start_time'],
            'initial_end': initial_job['scheduled_end_time'],
            'optimized_start': optimized_job['scheduled_start_time'],
            'optimized_end': optimized_job['scheduled_end_time']
        })
    
    return comparison

def print_comparison(comparison):
    print(f"{'Job ID':<10} {'Initial Start':<20} {'Initial End':<20} {'Optimized Start':<20} {'Optimized End':<20}")
    print("-" * 90)
    for job in comparison:
        print(f"{job['job_id']:<10} {job['initial_start']:<20} {job['initial_end']:<20} {job['optimized_start']:<20} {job['optimized_end']:<20}")

def main():
    if not os.path.exists(INITIAL_SCHEDULE_FILE):
        print(f"Initial schedule file not found: {INITIAL_SCHEDULE_FILE}")
        return
    if not os.path.exists(OPTIMIZED_SCHEDULE_FILE):
        print(f"Optimized schedule file not found: {OPTIMIZED_SCHEDULE_FILE}")
        return
    
    initial_schedule = load_schedule(INITIAL_SCHEDULE_FILE)
    optimized_schedule = load_schedule(OPTIMIZED_SCHEDULE_FILE)
    
    comparison = compare_schedules(initial_schedule, optimized_schedule)
    print_comparison(comparison)

if __name__ == "__main__":
    main()
