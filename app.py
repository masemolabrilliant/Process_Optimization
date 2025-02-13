# app.py

from flask import Flask, Response, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, SelectMultipleField, FieldList, FormField, SubmitField, FloatField, TextAreaField
from wtforms.validators import DataRequired, NumberRange
from werkzeug.utils import secure_filename

import plotly
import plotly.figure_factory as ff
import json
import os
import datetime
import time

# Import scheduler and metrics functions
from src.scheduler import Scheduler
from src.data_handler import load_and_validate_data
from src.metrics import (
    generate_report,
    calculate_equipment_utilization,
    calculate_tool_utilization,
    calculate_material_consumption,
    calculate_job_costs,
    calculate_technician_costs,
    calculate_total_labor_cost,
    calculate_total_scheduled_jobs,
    calculate_total_completion_time,
    calculate_average_job_duration,
    calculate_equipment_idle_times,
    generate_visualizations
)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'secret_key'  # To replace with secure key in production

# Data paths
DATA_DIR = 'data'
JOBS_FILE = os.path.join(DATA_DIR, 'jobs.json')
TECHNICIANS_FILE = os.path.join(DATA_DIR, 'technicians.json')
TOOLS_FILE = os.path.join(DATA_DIR, 'tools.json')
MATERIALS_FILE = os.path.join(DATA_DIR, 'materials.json')
EQUIPMENT_FILE = os.path.join(DATA_DIR, 'equipment.json')
SCHEDULE_FILE = os.path.join(DATA_DIR, 'schedule.json')
METRICS_FILE = os.path.join(DATA_DIR, 'metrics.json')

# Helper functions to load and save data
def load_data(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def save_data(data, file_path):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4, default=str)

# Function to run the scheduler and generate schedule and metrics
def run_scheduler():
    data = load_and_validate_data()
    scheduler = Scheduler(data, workday_start="08:00", workday_end="17:00", workdays=[0,1,2,3,4])
    scheduler.run()
    # Save the schedule to SCHEDULE_FILE
    schedule_data = []
    for job in scheduler.schedule:
        schedule_data.append({
            'job_id': job.job_id,
            'equipment_id': job.equipment_id,
            'scheduled_start_time': job.scheduled_start_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'scheduled_end_time': job.scheduled_end_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'assigned_technicians': [tech.tech_id for tech in job.assigned_technicians]
        })
    save_data(schedule_data, SCHEDULE_FILE)
    # Generate metrics and save to METRICS_FILE
    generate_report(scheduler)
    metrics = {
        'equipment_utilization': calculate_equipment_utilization(scheduler),
        'tool_utilization': calculate_tool_utilization(scheduler),
        'material_consumption': calculate_material_consumption(scheduler),
        'job_costs': calculate_job_costs(scheduler),
        'technician_costs': calculate_technician_costs(scheduler),
        'total_labor_cost': calculate_total_labor_cost(calculate_technician_costs(scheduler)),
        'total_scheduled_jobs': calculate_total_scheduled_jobs(scheduler),
        'total_completion_time': str(calculate_total_completion_time(scheduler)),
        'average_job_duration': calculate_average_job_duration(scheduler) / 3600,  # in hours
        'equipment_idle_times': calculate_equipment_idle_times(scheduler)
    }
    save_data(metrics, METRICS_FILE)
    
    # Generate visualizations
    generate_visualizations(scheduler)

# Routes and views

@app.route('/')
def index():
    return render_template('index.html')

# ----------------------------
# Tool Management Routes
# ----------------------------

class ToolRequirementForm(FlaskForm):
    tool_id = SelectField('Tool', validators=[DataRequired()])
    quantity = FloatField('Quantity', validators=[DataRequired(), NumberRange(min=0)])
    
# ----------------------------
# Materials Management Routes
# ----------------------------

class MaterialRequirementForm(FlaskForm):
    material_id = SelectField('Material', validators=[DataRequired()])
    quantity = FloatField('Quantity', validators=[DataRequired(), NumberRange(min=0)])


# ----------------------
# Job Management Routes
# ----------------------

