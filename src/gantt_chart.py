# src/gantt_chart.py

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime
import os

def generate_gantt_chart(schedule, workday_start_time, workday_end_time, workdays, save_fig):
    # Group jobs by equipment
    equipment_jobs = {}
    for job in schedule:
        equip_id = job['equipment_id']
        equipment_jobs.setdefault(equip_id, []).append(job)
    
    # Sort equipment IDs for consistent plotting
    sorted_equipments = sorted(equipment_jobs.keys())
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Assign a y position to each equipment
    y_label_positions = []
    y_labels = []
    
    for idx, equip_id in enumerate(sorted_equipments):
        jobs = equipment_jobs[equip_id]
        for job in jobs:
            # Split the job into working hour segments
            segments = split_job_into_working_hours(job, workday_start_time, workday_end_time, workdays)
            for segment in segments:
                start = mdates.date2num(segment['start'])
                end = mdates.date2num(segment['end'])
                duration = end - start
                # Plot the bar on the y-position corresponding to the equipment
                ax.barh(idx, duration, left=start, height=0.5, align='center', edgecolor='black', color='skyblue')
                # Add job labels inside the bars
                ax.text(start + duration / 2, idx, job['job_id'], ha='center', va='center', color='white', fontsize=8)
        y_label_positions.append(idx)
        y_labels.append(equip_id)
    
    # Set y-axis labels to equipment IDs
    ax.set_yticks(y_label_positions)
    ax.set_yticklabels(y_labels)
    
    # Format the x-axis for dates
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    
    # Labels and title
    ax.set_xlabel('Time')
    ax.set_ylabel('Equipment ID')
    ax.set_title('Maintenance Schedule Gantt Chart')
    
    plt.tight_layout()
    
    # Save the figure if save_fig is True
    if save_fig:
        # Ensure the directory exists
        images_dir = os.path.join('static', 'images')
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)
        plt.savefig(os.path.join(images_dir, 'gantt_chart.png'))
        plt.close()
    else:
        plt.show()

def split_job_into_working_hours(job, workday_start_time, workday_end_time, workdays):
    segments = []
    start_time = datetime.datetime.strptime(job['scheduled_start_time'], '%Y-%m-%dT%H:%M:%S')
    end_time = datetime.datetime.strptime(job['scheduled_end_time'], '%Y-%m-%dT%H:%M:%S')
    current_time = start_time

    while current_time < end_time:
        if current_time.weekday() in workdays:
            workday_start = datetime.datetime.combine(current_time.date(), workday_start_time)
            workday_end = datetime.datetime.combine(current_time.date(), workday_end_time)

            # If current time is after workday end, move to next day
            if current_time >= workday_end:
                current_time = workday_start + datetime.timedelta(days=1)
                continue

            segment_start = max(current_time, workday_start)
            segment_end = min(end_time, workday_end)

            if segment_start < segment_end:
                segments.append({'start': segment_start, 'end': segment_end})

            # Move to the end of the workday
            current_time = workday_end
        else:
            # Move to the start of the next workday
            next_day = current_time + datetime.timedelta(days=1)
            current_time = datetime.datetime.combine(next_day.date(), workday_start_time)

    return segments

if __name__ == '__main__':
    # Test code
    # Create sample jobs
    sample_schedule = [
        {
            'job_id': 'JOB001',
            'equipment_id': 'EQUIP001',
            'scheduled_start_time': '2023-12-01T16:00:00',
            'scheduled_end_time': '2023-12-02T10:00:00',
            'assigned_technicians': ['TECH001', 'TECH002']
        },
        {
            'job_id': 'JOB002',
            'equipment_id': 'EQUIP001',
            'scheduled_start_time': '2023-12-02T12:00:00',
            'scheduled_end_time': '2023-12-03T14:00:00',
            'assigned_technicians': ['TECH002']
        },
        {
            'job_id': 'JOB003',
            'equipment_id': 'EQUIP002',
            'scheduled_start_time': '2023-12-01T08:00:00',
            'scheduled_end_time': '2023-12-01T12:00:00',
            'assigned_technicians': ['TECH001']
        },
    ]
    
    workday_start_time = datetime.time(8, 0)
    workday_end_time = datetime.time(17, 0)
    workdays = {0, 1, 2, 3, 4}  # Monday to Friday
    
    generate_gantt_chart(sample_schedule, workday_start_time, workday_end_time, workdays, save_fig=True)
