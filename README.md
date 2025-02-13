# Shutdown Maintenance Scheduling Application

## Overview
This application is designed to manage and optimize shutdown maintenance schedules for industrial equipment. It provides tools for managing jobs, technicians, and resources, as well as generating and optimizing maintenance schedules.

## Features
- Job Management: Add, edit, and delete maintenance jobs
- Technician Management: Manage technician information and skills
- Resource Management: Track tools and materials required for jobs
- Schedule Generation: Create initial maintenance schedules
- Schedule Optimization: Optimize schedules using various algorithms (MILP, GA, OR-Tools, SA)
- Visualization: View schedules as Gantt charts
- Metrics: Calculate and display various performance metrics

## Installation
1. Clone this repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - On Windows: `venv\Scripts\activate`
   - On macOS and Linux: `source venv/bin/activate`
4. Install the required packages: `pip install -r requirements.txt`

## Usage
1. Run the Flask application: `python app.py`
2. Open a web browser and navigate to `http://localhost:5000`
3. Use the web interface to manage jobs, technicians, and view/optimize schedules

## Project Structure
- `app.py`: Main Flask application
- `src/`: Source code for scheduling algorithms and data handling
- `templates/`: HTML templates for the web interface
- `static/`: Static files (CSS, JavaScript, images)
- `data/`: JSON files for storing job, technician, and schedule data

## Contributing
Contributions to this project are welcome. Please fork the repository and submit a pull request with your changes.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.