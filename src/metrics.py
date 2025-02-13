# src/metrics.py

from datetime import datetime, timedelta
import csv
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Utilisation

def calculate_total_working_time(start_time: datetime, end_time: datetime, entity) -> float:
    total_time = 0.0
    current_time = start_time

    while current_time < end_time:
        # Check if current day is a working day
        if current_time.weekday() in entity.workdays:
            workday_start = datetime.combine(current_time.date(), entity.workday_start_time)
            workday_end = datetime.combine(current_time.date(), entity.workday_end_time)

            # If current time is after workday end, move to the start of the next workday
            if current_time >= workday_end:
                next_day = current_time.date() + timedelta(days=1)
                current_time = datetime.combine(next_day, entity.workday_start_time)
                continue

            # Calculate effective working period for the current day
            effective_start = max(current_time, workday_start)
            effective_end = min(workday_end, end_time)

            if effective_start < effective_end:
                time_available = (effective_end - effective_start).total_seconds()
                total_time += time_available

            # Move current_time to the end of the workday
            current_time = workday_end
        else:
            # Move current_time to the start of the next workday
            next_day = current_time.date() + timedelta(days=1)
            current_time = datetime.combine(next_day, entity.workday_start_time)

    return total_time

def calculate_equipment_utilization(scheduler):
    equipment_utilization = {}
    for equipment in scheduler.equipment.values():
        total_scheduled_time = sum(
            (min(end_time, scheduler.t_end) - max(start_time, scheduler.t_start)).total_seconds()
            for start_time, end_time, _ in equipment.schedule
        )
        total_working_time = calculate_total_working_time(scheduler.t_start, scheduler.t_end, equipment)
        utilization = (total_scheduled_time / total_working_time) * 100 if total_working_time > 0 else 0
        equipment_utilization[equipment.equipment_id] = utilization
    return equipment_utilization

def calculate_tool_utilization(scheduler):
    tool_utilization = {}
    for tool in scheduler.tools.values():
        total_reserved_time = 0.0
        total_capacity_time = 0.0
        current_date = scheduler.t_start.date()
        while datetime.combine(current_date, scheduler.workday_start_time) < scheduler.t_end:
            if current_date.weekday() in scheduler.workdays:
                workday_start = datetime.combine(current_date, scheduler.workday_start_time)
                workday_end = datetime.combine(current_date, scheduler.workday_end_time)
                time_available = (min(workday_end, scheduler.t_end) - max(workday_start, scheduler.t_start)).total_seconds()
                total_capacity_time += time_available * tool.total_quantity
            current_date += timedelta(days=1)
        for reservation in tool.reservations:
            reserved_start, reserved_end, quantity_reserved = reservation
            duration = (min(reserved_end, scheduler.t_end) - max(reserved_start, scheduler.t_start)).total_seconds()
            total_reserved_time += duration * quantity_reserved
        utilization = (total_reserved_time / total_capacity_time) * 100 if total_capacity_time > 0 else 0
        tool_utilization[tool.tool_id] = utilization
    return tool_utilization

def calculate_material_consumption(scheduler):
    material_consumption = {}
    for material in scheduler.materials.values():
        consumption_percentage = (material.quantity_used / material.total_quantity) * 100 if material.total_quantity > 0 else 0
        material_consumption[material.material_id] = consumption_percentage
    return material_consumption

# Cost Analysis functions

def calculate_job_costs(scheduler):
    job_costs = {}
    for job in scheduler.schedule:
        total_cost = 0.0
        for tech in job.assigned_technicians:
            hourly_rate = tech.hourly_rate
            # Calculate actual working time
            working_time = 0.0
            current_time = job.scheduled_start_time
            while current_time < job.scheduled_end_time:
                if current_time.weekday() in tech.workdays:
                    workday_start = datetime.combine(current_time.date(), tech.workday_start_time)
                    workday_end = datetime.combine(current_time.date(), tech.workday_end_time)

                    # If current_time is after workday_end, move to next day
                    if current_time >= workday_end:
                        current_time = datetime.combine(current_time.date() + timedelta(days=1), tech.workday_start_time)
                        continue

                    effective_start = max(current_time, workday_start)
                    effective_end = min(job.scheduled_end_time, workday_end)
                    if effective_start < effective_end:
                        duration = (effective_end - effective_start).total_seconds() / 3600
                        working_time += duration

                    # Move current_time to workday_end to avoid re-processing the same period
                    current_time = workday_end
                else:
                    # Move to the next workday start time
                    next_workday = current_time.date() + timedelta(days=1)
                    current_time = datetime.combine(next_workday, tech.workday_start_time)
            total_cost += working_time * hourly_rate
        job_costs[job.job_id] = total_cost
    return job_costs

