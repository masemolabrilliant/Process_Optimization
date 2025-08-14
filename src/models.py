# models.py
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ---------------------------
# Core reference tables
# ---------------------------

class Equipment(db.Model):
    __tablename__ = 'equipment'
    equipment_id = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    priority = db.Column(db.Integer)  # optional

    def __repr__(self):
        return f"<Equipment {self.equipment_id}>"


class Skill(db.Model):
    __tablename__ = 'skills'
    skill = db.Column(db.String(50), primary_key=True)

    def __repr__(self):
        return f"<Skill {self.skill}>"


class Tool(db.Model):
    __tablename__ = 'tools'
    tool_id = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer)

    def __repr__(self):
        return f"<Tool {self.tool_id}>"


class Material(db.Model):
    __tablename__ = 'materials'
    material_id = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer)

    def __repr__(self):
        return f"<Material {self.material_id}>"


# ---------------------------
# Technicians
# ---------------------------

class Technician(db.Model):
    __tablename__ = 'technicians'
    tech_id = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    phone_number = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(100), nullable=True)

    hourly_rate = db.Column(db.Float)

    # link to skills
    skills = db.relationship(
        'TechnicianSkill',
        backref='technician',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f"<Technician {self.tech_id}: {self.name}>"


class TechnicianSkill(db.Model):
    __tablename__ = 'technician_skills'
    tech_id = db.Column(
        db.String(10),
        db.ForeignKey('technicians.tech_id', ondelete='CASCADE'),
        primary_key=True
    )
    skill = db.Column(db.String(50), primary_key=True)

    def __repr__(self):
        return f"<TechnicianSkill {self.tech_id}:{self.skill}>"


# ---------------------------
# Jobs & link tables
# ---------------------------

class Job(db.Model):
    __tablename__ = 'jobs'

    job_id = db.Column(db.String(10), primary_key=True)
    description = db.Column(db.Text, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # hours
    equipment_id = db.Column(db.String(10), db.ForeignKey('equipment.equipment_id'), nullable=False)

    # Relationships
    equipment = db.relationship('Equipment', backref='jobs')

    skills = db.relationship('JobSkill', backref='job', cascade='all, delete-orphan')
    tools = db.relationship('JobTool', backref='job', cascade='all, delete-orphan')
    materials = db.relationship('JobMaterial', backref='job', cascade='all, delete-orphan')

    # Precedence (job -> precedes other jobs)
    precedes = db.relationship(
        'JobPrecedence',
        foreign_keys='JobPrecedence.job_id',
        backref='job',
        cascade='all, delete-orphan',
        passive_deletes=True
    )
    preceded_by = db.relationship(
        'JobPrecedence',
        foreign_keys='JobPrecedence.precedes_job_id',
        backref='precedes_job',
        cascade='all, delete-orphan',
        passive_deletes=True
    )

    def __repr__(self):
        return f"<Job {self.job_id}>"


class JobSkill(db.Model):
    __tablename__ = 'jobs_skills'
    job_id = db.Column(db.String(10), db.ForeignKey('jobs.job_id'), primary_key=True)
    skill = db.Column(db.String(50), primary_key=True)

    def __repr__(self):
        return f"<JobSkill {self.job_id}:{self.skill}>"


class JobTool(db.Model):
    __tablename__ = 'jobs_tools'
    job_id = db.Column(db.String(10), db.ForeignKey('jobs.job_id'), primary_key=True)
    tool_id = db.Column(db.String(10), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<JobTool {self.job_id}:{self.tool_id} x{self.quantity}>"


class JobMaterial(db.Model):
    __tablename__ = 'jobs_materials'
    job_id = db.Column(db.String(10), db.ForeignKey('jobs.job_id'), primary_key=True)
    material_id = db.Column(db.String(10), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<JobMaterial {self.job_id}:{self.material_id} x{self.quantity}>"


class JobPrecedence(db.Model):
    __tablename__ = 'jobs_precedence'
    job_id = db.Column(db.String(10), db.ForeignKey('jobs.job_id'), primary_key=True)
    precedes_job_id = db.Column(db.String(10), db.ForeignKey('jobs.job_id'), primary_key=True)

    def __repr__(self):
        return f"<JobPrecedence {self.job_id} -> {self.precedes_job_id}>"
