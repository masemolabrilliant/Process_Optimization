# src/scheduler.py

import sys
import os
import json

# Add the root directory to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datetime
from typing import List, Dict, Any, Optional, Tuple
from src.data_handler import load_and_validate_data
from src.gantt_chart import generate_gantt_chart
from src.metrics import generate_report, save_report_to_excel, save_report_to_csv, generate_visualizations

class Equipment:
    def __init__(self, equipment_id: str, name: str, priority: int,
                 workday_start: str = "00:00", workday_end: str = "23:59", workdays: List[int] = [0,1,2,3,4,5,6]):
        self.equipment_id = equipment_id
        self.name = name
        self.priority = priority
        self.schedule = []  # List of (start_time, end_time, job_id)
        # Added workday_start_time, workday_end_time, and workdays to Equipment class
        self.workday_start_time = datetime.datetime.strptime(workday_start, "%H:%M").time()
        self.workday_end_time = datetime.datetime.strptime(workday_end, "%H:%M").time()
        self.workdays = set(workdays)

    def is_available(self, start_time: datetime.datetime, end_time: datetime.datetime) -> bool:
        for scheduled_start, scheduled_end, _ in self.schedule:
            if not (end_time <= scheduled_start or start_time >= scheduled_end):
                return False
        return True

class Technician:
    def __init__(self, tech_id: str, name: str, skills: List[str], hourly_rate: float, workday_start: str = "08:00", workday_end: str = "18:00", workdays: List[int] = [0,1,2,3,4]):
        self.tech_id = tech_id
        self.name = name
        self.skills = skills
        self.hourly_rate = hourly_rate
        self.workday_start_time = datetime.datetime.strptime(workday_start, "%H:%M").time()
        self.workday_end_time = datetime.datetime.strptime(workday_end, "%H:%M").time()
        self.workdays = set(workdays)
        # self.availability = []  # List of available time slots
        self.assignments = []  # List of (start_time, end_time, job_id)

    def is_available(self, start_time: datetime.datetime, end_time: datetime.datetime) -> bool:
        # Check if the requested time is within the technician's working hours
        if start_time.time() < self.workday_start_time or end_time.time() > self.workday_end_time:
            return False
        if start_time.weekday() not in self.workdays or end_time.weekday() not in self.workdays:
            return False
        # Check if technician is not currently assigned to a job    
        for assignment in self.assignments:
            assigned_start, assigned_end, _ = assignment
            if not (end_time <= assigned_start or start_time >= assigned_end):
                return False
        return True

class Tool:
    def __init__(self, tool_id: str, name: str, quantity: int):
        self.tool_id = tool_id
        self.name = name
        self.total_quantity = quantity
        self.reservations = []  # List of (start_time, end_time, quantity_reserved)

    def is_available(self, start_time: datetime.datetime, end_time: datetime.datetime, quantity_needed: int) -> bool:
        quantity_in_use = 0
        for reservation in self.reservations:
            reserved_start, reserved_end, quantity_reserved = reservation
            if not (end_time <= reserved_start or start_time >= reserved_end):
                quantity_in_use += quantity_reserved
        return (self.total_quantity - quantity_in_use) >= quantity_needed

    def reserve(self, start_time: datetime.datetime, end_time: datetime.datetime, quantity_reserved: int):
        self.reservations.append((start_time, end_time, quantity_reserved))

class Material:
    def __init__(self, material_id: str, name: str, quantity: float):
        self.material_id = material_id
        self.name = name
        self.total_quantity = quantity
        self.quantity_used = 0.0

    def is_available(self, quantity_needed: float) -> bool:
        return (self.total_quantity - self.quantity_used) >= quantity_needed

    def allocate(self, quantity_used: float):
        self.quantity_used += quantity_used

