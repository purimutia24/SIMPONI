from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# URL Koneksi database MySQL di dalam WSL
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:@localhost:3306/db_simponi"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()