def calculate_technician_costs(scheduler):
    technician_costs = {}
    for tech in scheduler.technicians.values():
        total_cost = 0.0
        for assignment in tech.assignments:
            assigned_start, assigned_end, _ = assignment
            working_time = 0.0
            current_time = assigned_start
            while current_time < assigned_end:
                if current_time.weekday() in tech.workdays:
                    workday_start = datetime.combine(current_time.date(), tech.workday_start_time)
                    workday_end = datetime.combine(current_time.date(), tech.workday_end_time)

                    # If current_time is after workday_end, move to next day
                    if current_time >= workday_end:
                        current_time = datetime.combine(current_time.date() + timedelta(days=1), tech.workday_start_time)
                        continue

                    effective_start = max(current_time, workday_start)
                    effective_end = min(assigned_end, workday_end)
                    if effective_start < effective_end:
                        duration = (effective_end - effective_start).total_seconds() / 3600
                        working_time += duration

                    # Move current_time to workday_end to avoid re-processing the same period
                    current_time = workday_end
                else:
                    # Move to the next workday start time
                    next_workday = current_time.date() + timedelta(days=1)
                    current_time = datetime.combine(next_workday, tech.workday_start_time)
            total_cost += working_time * tech.hourly_rate
        technician_costs[tech.tech_id] = total_cost
    return technician_costs


def calculate_total_labor_cost(technician_costs):
    # Determine overall labour cost
    return sum(technician_costs.values())

# Schedule Efficiency Metrics

def calculate_total_scheduled_jobs(scheduler):
    if not scheduler.schedule:
        return 0
    return len(scheduler.schedule)

def calculate_total_completion_time(scheduler):
    if not scheduler.schedule:
        return 0
    start_times = [job.scheduled_start_time for job in scheduler.schedule]
    end_times = [job.scheduled_end_time for job in scheduler.schedule]
    total_completion_time = max(end_times) - min(start_times)
    return total_completion_time

def calculate_average_job_duration(scheduler):
    if not scheduler.schedule:
        return 0
    total_duration = sum((job.scheduled_end_time - job.scheduled_start_time).total_seconds() for job in scheduler.schedule)
    average_duration = total_duration / len(scheduler.schedule)
    return average_duration

def calculate_equipment_idle_times(scheduler):
    equipment_idle_times = {}
    for equipment in scheduler.equipment.values():
        schedule = sorted(equipment.schedule, key=lambda x: x[0])
        idle_time = 0.0
        current_time = scheduler.t_start
        for start_time, end_time, _ in schedule:
            if current_time < start_time:
                idle_duration = (start_time - current_time).total_seconds()
                idle_time += idle_duration
            current_time = max(current_time, end_time)
        # Account for idle time after last scheduled job
        if current_time < scheduler.t_end:
            idle_duration = (scheduler.t_end - current_time).total_seconds()
            idle_time += idle_duration
        equipment_idle_times[equipment.equipment_id] = idle_time
    return equipment_idle_times

# Generate and save reports

