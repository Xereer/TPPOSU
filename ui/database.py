from typing import List, Optional
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select
from datetime import datetime
from sqlalchemy.sql import func

class Experiments(SQLModel, table=True):
    __tablename__ = "experiments"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="—", max_length=500)
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = Field(default=None)
    operator: str = Field(default="—", max_length=100)

    measurements: List["Measurements"] = Relationship(back_populates="experiments")

    

class Measurements(SQLModel, table=True):
    __tablename__ = "measurements"

    id: Optional[int] = Field(default=None, primary_key=True)

    experiment_id: int = Field(foreign_key="experiments.id")

    number:  int
    channel_1: float
    channel_2: float
    channel_3: float
    channel_4: float
    channel_5: bool
    channel_6_avg: float
    channel_6_disp: float
    channel_19: float
    channel_49: float
    channel_69_func: float

    experiments: Optional[Experiments] = Relationship(back_populates="measurements")

sqlite_url = "sqlite:///data/database.db"
engine = create_engine(sqlite_url, echo=False)

def create_database_and_tables():
    SQLModel.metadata.create_all(engine)

if __name__ == "__main__":
    print("Database and tables created!")
