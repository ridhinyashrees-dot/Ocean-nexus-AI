import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Unoda PostgreSQL credentials & Namma create panna 'Argo DB' name
DB_USER = "postgres"
DB_PASSWORD = "Ridhinya@2008" # unoda pgAdmin password-a inga podu
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "Argo DB"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()