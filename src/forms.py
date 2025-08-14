# forms.py
from flask_wtf import FlaskForm
from wtforms import (
    StringField, IntegerField, FloatField, TextAreaField,
    SelectField, SelectMultipleField, FieldList, FormField, SubmitField
)
from wtforms.validators import DataRequired, NumberRange, Optional, Email, Length

# Child subforms for Job requirements
class ToolRequirementForm(FlaskForm):
    class Meta:
        csrf = False  # IMPORTANT: disable CSRF on nested subform
    tool_id = SelectField('Tool', choices=[], validators=[Optional()])
    quantity = IntegerField('Quantity', validators=[Optional(), NumberRange(min=1)])

class MaterialRequirementForm(FlaskForm):
    class Meta:
        csrf = False  # IMPORTANT: disable CSRF on nested subform
    material_id = SelectField('Material', choices=[], validators=[Optional()])
    quantity = IntegerField('Quantity', validators=[Optional(), NumberRange(min=1)])

# ---------------------------
# Equipment / Skill / Tool / Material CRUD forms
# ---------------------------

class EquipmentForm(FlaskForm):
    equipment_id = StringField('Equipment ID', validators=[DataRequired(), Length(max=10)])
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    priority = IntegerField('Priority', validators=[Optional()])
    submit = SubmitField('Save')


class SkillForm(FlaskForm):
    skill = StringField('Skill', validators=[DataRequired(), Length(max=50)])
    submit = SubmitField('Save')


class ToolForm(FlaskForm):
    tool_id = StringField('Tool ID', validators=[DataRequired(), Length(max=10)])
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Save')


class MaterialForm(FlaskForm):
    material_id = StringField('Material ID', validators=[DataRequired(), Length(max=10)])
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Save')


# ---------------------------
# Technician CRUD
# ---------------------------

class TechnicianForm(FlaskForm):
    tech_id = StringField('Technician ID', validators=[DataRequired(), Length(max=10)])
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    phone_number = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=100)])
    hourly_rate = FloatField('Hourly Rate', validators=[DataRequired(), NumberRange(min=0)])

    # Skills are managed via link table; we present as multi-select of Skill.skill
    skills = SelectMultipleField('Skills', choices=[], validators=[Optional()])

    submit = SubmitField('Save')

    def __init__(self, *args, skill_choices=None, **kwargs):
        """
        skill_choices: list[tuple(value,label)] e.g. [('Welding','Welding'), ...]
        """
        super().__init__(*args, **kwargs)
        if skill_choices is not None:
            self.skills.choices = skill_choices


# ---------------------------
# Job CRUD
# ---------------------------

class JobForm(FlaskForm):
    job_id = StringField('Job ID', validators=[DataRequired(), Length(max=10)])
    description = TextAreaField('Description', validators=[DataRequired()])
    duration = IntegerField('Duration (hours)', validators=[DataRequired(), NumberRange(min=0)])

    # dropdowns fed from DB via view
    equipment_id = SelectField('Equipment', choices=[], validators=[DataRequired()])
    required_skills = SelectMultipleField('Required Skills', choices=[], validators=[Optional()])
    precedence = SelectMultipleField('Precedence Jobs', choices=[], validators=[Optional()])

    required_tools = FieldList(FormField(ToolRequirementForm), min_entries=0)
    required_materials = FieldList(FormField(MaterialRequirementForm), min_entries=0)
    submit = SubmitField('Save')

    def __init__(
        self,
        *args,
        equipment_choices=None,
        skill_choices=None,
        job_choices=None,
        tool_choices=None,
        material_choices=None,
        **kwargs
    ):
        """
        Each *_choices should be a list[tuple(value,label)].
        e.g. equipment_choices = [('EQ1','EQ1 - Lathe'), ...]
        """
        super().__init__(*args, **kwargs)

        if equipment_choices is not None:
            self.equipment_id.choices = equipment_choices

        if skill_choices is not None:
            self.required_skills.choices = skill_choices

        if job_choices is not None:
            # Use for precedence; route can exclude current job_id on edit if needed
            self.precedence.choices = job_choices

        # Ensure FieldList inner SelectFields get their choices
        if tool_choices is not None:
            for entry in self.required_tools:
                entry.form.tool_id.choices = tool_choices

        if material_choices is not None:
            for entry in self.required_materials:
                entry.form.material_id.choices = material_choices

    # helper to (re)apply choices when dynamically adding rows via JS/AJAX
    def apply_nested_choices(self, tool_choices=None, material_choices=None):
        if tool_choices is not None:
            for entry in self.required_tools:
                entry.form.tool_id.choices = tool_choices
        if material_choices is not None:
            for entry in self.required_materials:
                entry.form.material_id.choices = material_choices
