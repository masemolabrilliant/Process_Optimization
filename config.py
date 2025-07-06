# config.py

from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).parent.resolve()

# Upload folder inside the base directory
UPLOAD_FOLDER = BASE_DIR / 'uploads'

# PostgreSQL configuration
DB_USERNAME = 'postgres'
DB_PASSWORD = 'jim12345'
DB_HOST = 'localhost'
DB_PORT = '5432'
DB_NAME = 'optimization'

# SQLAlchemy URI
SQLALCHEMY_DATABASE_URI = (
    f'postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)

# SQLAlchemy config
SQLALCHEMY_TRACK_MODIFICATIONS = False