def generate_report(scheduler):
    print("\nTechnician Utilization:")
    for tech in scheduler.technicians.values():
        total_assigned_time = sum(
            (min(assignment[1], scheduler.t_end) - max(assignment[0], scheduler.t_start)).total_seconds()
            for assignment in tech.assignments
        )
        total_working_time = calculate_total_working_time(scheduler.t_start, scheduler.t_end, tech)
        utilization = (total_assigned_time / total_working_time) * 100 if total_working_time > 0 else 0
        print(f"Technician {tech.tech_id} Utilization: {utilization:.2f}%")

    equipment_utilization = calculate_equipment_utilization(scheduler)
    print("\nEquipment Utilization:")
    for equip_id, utilization in equipment_utilization.items():
        print(f"Equipment {equip_id} Utilization: {utilization:.2f}%")

    tool_utilization = calculate_tool_utilization(scheduler)
    print("\nTool Utilization:")
    for tool_id, utilization in tool_utilization.items():
        print(f"Tool {tool_id} Utilization: {utilization:.2f}%")

    material_consumption = calculate_material_consumption(scheduler)
    print("\nMaterial Consumption:")
    for material_id, consumption in material_consumption.items():
        print(f"Material {material_id} Consumption: {consumption:.2f}%")

    job_costs = calculate_job_costs(scheduler)
    technician_costs = calculate_technician_costs(scheduler)
    total_labor_cost = calculate_total_labor_cost(technician_costs)

    print("\nJob Costs:")
    for job_id, cost in job_costs.items():
        print(f"Job {job_id} Cost: ${cost:.2f}")

    print("\nTechnician Costs:")
    for tech_id, cost in technician_costs.items():
        print(f"Technician {tech_id} Total Cost: ${cost:.2f}")

    print(f"\nTotal Labor Cost: ${total_labor_cost:.2f}")

    total_completion_time = calculate_total_completion_time(scheduler)
    average_job_duration = calculate_average_job_duration(scheduler)
    print(f"\nTotal Completion Time: {total_completion_time}")
    print(f"Average Job Duration: {average_job_duration / 3600:.2f} hours")

    equipment_idle_times = calculate_equipment_idle_times(scheduler)
    print("\nEquipment Idle Times:")
    for equip_id, idle_time in equipment_idle_times.items():
        idle_hours = idle_time / 3600
        print(f"Equipment {equip_id} Idle Time: {idle_hours:.2f} hours")