class JobForm(FlaskForm):
    job_id = StringField('Job ID', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    duration = FloatField('Duration (hours)', validators=[DataRequired(), NumberRange(min=0)])
    equipment_id = SelectField('Equipment', validators=[DataRequired()])
    required_skills = SelectMultipleField('Required Skills', validators=[DataRequired()])
    precedence = SelectMultipleField('Precedence Jobs')
    required_tools = FieldList(FormField(ToolRequirementForm), min_entries=1)
    required_materials = FieldList(FormField(MaterialRequirementForm), min_entries=1)
    submit = SubmitField('Submit')

# view jobs route
@app.route('/jobs')
def view_jobs():
    jobs = load_data(JOBS_FILE)
    return render_template('jobs.html', jobs=jobs)

# add jobs route
@app.route('/jobs/add', methods=['GET', 'POST'])
def add_job():
    form = JobForm()
    if form.validate_on_submit():
        jobs = load_data(JOBS_FILE)
        # Parse required_tools and required_materials
        required_tools = []
        tools_input = form.required_tools.data.split(',')
        for tool in tools_input:
            try:
                tool_id, qty = tool.strip().split(':')
                required_tools.append({'tool_id': tool_id.strip(), 'quantity': int(qty.strip())})
            except ValueError:
                flash(f'Invalid tool format: "{tool}". Use tool_id:quantity.', 'danger')
                return render_template('add_job.html', form=form)
        
        required_materials = []
        materials_input = form.required_materials.data.split(',')
        for mat in materials_input:
            try:
                mat_id, qty = mat.strip().split(':')
                required_materials.append({'material_id': mat_id.strip(), 'quantity': float(qty.strip())})
            except ValueError:
                flash(f'Invalid material format: "{mat}". Use material_id:quantity.', 'danger')
                return render_template('add_job.html', form=form)
        
        new_job = {
            'job_id': form.job_id.data,
            'description': form.description.data,
            'duration': form.duration.data,
            'equipment_id': form.equipment_id.data,
            'required_skills': [skill.strip() for skill in form.required_skills.data.split(',')],
            'precedence': [p.strip() for p in form.precedence.data.split(',') if p.strip()],
            'required_tools': required_tools,
            'required_materials': required_materials
        }
        jobs.append(new_job)
        save_data(jobs, JOBS_FILE)
        flash('Job added successfully!', 'success')
        return redirect(url_for('view_jobs'))
    return render_template('add_job.html', form=form)

# edit jobs route
@app.route('/jobs/edit/<job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    jobs = load_data(JOBS_FILE)
    job = next((job for job in jobs if job['job_id'] == job_id), None)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('view_jobs'))
    form = JobForm(data=job)
    if form.validate_on_submit():
        # Parse required_tools and required_materials
        required_tools = []
        tools_input = form.required_tools.data.split(',')
        for tool in tools_input:
            try:
                tool_id, qty = tool.strip().split(':')
                required_tools.append({'tool_id': tool_id.strip(), 'quantity': int(qty.strip())})
            except ValueError:
                flash(f'Invalid tool format: "{tool}". Use tool_id:quantity.', 'danger')
                return render_template('edit_job.html', form=form, job_id=job_id)
        
        required_materials = []
        materials_input = form.required_materials.data.split(',')
        for mat in materials_input:
            try:
                mat_id, qty = mat.strip().split(':')
                required_materials.append({'material_id': mat_id.strip(), 'quantity': float(qty.strip())})
            except ValueError:
                flash(f'Invalid material format: "{mat}". Use material_id:quantity.', 'danger')
                return render_template('edit_job.html', form=form, job_id=job_id)
        
        job.update({
            'job_id': form.job_id.data,
            'description': form.description.data,
            'duration': form.duration.data,
            'equipment_id': form.equipment_id.data,
            'required_skills': [skill.strip() for skill in form.required_skills.data.split(',')],
            'precedence': [p.strip() for p in form.precedence.data.split(',') if p.strip()],
            'required_tools': required_tools,
            'required_materials': required_materials
        })
        save_data(jobs, JOBS_FILE)
        flash('Job updated successfully!', 'success')
        return redirect(url_for('view_jobs'))
    # Pre-fill required_tools and required_materials as strings
    form.required_tools.data = ','.join([f"{tool['tool_id']}:{tool['quantity']}" for tool in job['required_tools']])
    form.required_materials.data = ','.join([f"{mat['material_id']}:{mat['quantity']}" for mat in job['required_materials']])
    return render_template('edit_job.html', form=form, job_id=job_id)

# delete jobs route
@app.route('/jobs/delete/<job_id>', methods=['POST'])
def delete_job(job_id):
    jobs = load_data(JOBS_FILE)
    jobs = [job for job in jobs if job['job_id'] != job_id]
    save_data(jobs, JOBS_FILE)
    flash('Job deleted successfully!', 'success')
    return redirect(url_for('view_jobs'))

# upload jobs route
@app.route('/jobs/upload', methods=['GET', 'POST'])
def upload_jobs():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.json'):
            filename = secure_filename('jobs.json')
            file.save(os.path.join(DATA_DIR, filename))
            flash('Jobs uploaded successfully!', 'success')
            return redirect(url_for('view_jobs'))
        else:
            flash('Invalid file format. Please upload a JSON file.', 'danger')
    return render_template('upload_jobs.html')

# ----------------------------
# Technician Management Routes
# ----------------------------

class TechnicianForm(FlaskForm):
    tech_id = StringField('Technician ID', validators=[DataRequired()])
    name = StringField('Name', validators=[DataRequired()])
    hourly_rate = FloatField('Hourly Rate', validators=[DataRequired(), NumberRange(min=0)])
    skills = StringField('Skills (comma-separated)', validators=[DataRequired()])
    workdays = StringField('Workdays (comma-separated, 0=Mon, 6=Sun)', validators=[DataRequired()])
    workday_start = StringField('Workday Start Time (HH:MM)', validators=[DataRequired()])
    workday_end = StringField('Workday End Time (HH:MM)', validators=[DataRequired()])
    submit = SubmitField('Submit')

@app.route('/technicians')
def view_technicians():
    technicians = load_data(TECHNICIANS_FILE)
    return render_template('technicians.html', technicians=technicians)

@app.route('/technicians/add', methods=['GET', 'POST'])
def add_technician():
    form = TechnicianForm()
    if form.validate_on_submit():
        technicians = load_data(TECHNICIANS_FILE)
        # Parse workdays
        try:
            workdays = [int(day.strip()) for day in form.workdays.data.split(',')]
        except ValueError:
            flash('Invalid workday format. Use comma-separated integers (0=Mon, 6=Sun).', 'danger')
            return render_template('add_technician.html', form=form)
        
        new_technician = {
            'tech_id': form.tech_id.data,
            'name': form.name.data,
            'hourly_rate': form.hourly_rate.data,
            'skills': [skill.strip() for skill in form.skills.data.split(',')],
            'workdays': workdays,
            'workday_start': form.workday_start.data,
            'workday_end': form.workday_end.data
        }
        technicians.append(new_technician)
        save_data(technicians, TECHNICIANS_FILE)
        flash('Technician added successfully!', 'success')
        return redirect(url_for('view_technicians'))
    return render_template('add_technician.html', form=form)

@app.route('/technicians/edit/<tech_id>', methods=['GET', 'POST'])
def edit_technician(tech_id):
    technicians = load_data(TECHNICIANS_FILE)
    technician = next((tech for tech in technicians if tech['tech_id'] == tech_id), None)
    if not technician:
        flash('Technician not found.', 'danger')
        return redirect(url_for('view_technicians'))
    form = TechnicianForm(data=technician)
    if form.validate_on_submit():
        # Parse workdays
        try:
            workdays = [int(day.strip()) for day in form.workdays.data.split(',')]
        except ValueError:
            flash('Invalid workday format. Use comma-separated integers (0=Mon, 6=Sun).', 'danger')
            return render_template('edit_technician.html', form=form, tech_id=tech_id)
        
        technician.update({
            'tech_id': form.tech_id.data,
            'name': form.name.data,
            'hourly_rate': form.hourly_rate.data,
            'skills': [skill.strip() for skill in form.skills.data.split(',')],
            'workdays': workdays,
            'workday_start': form.workday_start.data,
            'workday_end': form.workday_end.data
        })
        save_data(technicians, TECHNICIANS_FILE)
        flash('Technician updated successfully!', 'success')
        return redirect(url_for('view_technicians'))
    # Pre-fill workdays, workday_start, workday_end as strings
    form.workdays.data = ','.join([str(day) for day in technician['workdays']])
    return render_template('edit_technician.html', form=form, tech_id=tech_id)

@app.route('/technicians/delete/<tech_id>', methods=['POST'])
def delete_technician(tech_id):
    technicians = load_data(TECHNICIANS_FILE)
    technicians = [tech for tech in technicians if tech['tech_id'] != tech_id]
    save_data(technicians, TECHNICIANS_FILE)
    flash('Technician deleted successfully!', 'success')
    return redirect(url_for('view_technicians'))

# ------------------------
# Schedule Display Route
# ------------------------

def split_job_into_working_hours(job, workday_start_time, workday_end_time, workdays):
    segments = []
    start_time = job.scheduled_start_time
    end_time = job.scheduled_end_time
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

def create_gantt_chart(schedule):
    segments = []
    workday_start_time = datetime.time(8, 0)  # To be adjusted as needed
    workday_end_time = datetime.time(17, 0)   # To be adjusted as needed
    workdays = {0, 1, 2, 3, 4}  # Assuming a Monday to Friday work week

    # Check if schedule is a dictionary with 'scheduled_jobs' key
    if isinstance(schedule, dict) and 'scheduled_jobs' in schedule:
        jobs = schedule['scheduled_jobs']
    else:
        jobs = schedule  # Assume it's a list of jobs

    for job in jobs:
        if not isinstance(job, dict):
            print(f"Unexpected job format: {job}")
            continue

        try:
            scheduled_start = datetime.datetime.strptime(job['scheduled_start_time'], '%Y-%m-%dT%H:%M:%S')
            scheduled_end = datetime.datetime.strptime(job['scheduled_end_time'], '%Y-%m-%dT%H:%M:%S')
        except KeyError:
            print(f"Missing start or end time for job: {job}")
            continue
        except ValueError:
            print(f"Invalid date format for job: {job}")
            continue

        job_obj = type('JobObj', (), {
            'job_id': job['job_id'],
            'equipment_id': job['equipment_id'],
            'scheduled_start_time': scheduled_start,
            'scheduled_end_time': scheduled_end
        })()

        job_segments = split_job_into_working_hours(job_obj, workday_start_time, workday_end_time, workdays)
        for segment in job_segments:
            segments.append({
                'Task': job_obj.equipment_id,
                'Start': segment['start'].strftime('%Y-%m-%d %H:%M:%S'),
                'Finish': segment['end'].strftime('%Y-%m-%d %H:%M:%S'),
                'Resource': job_obj.job_id,
                'Description': f"Job: {job['job_id']}<br>Start: {segment['start']}<br>End: {segment['end']}<br>Technicians: {', '.join(job['assigned_technicians'])}"
            })

    if not segments:
        return None

    unique_resources = sorted(set(item['Resource'] for item in segments))
    num_unique_resources = len(unique_resources)
   
    import plotly.express as px
    color_palette = px.colors.qualitative.Plotly * (num_unique_resources // len(px.colors.qualitative.Plotly) + 1)
    resource_color_map = {resource: color_palette[idx] for idx, resource in enumerate(unique_resources)}

    fig = ff.create_gantt(
        segments,
        index_col='Resource',
        show_colorbar=True,
        group_tasks=True,
        title='Maintenance Schedule',
        colors=resource_color_map,
    )

    fig.update_traces(
        hovertemplate='%{text}',
        text=[s['Description'] for s in segments]
    )

    return json.loads(json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder))

def create_gantt_chart_new(schedule):
    segments = []
    workday_start_time = datetime.time(8, 0)  # Adjust if needed
    workday_end_time = datetime.time(17, 0)   # Adjust if needed
    workdays = {0, 1, 2, 3, 4}  # Monday to Friday

    for job in schedule:
        try:
            scheduled_start = datetime.datetime.strptime(job['scheduled_start_time'], '%Y-%m-%dT%H:%M:%S')
            scheduled_end = datetime.datetime.strptime(job['scheduled_end_time'], '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            print(f"Invalid date format for job {job['job_id']}.")
            continue

        job_obj = type('JobObj', (), {
            'job_id': job['job_id'],
            'equipment_id': job['equipment_id'],
            'scheduled_start_time': scheduled_start,
            'scheduled_end_time': scheduled_end
        })()

        job_segments = split_job_into_working_hours(job_obj, workday_start_time, workday_end_time, workdays)
        for segment in job_segments:
            segments.append({
                'Task': job_obj.equipment_id,
                'Start': segment['start'].strftime('%Y-%m-%d %H:%M:%S'),
                'Finish': segment['end'].strftime('%Y-%m-%d %H:%M:%S'),
                'Resource': job_obj.job_id,
                'Description': f"Job: {job['job_id']}<br>Start: {segment['start']}<br>End: {segment['end']}<br>Technicians: {', '.join(job['assigned_technicians'])}"
            })

    if not segments:
        return None

    fig = ff.create_gantt(
        segments,
        index_col='Resource',
        show_colorbar=True,
        group_tasks=True,
        title='Maintenance Schedule'
    )

    fig.update_layout(autosize=True, width=1000, height=600)

    return json.loads(json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder))

@app.route('/schedule')
def view_schedule_old():
    if not os.path.exists(SCHEDULE_FILE):
        run_scheduler()
        flash('Initial schedule generated using the greedy algorithm.', 'info')
    
    schedule_data = load_data(SCHEDULE_FILE)
    
    # If schedule_data is a dictionary with 'scheduled_jobs', pass that to create_gantt_chart
    # Otherwise, pass the whole schedule_data
    if isinstance(schedule_data, dict) and 'scheduled_jobs' in schedule_data:
        gantt_fig = create_gantt_chart(schedule_data['scheduled_jobs'])
        schedule = schedule_data['scheduled_jobs']
    else:
        gantt_fig = create_gantt_chart(schedule_data)
        schedule = schedule_data

    equipment_data = load_data(EQUIPMENT_FILE)

    gantt_chart = json.dumps(gantt_fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    return render_template('schedule.html', gantt_chart=gantt_chart, schedule=schedule, equipment_data=equipment_data)

@app.route('/schedule')
def view_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        run_scheduler()
        flash('Initial schedule generated using the greedy algorithm.', 'info')
    
    schedule_data = load_data(SCHEDULE_FILE)
    
    if isinstance(schedule_data, dict) and 'scheduled_jobs' in schedule_data:
        gantt_chart = create_gantt_chart(schedule_data['scheduled_jobs'])
        schedule = schedule_data['scheduled_jobs']
    else:
        gantt_chart = create_gantt_chart(schedule_data)
        schedule = schedule_data

    equipment_data = load_data(EQUIPMENT_FILE)
    
    return render_template('schedule.html', gantt_chart=gantt_chart, schedule=schedule, equipment_data=equipment_data)

# Route to serve the Gantt chart image if generated using matplotlib
@app.route('/gantt_chart.png')
def gantt_chart_image():
    return send_from_directory('static/images', 'gantt_chart.png')

# ------------------------------
# Optimization Controls Route
# ------------------------------

class MILPOptimizationForm(FlaskForm):
    time_limit = IntegerField('Time Limit (seconds)', validators=[DataRequired(), NumberRange(min=1)])
    gap = FloatField('Optimality Gap', validators=[DataRequired(), NumberRange(min=0, max=1)])
    submit = SubmitField('Run MILP Optimization')

class GAOptimizationForm(FlaskForm):
    population_size = IntegerField('Population Size', validators=[DataRequired(), NumberRange(min=10)])
    generations = IntegerField('Number of Generations', validators=[DataRequired(), NumberRange(min=1)])
    mutation_rate = FloatField('Mutation Rate', validators=[DataRequired(), NumberRange(min=0, max=1)])
    crossover_rate = FloatField('Crossover Rate', validators=[DataRequired(), NumberRange(min=0, max=1)])
    submit = SubmitField('Run Genetic Algorithm Optimization')

class ORToolsOptimizationForm(FlaskForm):
    time_limit = IntegerField('Time Limit (seconds)', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Run OR-Tools Optimization')

@app.route('/optimize', methods=['GET', 'POST'])
def optimize():
    if request.method == 'POST':
        algorithm = request.form.get('algorithm')
        initial_schedule = load_data(SCHEDULE_FILE)
        start_time = time.time()
        
        if algorithm == 'MILP':
            from src.optimiser_milp import optimize_schedule as optimize_milp
            try:
                optimized_schedule = optimize_milp()
                flash('Optimization with MILP completed successfully!', 'success')
            except Exception as e:
                flash(f'Optimization failed: {str(e)}', 'danger')
                return redirect(url_for('optimize'))
        elif algorithm == 'GA':
            from src.optimiser_ga import optimize_schedule as optimize_ga
            try:
                optimized_schedule = optimize_ga()
                flash('Optimization with Genetic Algorithm completed successfully!', 'success')
            except Exception as e:
                flash(f'Optimization failed: {str(e)}', 'danger')
                return redirect(url_for('optimize'))
        elif algorithm == 'ORTOOLS':
            from src.optimiser_ortools import optimize_schedule as optimize_ortools
            try:
                optimized_schedule = optimize_ortools()
                flash('Optimization with Google OR-Tools completed successfully!', 'success')
            except Exception as e:
                flash(f'Optimization failed: {str(e)}', 'danger')
                return redirect(url_for('optimize'))
        elif algorithm == 'SA':
            # # To uncomment when Simulated Annealing optimization is implemented
            # from src.optimiser_sa import optimize_schedule as optimize_sa
            # try:
            #     optimized_schedule = optimize_sa()
            #     flash('Optimization with Simulated Annealing algorithm completed successfully!', 'success')
            # except Exception as e:
            #     flash(f'Optimization failed: {str(e)}', 'danger')
            flash('Simulated Annealing optimization algorithm is not yet implemented.', 'warning') # comment out after implementing SA
        else:
            flash('Invalid optimization algorithm selected.', 'danger')
            return redirect(url_for('optimize'))

        end_time = time.time()
        optimization_time = end_time - start_time

        # Save the optimized schedule
        optimized_schedule_file = os.path.join(DATA_DIR, f'optimized_schedule_{algorithm.lower()}.json')
        try:
            with open(optimized_schedule_file, 'w') as f:
                json.dump(optimized_schedule, f, indent=4)
            print(f"Saved optimized schedule to {optimized_schedule_file}")
        except Exception as e:
            print(f"Error saving optimized schedule: {str(e)}")
            flash(f'Error saving optimized schedule: {str(e)}', 'danger')
            return redirect(url_for('optimize'))

        # Save the optimization time
        optimization_time_file = os.path.join(DATA_DIR, f'optimization_time_{algorithm.lower()}.json')
        with open(optimization_time_file, 'w') as f:
            json.dump({'time': optimization_time}, f, indent=4)

        return redirect(url_for('optimization_results', algorithm=algorithm))

    return render_template('optimize.html')

# def save_optimized_schedule(schedule, algorithm):
#     filename = f'optimized_schedule_{algorithm.lower()}.json'
#     filepath = os.path.join(DATA_DIR, filename)
#     with open(filepath, 'w') as f:
#         json.dump(schedule, f, indent=4)
#     print(f"Saved optimized schedule to {filepath}")

# def save_optimization_time(optimization_time, algorithm):
#     filename = f'optimization_time_{algorithm.lower()}.json'
#     filepath = os.path.join(DATA_DIR, filename)
#     with open(filepath, 'w') as f:
#         json.dump({'time': optimization_time}, f, indent=4)

# View progress updates during optimisation

@app.route('/optimization_results/<algorithm>')
def optimization_results(algorithm):
    try:
        # Load the initial and optimized schedules
        initial_schedule = load_data(SCHEDULE_FILE)
        optimized_schedule_file = f'optimized_schedule_{algorithm.lower()}.json'
        optimized_schedule_raw = load_data(os.path.join(DATA_DIR, optimized_schedule_file))

        # If optimized_schedule is a string, try to parse it as JSON
        if isinstance(optimized_schedule_raw, str):
            try:
                optimized_schedule = json.loads(optimized_schedule_raw)
                print("Successfully parsed optimized_schedule from JSON string")
            except json.JSONDecodeError as e:
                print(f"Failed to parse optimized_schedule as JSON: {str(e)}")
                print(f"Raw content of optimized_schedule: {optimized_schedule_raw[:1000]}...")  # Print first 1000 characters
                raise ValueError(f"Invalid JSON in optimized schedule: {str(e)}")
        else:
            optimized_schedule = optimized_schedule_raw

        # Calculate makespan for both schedules
        initial_makespan = calculate_makespan(initial_schedule)
        optimized_makespan = calculate_makespan(optimized_schedule)
        makespan_reduction = (initial_makespan - optimized_makespan) / initial_makespan * 100

        # Generate Gantt charts
        initial_gantt = create_gantt_chart(initial_schedule)
        optimized_gantt = create_gantt_chart(optimized_schedule)

        # Load optimization time
        optimization_time_file = os.path.join(DATA_DIR, f'optimization_time_{algorithm.lower()}.json')
        if os.path.exists(optimization_time_file):
            optimization_time = load_data(optimization_time_file)
            optimization_time = optimization_time.get('time', 'N/A')
        else:
            optimization_time = 'N/A'

        return render_template('optimization_results.html', 
                               algorithm=algorithm,
                               optimization_time=optimization_time,
                               initial_makespan=initial_makespan,
                               optimized_makespan=optimized_makespan,
                               makespan_reduction=makespan_reduction,
                               initial_gantt=initial_gantt,
                               optimized_gantt=optimized_gantt,
                               initial_schedule=initial_schedule,
                               optimized_schedule=optimized_schedule)
    except Exception as e:
        print(f"Error in optimization_results: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error displaying optimization results: {str(e)}", 'danger')
        return redirect(url_for('optimize'))

def calculate_makespan(schedule):
    # print(f"Calculate makespan - Schedule type: {type(schedule)}")
    
    if isinstance(schedule, str):
        try:
            schedule = json.loads(schedule)
            print("Successfully parsed schedule from JSON string")
        except json.JSONDecodeError as e:
            print(f"Failed to parse schedule as JSON: {str(e)}")
            raise ValueError(f"Invalid JSON in schedule: {str(e)}")

    if isinstance(schedule, dict):
        if 'scheduled_jobs' in schedule:
            jobs = schedule['scheduled_jobs']
        elif any(isinstance(v, dict) and 'splits' in v for v in schedule.values()):
            jobs = [split for job in schedule.values() if isinstance(job, dict) and 'splits' in job for split in job['splits']]
        else:
            jobs = list(schedule.values())
    elif isinstance(schedule, list):
        jobs = schedule
    else:
        raise ValueError(f"Unexpected schedule format: {type(schedule)}")

    start_times = []
    end_times = []

    for job in jobs:
        if isinstance(job, dict):
            if 'scheduled_start_time' in job and 'scheduled_end_time' in job:
                start_times.append(datetime.datetime.strptime(job['scheduled_start_time'], '%Y-%m-%dT%H:%M:%S'))
                end_times.append(datetime.datetime.strptime(job['scheduled_end_time'], '%Y-%m-%dT%H:%M:%S'))
            elif 'Start' in job and 'Finish' in job:
                start_times.append(datetime.datetime.strptime(job['Start'], '%Y-%m-%d %H:%M:%S'))
                end_times.append(datetime.datetime.strptime(job['Finish'], '%Y-%m-%d %H:%M:%S'))
            else:
                print(f"Unexpected job format: {json.dumps(job, indent=2)}")
        elif isinstance(job, str):
            print(f"Skipping job (string): {job}")
            continue
        else:
            print(f"Unexpected job type: {type(job)}")

    if not start_times or not end_times:
        raise ValueError("No valid job times found in the schedule")

    return max(end_times) - min(start_times)

# -----------------------
# Metrics Reports Route
# -----------------------

@app.route('/metrics')
def view_metrics():
    # Check if metrics file exists
    if not os.path.exists(METRICS_FILE):
        # Run scheduler.py to generate initial metrics
        run_scheduler()
        flash('Metrics generated from the initial schedule.', 'info')
    metrics = load_data(METRICS_FILE)

    # Schedule type information
    if 'schedule_type' not in metrics:
        metrics['schedule_type'] = 'initial'  # or 'optimized' if it's from an optimized schedule

    # Ensure total_jobs is included in the metrics
    if 'total_jobs' not in metrics:
        # If it's not in the metrics file, we can calculate it here
        schedule = load_data(SCHEDULE_FILE)
        if isinstance(schedule, dict) and 'scheduled_jobs' in schedule:
            metrics['total_jobs'] = len(schedule['scheduled_jobs'])
        elif isinstance(schedule, list):
            metrics['total_jobs'] = len(schedule)
        else:
            metrics['total_jobs'] = 'N/A'

    return render_template('metrics.html', metrics=metrics)

# Route to serve visualization images
@app.route('/visualizations/<filename>')
def visualization_image(filename):
    return send_from_directory('static/images', filename)

# ---------------------------
# Comparison Reports
# ---------------------------

# Helper functions
def calculate_schedule_metrics(schedule):
    if isinstance(schedule, dict) and 'scheduled_jobs' in schedule:
        jobs = schedule['scheduled_jobs']
    elif isinstance(schedule, list):
        jobs = schedule
    else:
        raise ValueError("Unexpected schedule format")

    total_duration = sum(
        (datetime.datetime.strptime(job['scheduled_end_time'], '%Y-%m-%dT%H:%M:%S') -
         datetime.datetime.strptime(job['scheduled_start_time'], '%Y-%m-%dT%H:%M:%S')).total_seconds() / 3600 
        for job in jobs if isinstance(job, dict)
    )
    
    if jobs:
        makespan = max(datetime.datetime.strptime(job['scheduled_end_time'], '%Y-%m-%dT%H:%M:%S') for job in jobs if isinstance(job, dict)) - \
                   min(datetime.datetime.strptime(job['scheduled_start_time'], '%Y-%m-%dT%H:%M:%S') for job in jobs if isinstance(job, dict))
        makespan_hours = makespan.total_seconds() / 3600
    else:
        makespan_hours = 0
    
    equipment_utilization = {}
    for job in jobs:
        if isinstance(job, dict):
            if job['equipment_id'] not in equipment_utilization:
                equipment_utilization[job['equipment_id']] = 0
            equipment_utilization[job['equipment_id']] += (
                datetime.datetime.strptime(job['scheduled_end_time'], '%Y-%m-%dT%H:%M:%S') - 
                datetime.datetime.strptime(job['scheduled_start_time'], '%Y-%m-%dT%H:%M:%S')
            ).total_seconds() / 3600
    
    avg_equipment_utilization = sum(equipment_utilization.values()) / len(equipment_utilization) if equipment_utilization else 0
    
    return {
        'total_duration': total_duration,
        'makespan': makespan_hours,
        'avg_equipment_utilization': avg_equipment_utilization,
        'num_jobs': len(jobs)
    }

def compare_schedules(schedule1, schedule2):
    metrics1 = calculate_schedule_metrics(schedule1)
    metrics2 = calculate_schedule_metrics(schedule2)
    
    def safe_percentage_change(old, new):
        if old == 0:
            return 'inf' if new > 0 else '0'
        return ((new - old) / old) * 100

    comparison = {
        'total_duration': {
            'schedule1': metrics1['total_duration'],
            'schedule2': metrics2['total_duration'],
            'difference': metrics2['total_duration'] - metrics1['total_duration'],
            'percentage_change': safe_percentage_change(metrics1['total_duration'], metrics2['total_duration'])
        },
        'makespan': {
            'schedule1': metrics1['makespan'],
            'schedule2': metrics2['makespan'],
            'difference': metrics2['makespan'] - metrics1['makespan'],
            'percentage_change': safe_percentage_change(metrics1['makespan'], metrics2['makespan'])
        },
        'avg_equipment_utilization': {
            'schedule1': metrics1['avg_equipment_utilization'],
            'schedule2': metrics2['avg_equipment_utilization'],
            'difference': metrics2['avg_equipment_utilization'] - metrics1['avg_equipment_utilization'],
            'percentage_change': safe_percentage_change(metrics1['avg_equipment_utilization'], metrics2['avg_equipment_utilization'])
        },
        'num_jobs': {
            'schedule1': metrics1['num_jobs'],
            'schedule2': metrics2['num_jobs'],
            'difference': metrics2['num_jobs'] - metrics1['num_jobs'],
            'percentage_change': safe_percentage_change(metrics1['num_jobs'], metrics2['num_jobs'])
        }
    }
    
    return comparison

def compare_multiple_schedules(schedules):
    comparison = {
        'total_duration': {},
        'makespan': {},
        'avg_equipment_utilization': {},
        'num_jobs': {}
    }
    
    for optimizer, schedule in schedules.items():
        metrics = calculate_schedule_metrics(schedule)
        for metric in comparison.keys():
            comparison[metric][optimizer] = metrics.get(metric, 'N/A')
    
    return comparison

@app.route('/compare_initial_optimized/<optimizer>')
def compare_initial_optimized(optimizer):
    initial_schedule = load_data(SCHEDULE_FILE)
    OPTIMIZED_SCHEDULE_FILE = os.path.join(DATA_DIR, f'optimized_schedule_{optimizer.lower()}.json')
    optimized_schedule = load_data(OPTIMIZED_SCHEDULE_FILE)
    
    comparison = compare_schedules(initial_schedule, optimized_schedule)
    return render_template('compare_schedules.html', comparison=comparison, optimizer=optimizer)

@app.route('/compare_optimizers')
def compare_optimizers():
    optimizers = ['MILP', 'GA', 'OR-Tools']
    schedules = {'Initial': load_data(SCHEDULE_FILE)}  # Load the initial schedule
    
    for opt in optimizers:
        file_path = os.path.join(DATA_DIR, f'optimized_schedule_{opt.lower()}.json')
        if os.path.exists(file_path):
            schedules[opt] = load_data(file_path)
        else:
            print(f"Warning: Optimized schedule for {opt} not found.")
    
    comparison = compare_multiple_schedules(schedules)
    return render_template('compare_optimizers.html', comparison=comparison, optimizers=['Initial'] + optimizers)

# ---------------------------
# Run the Flask Application
# ---------------------------

if __name__ == '__main__':
    app.run(debug=True)