class Job:
    def __init__(self, job_data: Dict[str, Any]):
        self.job_id = job_data['job_id']
        self.description = job_data['description']
        self.equipment_id = job_data['equipment_id']
        self.duration = datetime.timedelta(hours=job_data['duration'])
        self.required_skills = job_data['required_skills']
        self.required_tools = job_data['required_tools']
        self.required_materials = job_data['required_materials']
        self.precedence = job_data['precedence']
        self.scheduled_start_time: Optional[datetime.datetime] = None
        self.scheduled_end_time: Optional[datetime.datetime] = None
        self.assigned_technicians: List[Technician] = []
        self.status = 'unscheduled'  # Could be 'scheduled' or 'unscheduled'

    def is_ready(self, scheduled_jobs: Dict[str, 'Job']) -> bool:
        # Check if all predecessor jobs have been completed
        for pred_id in self.precedence:
            pred_job = scheduled_jobs.get(pred_id)
            if not pred_job or pred_job.status != 'scheduled':
                return False
        return True

class Scheduler:
    def __init__(self, data: Dict[str, Any], workday_start: str = "08:00", workday_end: str = "18:00", workdays: List[int] = [0,1,2,3,4]):
        self.jobs: Dict[str, Job] = {job_data['job_id']: Job(job_data) for job_data in data['jobs']}
        self.equipment: Dict[str, Equipment] = {equip_data['equipment_id']: Equipment(**equip_data) for equip_data in data['equipment']}
        self.technicians: Dict[str, Technician] = {tech_data['tech_id']: Technician(**tech_data) for tech_data in data['technicians']}
        self.tools: Dict[str, Tool] = {tool_data['tool_id']: Tool(**tool_data) for tool_data in data['tools']}
        self.materials: Dict[str, Material] = {mat_data['material_id']: Material(**mat_data) for mat_data in data['materials']}
        self.t_start = datetime.datetime.strptime(data.get('t_start', '2023-12-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
        self.t_end = datetime.datetime.strptime(data.get('t_end', '2023-12-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')
        self.current_time = self.t_start
        self.schedule: List[Job] = []
        self.unscheduled_jobs: List[Tuple[Job, str]] = []  # List of (Job, reason)

        # Convert workday start and end times to datetime.time objects
        self.workday_start_time = datetime.datetime.strptime(workday_start, "%H:%M").time()
        self.workday_end_time = datetime.datetime.strptime(workday_end, "%H:%M").time()

        # Define workdays (Monday=0, Sunday=6)
        self.workdays = set(workdays)

    # Implementing the helper functions

    def is_job_feasible(self, job: Job) -> bool:
        # Check if job is ready (predecessors completed)
        if not job.is_ready(self.jobs):
            return False

        # Adjusted start time to the next working time
        proposed_start_time = self.get_next_working_time(self.current_time)
        proposed_end_time = self.calculate_job_end_time(proposed_start_time, job.duration)

        # Ensure proposed times are within scheduling window
        if proposed_end_time > self.t_end:
            return False

        # Check equipment availability
        equipment = self.equipment[job.equipment_id]
        if not equipment.is_available(proposed_start_time, proposed_end_time):
            return False

        # Check if required technicians are available during proposed times
        available_techs = [
            tech for tech in self.technicians.values()
            if tech.is_available(proposed_start_time, proposed_end_time)
        ]
        if not self.can_assign_technicians(job, available_techs):
            return False

        # Check if required tools are available
        for tool_req in job.required_tools:
            tool = self.tools.get(tool_req['tool_id'])
            if not tool or not tool.is_available(proposed_start_time, proposed_end_time, tool_req['quantity']):
                return False

        # Check if required materials are available
        for mat_req in job.required_materials:
            material = self.materials.get(mat_req['material_id'])
            if not material or not material.is_available(mat_req['quantity']):
                return False

        return True


    # Technician assignment
    def can_assign_technicians(self, job: Job, available_techs: List[Technician]) -> bool:
        # Find combinations of technicians covering all required skills
        from itertools import combinations

        required_skills = set(job.required_skills)
        for r in range(1, len(available_techs) + 1):
            for tech_combo in combinations(available_techs, r):
                skills_covered = set()
                for tech in tech_combo:
                    skills_covered.update(tech.skills)
                if required_skills.issubset(skills_covered):
                    job.assigned_technicians = list(tech_combo)
                    return True
        return False

    # Assign resources
    def assign_resources(self, job: Job):
        # Assign technicians
        for tech in job.assigned_technicians:
            tech.assignments.append((job.scheduled_start_time, job.scheduled_end_time, job.job_id))

        # Reserve tools
        for tool_req in job.required_tools:
            tool = self.tools[tool_req['tool_id']]
            tool.reserve(job.scheduled_start_time, job.scheduled_end_time, tool_req['quantity'])

        # Allocate materials
        for mat_req in job.required_materials:
            material = self.materials[mat_req['material_id']]
            material.allocate(mat_req['quantity'])

        # Schedule on equipment
        equipment = self.equipment[job.equipment_id]
        equipment.schedule.append((job.scheduled_start_time, job.scheduled_end_time, job.job_id))

    def schedule_job(self, job: Job):
        proposed_start_time = self.get_next_working_time(self.current_time)
        proposed_end_time = self.calculate_job_end_time(proposed_start_time, job.duration)
        job.scheduled_start_time = proposed_start_time
        job.scheduled_end_time = proposed_end_time
        job.status = 'scheduled'
        self.assign_resources(job)
        self.schedule.append(job)

    # Main scheduling loop
    def run(self):
        # Group jobs by priority
        priority_groups = {1: [], 2: [], 3: []}
        for job in self.jobs.values():
            equipment = self.equipment[job.equipment_id]
            priority_groups[equipment.priority].append(job)

        # Process each priority group
        for priority in sorted(priority_groups.keys()):
            group_jobs = priority_groups[priority]

            # Compute effective duration and sort
            for job in group_jobs:
                job.effective_duration = job.duration + self.get_predecessors_duration(job)
            group_jobs.sort(key=lambda x: x.effective_duration)

            unscheduled_jobs = group_jobs.copy()
            while self.current_time < self.t_end and unscheduled_jobs:
                # Adjust current_time to the next working time if necessary
                self.current_time = self.get_next_working_time(self.current_time)

                feasible_jobs = []
                for job in unscheduled_jobs:
                    if self.is_job_feasible(job):
                        feasible_jobs.append(job)

                if feasible_jobs:
                    # Evaluate feasible jobs to select the best one
                    best_job = self.select_best_job(feasible_jobs)
                    # Schedule the best job
                    self.schedule_job(best_job)
                    unscheduled_jobs.remove(best_job)
                    # Do not update self.current_time here; continue scheduling at the same time
                else:
                    # Advance current_time to the next earliest scheduled job end time or next working time
                    next_times = [
                        job.scheduled_end_time for job in self.schedule
                        if job.scheduled_end_time > self.current_time
                    ]
                    if next_times:
                        self.current_time = min(next_times)
                        self.current_time = self.get_next_working_time(self.current_time)
                    else:
                        # No more scheduled jobs; advance to next working time
                        self.current_time = self.get_next_working_time(self.current_time + datetime.timedelta(minutes=1))
                    if self.current_time >= self.t_end:
                        break  # Scheduling window exceeded

            # Handle unscheduled jobs in the group
            for job in unscheduled_jobs:
                reason = self.get_unfeasibility_reason(job)
                self.unscheduled_jobs.append((job, reason))


    # Helper Methods

    def get_predecessors_duration(self, job: Job) -> datetime.timedelta:
        duration = datetime.timedelta()
        for pred_id in job.precedence:
            pred_job = self.jobs.get(pred_id)
            if pred_job:
                duration += pred_job.duration
        return duration

    def get_next_working_time(self, time: datetime.datetime) -> datetime.datetime:
        # If current time is after workday end time, move to next workday start time
        if time.time() >= self.workday_end_time or time.weekday() not in self.workdays:
            # Move to start of next valid workday
            while True:
                time += datetime.timedelta(days=1)
                if time.weekday() in self.workdays:
                    time = datetime.datetime.combine(time.date(), self.workday_start_time)
                    break
        elif time.time() < self.workday_start_time:
            # Move to start of current workday
            time = datetime.datetime.combine(time.date(), self.workday_start_time)
        return time
    
    def calculate_job_end_time(self, start_time: datetime.datetime, duration: datetime.timedelta) -> datetime.datetime:
        remaining_duration = duration
        current_time = start_time

        while remaining_duration > datetime.timedelta(0):
            # Determine the end of the current workday
            workday_end = datetime.datetime.combine(current_time.date(), self.workday_end_time)
            time_available = workday_end - current_time

            if time_available >= remaining_duration:
                # Job can be completed within current workday
                return current_time + remaining_duration
            else:
                # Move to next workday and reduce remaining duration
                remaining_duration -= time_available
                current_time = self.get_next_working_time(workday_end + datetime.timedelta(seconds=1))
        return current_time

    def is_within_working_hours(self, time: datetime.datetime) -> bool:
        return (
            time.weekday() in self.workdays and
            self.workday_start_time <= time.time() < self.workday_end_time
        )

    def calculate_cumulative_scheduled_times(self) -> Dict[str, datetime.timedelta]:
        cumulative_times = {equip_id: datetime.timedelta() for equip_id in self.equipment.keys()}
        for job in self.schedule:
            equip_id = job.equipment_id
            job_duration = job.scheduled_end_time - job.scheduled_start_time
            cumulative_times[equip_id] += job_duration
        return cumulative_times

    def evaluate_job_impact(self, job: Job) -> datetime.timedelta:
        # Simulate scheduling the job
        # Note: To ensure that this simulation does not alter the actual schedule or resources, we make copies of the necessary data structures
        simulated_cumulative_times = self.calculate_cumulative_scheduled_times()

        # Calculate proposed start and end times
        proposed_start_time = self.get_next_working_time(self.current_time)
        proposed_end_time = self.calculate_job_end_time(proposed_start_time, job.duration)

        # Add the job's duration to the cumulative time of its equipment
        equip_id = job.equipment_id
        job_duration = proposed_end_time - proposed_start_time
        simulated_cumulative_times[equip_id] += job_duration

        # Return the maximum cumulative scheduled time after adding this job
        max_cumulative_time = max(simulated_cumulative_times.values())
        return max_cumulative_time

    def select_best_job(self, feasible_jobs: List[Job]) -> Job:
        # Get the current maximum cumulative scheduled time
        current_cumulative_times = self.calculate_cumulative_scheduled_times()
        current_max_cumulative_time = max(current_cumulative_times.values())

        # Initialize variables to track the best job
        best_job = None
        least_increase = None

        for job in feasible_jobs:
            # Evaluate the impact of scheduling this job
            new_max_cumulative_time = self.evaluate_job_impact(job)
            increase = new_max_cumulative_time - current_max_cumulative_time

            if least_increase is None or increase < least_increase:
                least_increase = increase
                best_job = job

        return best_job

    def get_unfeasibility_reason(self, job: Job) -> str:
        # This function can be expanded to provide detailed reasons
        if not job.is_ready(self.jobs):
            return "Predecessor jobs not completed."
        # Additional checks can be added here
        return "Resource constraints or scheduling window exceeded."

    # Output

    def print_schedule(self):
        print("Scheduled Jobs:")
        for job in self.schedule:
            print(f"Job ID: {job.job_id}, Equipment: {job.equipment_id}, Start: {job.scheduled_start_time}, End: {job.scheduled_end_time}, Technicians: {[tech.tech_id for tech in job.assigned_technicians]}")

        if self.unscheduled_jobs:
            print("\nUnscheduled Jobs:")
            for job, reason in self.unscheduled_jobs:
                print(f"Job ID: {job.job_id}, Reason: {reason}")

# Running the scheduler
# if __name__ == '__main__':
#     # Load data
#     data = load_and_validate_data()
#     scheduler = Scheduler(data, workday_start="08:00", workday_end="17:00", workdays=[0,1,2,3,4])
#     scheduler.run()
#     scheduler.print_schedule()

#     # Prepare the schedule data to save
#     schedule_data = {
#         'scheduled_jobs': {},
#         'unscheduled_jobs': []
#     }

#     # Organize scheduled jobs by equipment_id
#     for job in scheduler.schedule:
#         job_dict = {
#             'job_id': job.job_id,
#             'description': job.description,
#             'equipment_id': job.equipment_id,
#             'scheduled_start_time': job.scheduled_start_time.strftime('%Y-%m-%dT%H:%M:%S'),
#             'scheduled_end_time': job.scheduled_end_time.strftime('%Y-%m-%dT%H:%M:%S'),
#             'assigned_technicians': [tech.tech_id for tech in job.assigned_technicians]
#         }
#         equipment_id = job.equipment_id
#         schedule_data['scheduled_jobs'].setdefault(equipment_id, []).append(job_dict)

#     # Add unscheduled jobs with reasons
#     for job, reason in scheduler.unscheduled_jobs:
#         unscheduled_job_dict = {
#             'job_id': job.job_id,
#             'description': job.description,
#             'equipment_id': job.equipment_id,
#             'reason': reason
#         }
#         schedule_data['unscheduled_jobs'].append(unscheduled_job_dict)

#     # Save the schedule data to a JSON file
#     with open('data/schedule.json', 'w') as f:
#         json.dump(schedule_data, f, indent=4)

#     # # Generate Gantt chart
#     # generate_gantt_chart(scheduler.schedule)

#     # Generate Gantt chart
#     generate_gantt_chart(
#         scheduler.schedule,
#         scheduler.workday_start_time,
#         scheduler.workday_end_time,
#         scheduler.workdays,
#         save_fig=True
#     )

#     # Generate metrics report
#     generate_report(scheduler)

#     # Save reports to CSV and Excel
#     save_report_to_csv(scheduler)
#     save_report_to_excel(scheduler)

#     # Generate visualizations
#     generate_visualizations(scheduler)

# At the end of scheduler.py

if __name__ == '__main__':
    # Load data
    data = load_and_validate_data()
    scheduler = Scheduler(data, workday_start="08:00", workday_end="17:00", workdays=[0,1,2,3,4])
    scheduler.run()
    scheduler.print_schedule()

    # Prepare the schedule data
    schedule_data = {
        'scheduled_jobs': [],
        'unscheduled_jobs': []
    }

    # Organize scheduled jobs
    for job in scheduler.schedule:
        job_dict = {
            'job_id': job.job_id,
            'description': job.description,
            'equipment_id': job.equipment_id,
            'scheduled_start_time': job.scheduled_start_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'scheduled_end_time': job.scheduled_end_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'assigned_technicians': [tech.tech_id for tech in job.assigned_technicians]
        }
        schedule_data['scheduled_jobs'].append(job_dict)

    # Add unscheduled jobs with reasons
    for job, reason in scheduler.unscheduled_jobs:
        unscheduled_job_dict = {
            'job_id': job.job_id,
            'description': job.description,
            'equipment_id': job.equipment_id,
            'reason': reason
        }
        schedule_data['unscheduled_jobs'].append(unscheduled_job_dict)

    # Save the schedule data to a JSON file
    with open('data/schedule.json', 'w') as f:
        json.dump(schedule_data, f, indent=4)

    # Generate Gantt chart
    generate_gantt_chart(
        schedule_data['scheduled_jobs'],
        scheduler.workday_start_time,
        scheduler.workday_end_time,
        scheduler.workdays,
        save_fig=True
    )

    # Generate metrics report
    generate_report(scheduler)

    # Save reports to CSV and Excel
    save_report_to_csv(scheduler)
    save_report_to_excel(scheduler)

    # Generate visualizations
    generate_visualizations(scheduler)