def save_report_to_csv(scheduler):
    # Technician Utilization
    with open('technician_utilization.csv', 'w', newline='') as csvfile:
        fieldnames = ['Technician ID', 'Utilization (%)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for tech in scheduler.technicians.values():
            total_assigned_time = sum(
                (min(assignment[1], scheduler.t_end) - max(assignment[0], scheduler.t_start)).total_seconds()
                for assignment in tech.assignments
            )
            total_working_time = calculate_total_working_time(scheduler.t_start, scheduler.t_end, tech)
            utilization = (total_assigned_time / total_working_time) * 100 if total_working_time > 0 else 0
            writer.writerow({'Technician ID': tech.tech_id, 'Utilization (%)': f"{utilization:.2f}"})

    # Equipment Utilization
    equipment_utilization = calculate_equipment_utilization(scheduler)
    with open('equipment_utilization.csv', 'w', newline='') as csvfile:
        fieldnames = ['Equipment ID', 'Utilization (%)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for equip_id, utilization in equipment_utilization.items():
            writer.writerow({'Equipment ID': equip_id, 'Utilization (%)': f"{utilization:.2f}"})

    # Tool Utilization
    tool_utilization = calculate_tool_utilization(scheduler)
    with open('tool_utilization.csv', 'w', newline='') as csvfile:
        fieldnames = ['Tool ID', 'Utilization (%)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for tool_id, utilization in tool_utilization.items():
            writer.writerow({'Tool ID': tool_id, 'Utilization (%)': f"{utilization:.2f}"})

    # Material Consumption
    material_consumption = calculate_material_consumption(scheduler)
    with open('material_consumption.csv', 'w', newline='') as csvfile:
        fieldnames = ['Material ID', 'Consumption (%)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for material_id, consumption in material_consumption.items():
            writer.writerow({'Material ID': material_id, 'Consumption (%)': f"{consumption:.2f}"})

    # Job Costs
    job_costs = calculate_job_costs(scheduler)
    with open('job_costs.csv', 'w', newline='') as csvfile:
        fieldnames = ['Job ID', 'Cost ($)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for job_id, cost in job_costs.items():
            writer.writerow({'Job ID': job_id, 'Cost ($)': f"{cost:.2f}"})

    # Technician Costs
    technician_costs = calculate_technician_costs(scheduler)
    with open('technician_costs.csv', 'w', newline='') as csvfile:
        fieldnames = ['Technician ID', 'Total Cost ($)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for tech_id, cost in technician_costs.items():
            writer.writerow({'Technician ID': tech_id, 'Total Cost ($)': f"{cost:.2f}"})

    # Total Labor Cost
    total_labor_cost = calculate_total_labor_cost(technician_costs)
    with open('total_labor_cost.csv', 'w', newline='') as csvfile:
        fieldnames = ['Total Labor Cost ($)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({'Total Labor Cost ($)': f"{total_labor_cost:.2f}"})

    # Schedule Efficiency Metrics
    total_completion_time = calculate_total_completion_time(scheduler)
    average_job_duration = calculate_average_job_duration(scheduler)
    with open('schedule_efficiency.csv', 'w', newline='') as csvfile:
        fieldnames = ['Metric', 'Value']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({'Metric': 'Total Completion Time (hours)', 'Value': f"{total_completion_time.total_seconds() / 3600:.2f}"})
        writer.writerow({'Metric': 'Average Job Duration (hours)', 'Value': f"{average_job_duration / 3600:.2f}"})

    # Equipment Idle Times
    equipment_idle_times = calculate_equipment_idle_times(scheduler)
    with open('equipment_idle_times.csv', 'w', newline='') as csvfile:
        fieldnames = ['Equipment ID', 'Idle Time (hours)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for equip_id, idle_time in equipment_idle_times.items():
            idle_hours = idle_time / 3600
            writer.writerow({'Equipment ID': equip_id, 'Idle Time (hours)': f"{idle_hours:.2f}"})

def save_report_to_excel(scheduler):
    writer = pd.ExcelWriter('scheduler_report.xlsx', engine='xlsxwriter')
    workbook = writer.book

    # Technician Utilization
    technician_data = []
    for tech in scheduler.technicians.values():
        total_assigned_time = sum(
            (min(assignment[1], scheduler.t_end) - max(assignment[0], scheduler.t_start)).total_seconds()
            for assignment in tech.assignments
        )
        total_working_time = calculate_total_working_time(scheduler.t_start, scheduler.t_end, tech)
        utilization = (total_assigned_time / total_working_time) * 100 if total_working_time > 0 else 0
        technician_data.append({'Technician ID': tech.tech_id, 'Utilization (%)': utilization})
    df_technicians = pd.DataFrame(technician_data)
    df_technicians.to_excel(writer, sheet_name='Technician Utilization', index=False)

    # Equipment Utilization
    equipment_utilization = calculate_equipment_utilization(scheduler)
    equipment_data = [{'Equipment ID': equip_id, 'Utilization (%)': utilization} for equip_id, utilization in equipment_utilization.items()]
    df_equipment = pd.DataFrame(equipment_data)
    df_equipment.to_excel(writer, sheet_name='Equipment Utilization', index=False)

    # Tool Utilization
    tool_utilization = calculate_tool_utilization(scheduler)
    tool_data = [{'Tool ID': tool_id, 'Utilization (%)': utilization} for tool_id, utilization in tool_utilization.items()]
    df_tools = pd.DataFrame(tool_data)
    df_tools.to_excel(writer, sheet_name='Tool Utilization', index=False)

    # Material Consumption
    material_consumption = calculate_material_consumption(scheduler)
    material_data = [{'Material ID': material_id, 'Consumption (%)': consumption} for material_id, consumption in material_consumption.items()]
    df_materials = pd.DataFrame(material_data)
    df_materials.to_excel(writer, sheet_name='Material Consumption', index=False)

    # Job Costs
    job_costs = calculate_job_costs(scheduler)
    job_data = [{'Job ID': job_id, 'Cost ($)': cost} for job_id, cost in job_costs.items()]
    df_jobs = pd.DataFrame(job_data)
    df_jobs.to_excel(writer, sheet_name='Job Costs', index=False)

    # Technician Costs
    technician_costs = calculate_technician_costs(scheduler)
    tech_cost_data = [{'Technician ID': tech_id, 'Total Cost ($)': cost} for tech_id, cost in technician_costs.items()]
    df_tech_costs = pd.DataFrame(tech_cost_data)
    df_tech_costs.to_excel(writer, sheet_name='Technician Costs', index=False)

    # Total Labor Cost
    total_labor_cost = calculate_total_labor_cost(technician_costs)
    df_total_cost = pd.DataFrame([{'Total Labor Cost ($)': total_labor_cost}])
    df_total_cost.to_excel(writer, sheet_name='Total Labor Cost', index=False)

    # Schedule Efficiency Metrics
    total_completion_time = calculate_total_completion_time(scheduler)
    average_job_duration = calculate_average_job_duration(scheduler)
    efficiency_data = [
        {'Metric': 'Total Completion Time (hours)', 'Value': total_completion_time.total_seconds() / 3600},
        {'Metric': 'Average Job Duration (hours)', 'Value': average_job_duration / 3600},
    ]
    df_efficiency = pd.DataFrame(efficiency_data)
    df_efficiency.to_excel(writer, sheet_name='Schedule Efficiency', index=False)

    # Equipment Idle Times
    equipment_idle_times = calculate_equipment_idle_times(scheduler)
    idle_times_data = [{'Equipment ID': equip_id, 'Idle Time (hours)': idle_time / 3600} for equip_id, idle_time in equipment_idle_times.items()]
    df_idle_times = pd.DataFrame(idle_times_data)
    df_idle_times.to_excel(writer, sheet_name='Equipment Idle Times', index=False)

    # Insert images after saving dfs
    worksheet = workbook.add_worksheet('Visualizations')
    worksheet.insert_image('A1', 'technician_utilization.png')
    worksheet.insert_image('A20', 'equipment_utilization.png')
    # i will add more images as needed...

    writer.close()

# Visualisations

def plot_technician_utilization(scheduler):
    technician_utilization = []
    technician_ids = []
    for tech in scheduler.technicians.values():
        total_assigned_time = sum(
            (min(assignment[1], scheduler.t_end) - max(assignment[0], scheduler.t_start)).total_seconds()
            for assignment in tech.assignments
        )
        total_working_time = calculate_total_working_time(scheduler.t_start, scheduler.t_end, tech)
        utilization = (total_assigned_time / total_working_time) * 100 if total_working_time > 0 else 0
        technician_utilization.append(utilization)
        technician_ids.append(tech.tech_id)

    plt.figure(figsize=(10, 6))
    plt.bar(technician_ids, technician_utilization, color='skyblue')
    plt.xlabel('Technician ID')
    plt.ylabel('Utilization (%)')
    plt.title('Technician Utilization')
    plt.ylim(0, 100)
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('technician_utilization.png')
    plt.close()

def plot_equipment_utilization(scheduler):
    equipment_utilization = calculate_equipment_utilization(scheduler)
    equipment_ids = list(equipment_utilization.keys())
    utilization_values = list(equipment_utilization.values())

    plt.figure(figsize=(10, 6))
    plt.bar(equipment_ids, utilization_values, color='lightgreen')
    plt.xlabel('Equipment ID')
    plt.ylabel('Utilization (%)')
    plt.title('Equipment Utilization')
    plt.ylim(0, 100)
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('equipment_utilization.png')
    plt.close()

def plot_tool_utilization(scheduler):
    tool_utilization = calculate_tool_utilization(scheduler)
    tool_ids = list(tool_utilization.keys())
    utilization_values = list(tool_utilization.values())

    plt.figure(figsize=(10, 6))
    plt.bar(tool_ids, utilization_values, color='salmon')
    plt.xlabel('Tool ID')
    plt.ylabel('Utilization (%)')
    plt.title('Tool Utilization')
    plt.ylim(0, 100)
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('tool_utilization.png')
    plt.close()

def plot_material_consumption(scheduler):
    material_consumption = calculate_material_consumption(scheduler)
    material_ids = list(material_consumption.keys())
    consumption_values = list(material_consumption.values())

    plt.figure(figsize=(8, 8))
    plt.pie(consumption_values, labels=material_ids, autopct='%1.1f%%', startangle=140)
    plt.title('Material Consumption')
    plt.tight_layout()
    plt.savefig('material_consumption.png')
    plt.close()

def plot_job_costs(scheduler):
    job_costs = calculate_job_costs(scheduler)
    job_ids = list(job_costs.keys())
    costs = list(job_costs.values())

    plt.figure(figsize=(12, 6))
    plt.bar(job_ids, costs, color='orchid')
    plt.xlabel('Job ID')
    plt.ylabel('Cost ($)')
    plt.title('Job Costs')
    plt.xticks(rotation=45)
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('job_costs.png')
    plt.close()

def plot_technician_costs(scheduler):
    technician_costs = calculate_technician_costs(scheduler)
    tech_ids = list(technician_costs.keys())
    costs = list(technician_costs.values())

    plt.figure(figsize=(10, 6))
    plt.bar(tech_ids, costs, color='gold')
    plt.xlabel('Technician ID')
    plt.ylabel('Total Cost ($)')
    plt.title('Technician Costs')
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('technician_costs.png')
    plt.close()

def plot_job_durations(scheduler):
    job_durations = [
        (job.scheduled_end_time - job.scheduled_start_time).total_seconds() / 3600
        for job in scheduler.schedule
    ]

    plt.figure(figsize=(10, 6))
    plt.hist(job_durations, bins=range(0, int(max(job_durations)) + 2), color='steelblue', edgecolor='black')
    plt.xlabel('Job Duration (hours)')
    plt.ylabel('Number of Jobs')
    plt.title('Distribution of Job Durations')
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('job_durations.png')
    plt.close()

def plot_equipment_idle_times(scheduler):
    equipment_idle_times = calculate_equipment_idle_times(scheduler)
    equipment_ids = list(equipment_idle_times.keys())
    idle_times_hours = [idle_time / 3600 for idle_time in equipment_idle_times.values()]

    plt.figure(figsize=(10, 6))
    plt.bar(equipment_ids, idle_times_hours, color='lightcoral')
    plt.xlabel('Equipment ID')
    plt.ylabel('Idle Time (hours)')
    plt.title('Equipment Idle Times')
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig('equipment_idle_times.png')
    plt.close()

def generate_visualizations(scheduler):
    plot_technician_utilization(scheduler)
    plot_equipment_utilization(scheduler)
    plot_tool_utilization(scheduler)
    plot_material_consumption(scheduler)
    plot_job_costs(scheduler)
    plot_technician_costs(scheduler)
    plot_job_durations(scheduler)
    plot_equipment_idle_times(scheduler)

if __name__ == '__main__':
    # Test code
    # Create sample technicians and assignments
    class Technician:
        def __init__(self, tech_id, workday_start_time, workday_end_time, workdays):
            self.tech_id = tech_id
            self.workday_start_time = workday_start_time
            self.workday_end_time = workday_end_time
            self.workdays = set(workdays)
            self.assignments = []  # List of (start_time, end_time, job_id)

    class Scheduler:
        def __init__(self):
            self.t_start = datetime(2023, 12, 1, 8, 0)
            self.t_end = datetime(2023, 12, 7, 17, 0)
            self.technicians = {}

    # Create sample technicians
    tech1 = Technician('TECH001', datetime.strptime("08:00", "%H:%M").time(), datetime.strptime("17:00", "%H:%M").time(), [0,1,2,3,4])
    tech2 = Technician('TECH002', datetime.strptime("08:00", "%H:%M").time(), datetime.strptime("17:00", "%H:%M").time(), [0,1,2,3,4])

    # Assignments for technicians
    tech1.assignments = [
        (datetime(2023, 12, 1, 8, 0), datetime(2023, 12, 1, 12, 0), 'JOB001'),
        (datetime(2023, 12, 2, 8, 0), datetime(2023, 12, 2, 10, 0), 'JOB003'),
    ]
    tech2.assignments = [
        (datetime(2023, 12, 1, 12, 0), datetime(2023, 12, 1, 16, 0), 'JOB002'),
    ]

    # Create scheduler instance
    scheduler = Scheduler()
    scheduler.technicians['TECH001'] = tech1
    scheduler.technicians['TECH002'] = tech2

    # Run the report
    generate_report(scheduler)
