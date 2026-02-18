import grpc
import logging
import todo_pb2
import todo_pb2_grpc
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import time
from concurrent import futures
from google.protobuf import empty_pb2
import os
# SQLAlchemy database URL
DATABASE_URL = "postgresql+asyncpg://bodya11@localhost:5432/messenger_db_dip"

# Create a SQLAlchemy engine
engine = create_engine(DATABASE_URL)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a Base class for declarative models
Base = declarative_base()

# Define the Todo model
class Todo(Base):
    __tablename__ = "todo"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    done = Column(Boolean)

# Create the todo table
Base.metadata.create_all(bind=engine)

# Define the gRPC service


# Create a gRPC server
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

# Add the TodoServicer to the server
todo_pb2_grpc.add_TodoServiceServicer_to_server(TodoServicer(), server)

# Start the server
server.add_insecure_port('[::]:50051')
server.start()
logging.info("Server started on port 50051")

# Wait for the server to stop
try:
    while True:
        time.sleep(86400)
except KeyboardInterrupt:
    server.stop(0)