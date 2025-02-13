import sys
import os
import random
import datetime
import json
from typing import List, Dict, Any, Tuple
import numpy as np

# Add the root directory to the system path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.data_handler import load_and_validate_data

# Data paths
DATA_DIR = 'data'

# Constants
POPULATION_SIZE = 100
GENERATIONS = 100
MUTATION_RATE = 0.1
CROSSOVER_RATE = 0.8

# Define working hours
WORKDAY_START = datetime.time(8, 0)
WORKDAY_END = datetime.time(17, 0)
WORKDAYS = {0, 1, 2, 3, 4}  # Monday to Friday

class GeneticAlgorithm:
    def __init__(self, data: Dict[str, Any]):
        self.jobs = data['jobs']
        self.technicians = data['technicians']
        self.equipment = data['equipment']
        self.tools = data['tools']
        self.materials = data['materials']
        self.t_start = datetime.datetime.strptime(data.get('t_start', '2023-12-01T08:00:00'), '%Y-%m-%dT%H:%M:%S')
        self.t_end = datetime.datetime.strptime(data.get('t_end', '2023-12-07T18:00:00'), '%Y-%m-%dT%H:%M:%S')

    def is_working_hour(self, dt: datetime.datetime) -> bool:
        return dt.weekday() in WORKDAYS and WORKDAY_START <= dt.time() < WORKDAY_END

    def next_working_hour(self, dt: datetime.datetime) -> datetime.datetime:
        while not self.is_working_hour(dt):
            dt += datetime.timedelta(hours=1)
            if dt.time() < WORKDAY_START:
                dt = dt.replace(hour=WORKDAY_START.hour, minute=WORKDAY_START.minute)
            elif dt.time() >= WORKDAY_END:
                dt += datetime.timedelta(days=1)
                dt = dt.replace(hour=WORKDAY_START.hour, minute=WORKDAY_START.minute)
        return dt

    def generate_individual(self) -> List[Dict[str, Any]]:
        schedule = []
        for job in self.jobs:
            start_time = self.next_working_hour(self.t_start + datetime.timedelta(minutes=random.randint(0, int((self.t_end - self.t_start).total_seconds() / 60))))
            end_time = start_time + datetime.timedelta(hours=job['duration'])
            
            # Ensure the job ends within working hours and the scheduling window
            while not self.is_working_hour(end_time - datetime.timedelta(minutes=1)) or end_time > self.t_end:
                start_time = self.next_working_hour(start_time + datetime.timedelta(hours=1))
                end_time = start_time + datetime.timedelta(hours=job['duration'])
                if start_time >= self.t_end:
                    # If we can't fit the job, schedule it at the start of the window
                    start_time = self.next_working_hour(self.t_start)
                    end_time = start_time + datetime.timedelta(hours=job['duration'])
            
            available_techs = [tech for tech in self.technicians if set(job['required_skills']).issubset(set(tech['skills']))]
            assigned_techs = random.sample(available_techs, min(len(available_techs), 2))  # Assign up to 2 technicians
            
            schedule.append({
                'job_id': job['job_id'],
                'equipment_id': job['equipment_id'],
                'scheduled_start_time': start_time,
                'scheduled_end_time': end_time,
                'assigned_technicians': [tech['tech_id'] for tech in assigned_techs]
            })
        return schedule

    def fitness(self, individual: List[Dict[str, Any]]) -> float:
        total_violation = 0
        equipment_usage = {equip['equipment_id']: [] for equip in self.equipment}
        technician_usage = {tech['tech_id']: [] for tech in self.technicians}
        tool_usage = {tool['tool_id']: 0 for tool in self.tools}
        material_usage = {material['material_id']: 0 for material in self.materials}
        
        for job in individual:
            # Working hours and scheduling window violation
            start_time, end_time = job['scheduled_start_time'], job['scheduled_end_time']
            if start_time < self.t_start or end_time > self.t_end:
                total_violation += 1000  # Heavy penalty for being outside scheduling window
            
            current_time = start_time
            while current_time < end_time:
                if not self.is_working_hour(current_time):
                    total_violation += 1
                current_time += datetime.timedelta(hours=1)
            
            # Other constraints remain the same
            equipment_usage[job['equipment_id']].append((start_time, end_time))
            for tech_id in job['assigned_technicians']:
                technician_usage[tech_id].append((start_time, end_time))
            
            job_data = next(j for j in self.jobs if j['job_id'] == job['job_id'])
            for tool_req in job_data['required_tools']:
                tool_usage[tool_req['tool_id']] += tool_req['quantity']
            for material_req in job_data['required_materials']:
                material_usage[material_req['material_id']] += material_req['quantity']
        
        # Check for overlaps in equipment and technician usage
        for usage in list(equipment_usage.values()) + list(technician_usage.values()):
            usage.sort(key=lambda x: x[0])
            for i in range(len(usage) - 1):
                if usage[i][1] > usage[i+1][0]:
                    total_violation += 1
        
        # Check for tool and material over-usage
        for tool in self.tools:
            if tool_usage[tool['tool_id']] > tool['quantity']:
                total_violation += tool_usage[tool['tool_id']] - tool['quantity']
        for material in self.materials:
            if material_usage[material['material_id']] > material['quantity']:
                total_violation += material_usage[material['material_id']] - material['quantity']
        
        makespan = max(job['scheduled_end_time'] for job in individual) - min(job['scheduled_start_time'] for job in individual)
        
        return 1 / (makespan.total_seconds() / 3600 + total_violation * 100)  # Increased penalty for violations

    def crossover(self, parent1: List[Dict[str, Any]], parent2: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if random.random() > CROSSOVER_RATE:
            return parent1, parent2
        
        crossover_point = random.randint(1, len(parent1) - 1)
        child1 = parent1[:crossover_point] + parent2[crossover_point:]
        child2 = parent2[:crossover_point] + parent1[crossover_point:]
        return child1, child2

    def mutate(self, individual: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for i in range(len(individual)):
            if random.random() < MUTATION_RATE:
                job = individual[i]
                
                # Mutate start time
                shift = datetime.timedelta(hours=random.randint(-12, 12))
                new_start = self.next_working_hour(job['scheduled_start_time'] + shift)
                new_end = new_start + datetime.timedelta(hours=next(j['duration'] for j in self.jobs if j['job_id'] == job['job_id']))
                
                # Ensure the job ends within working hours and the scheduling window
                while not self.is_working_hour(new_end - datetime.timedelta(minutes=1)) or new_end > self.t_end:
                    new_start = self.next_working_hour(new_start + datetime.timedelta(hours=1))
                    new_end = new_start + datetime.timedelta(hours=next(j['duration'] for j in self.jobs if j['job_id'] == job['job_id']))
                    if new_start >= self.t_end:
                        # If we can't fit the job, schedule it at the start of the window
                        new_start = self.next_working_hour(self.t_start)
                        new_end = new_start + datetime.timedelta(hours=next(j['duration'] for j in self.jobs if j['job_id'] == job['job_id']))
                
                job['scheduled_start_time'] = new_start
                job['scheduled_end_time'] = new_end
                
                # Mutate assigned technicians
                job_data = next(j for j in self.jobs if j['job_id'] == job['job_id'])
                available_techs = [tech for tech in self.technicians if set(job_data['required_skills']).issubset(set(tech['skills']))]
                job['assigned_technicians'] = [tech['tech_id'] for tech in random.sample(available_techs, min(len(available_techs), 2))]
        
        return individual

    def select_parents(self, population: List[List[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        tournament_size = 5
        tournament1 = random.sample(population, tournament_size)
        tournament2 = random.sample(population, tournament_size)
        parent1 = max(tournament1, key=self.fitness)
        parent2 = max(tournament2, key=self.fitness)
        return parent1, parent2

    def optimize(self) -> List[Dict[str, Any]]:
        population = [self.generate_individual() for _ in range(POPULATION_SIZE)]
        
        for generation in range(GENERATIONS):
            new_population = []
            
            for _ in range(POPULATION_SIZE // 2):
                parent1, parent2 = self.select_parents(population)
                child1, child2 = self.crossover(parent1, parent2)
                new_population.extend([self.mutate(child1), self.mutate(child2)])
            
            population = new_population
            
            best_individual = max(population, key=self.fitness)
            best_fitness = self.fitness(best_individual)
            
            print(f"Generation {generation + 1}: Best Fitness = {best_fitness}")
        
        return best_individual

def save_optimized_schedule(schedule, optimizer_name):
    filename = f'optimized_schedule_{optimizer_name.lower()}.json'
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(schedule, f, indent=4)
    print(f"\nOptimized schedule saved to {filepath}")

def optimize_schedule():
    data = load_and_validate_data()
    ga = GeneticAlgorithm(data)
    best_schedule = ga.optimize()
    
    # Convert datetime objects to string for JSON serialization
    for job in best_schedule:
        job['scheduled_start_time'] = job['scheduled_start_time'].strftime('%Y-%m-%dT%H:%M:%S')
        job['scheduled_end_time'] = job['scheduled_end_time'].strftime('%Y-%m-%dT%H:%M:%S')
    
    # Save the optimized schedule
    save_optimized_schedule(best_schedule, "GA")
    
    print("Optimization complete. Schedule saved to 'optimized_schedule.json'.")
    return best_schedule

if __name__ == "__main__":
    optimize_schedule()