
from sqlite3 import IntegrityError
import traceback
import grpc
from services.converters.userConverter import db_user_to_proto
from security.NewPass import CreatePass
from database import AsyncSessionLocal
from protobuf import mess_pb2_grpc,mess_pb2


from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy import select, insert, update, delete
import asyncio

from services.models import User


class UsersServicer(mess_pb2_grpc.UserServiceServicer):

    # Create a new Todo
    async def CreateUser(self, request, context):
        # 1. Создаём объект для вставки (исключая поля, которые генерируются БД)
        user_data = {
            "nick_name": request.nick_name,
            "first_name": request.first_name,
            "last_name": request.last_name,
            "middle_name": request.middle_name,
            "email": request.email,
            "phone": request.phone,
            "password":request.password
            # поля по умолчанию: created_at, updated_at будут заполнены БД или можно установить здесь
        }   

        password_hash, salt = CreatePass.createPassWithSalt(password=user_data["password"])


        # 2. Асинхронная сессия
        async with AsyncSessionLocal() as session:
            try:
                # 3. Выполняем вставку с возвратом данных
                stmt = insert(User).values(nick_name = user_data["nick_name"],
                                           first_name = user_data["first_name"],
                                           last_name = user_data["last_name"],
                                           middle_name = user_data["middle_name"],
                                           email = user_data["email"],
                                           phone = user_data["phone"],
                                           password_hash = password_hash,
                                           salt = salt
                                            ).returning(User)
                result = await session.execute(stmt)
                new_user = result.scalar_one()

                # 4. Коммитим транзакцию
                await session.commit()

                
                return db_user_to_proto(new_user)
            
            except IntegrityError as e:
                await session.rollback()
                # Например, нарушение уникальности email
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "User with this email already exists")
            except Exception as e:
                await session.rollback()
                await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")
    async def UpdateUser(self, request, context):
    # 1. user_id получаем напрямую из request
        user_id = request.user_id
        if not user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")

        # 2. Собираем только те поля, которые реально переданы и не пустые
        update_data = {}
        if request.HasField("nick_name") and request.nick_name:
            update_data["nick_name"] = request.nick_name
        if request.HasField("first_name") and request.first_name:
            update_data["first_name"] = request.first_name
        if request.HasField("last_name") and request.last_name:
            update_data["last_name"] = request.last_name
        if request.HasField("middle_name") and request.middle_name:
            update_data["middle_name"] = request.middle_name
        if request.HasField("email") and request.email:
            update_data["email"] = request.email
        if request.HasField("phone") and request.phone:
            update_data["phone"] = request.phone
        if request.HasField("avatar_url") and request.avatar_url:
            update_data["avatar_url"] = request.avatar_url
        if request.HasField("bio") and request.bio:
            update_data["bio"] = request.bio

        # 3. Если нечего обновлять – просто возвращаем текущего пользователя
        if not update_data:
            async with AsyncSessionLocal() as session:
                user = await session.get(User, user_id)
                if not user:
                    await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
                return db_user_to_proto(user)

        # 4. Обновление с возвратом обновлённой записи
        async with AsyncSessionLocal() as session:
            try:
                stmt = (
                    update(User)
                    .where(User.user_id == user_id)   # используем user_id из request
                    .values(**update_data)
                    .returning(User)
                )
                result = await session.execute(stmt)
                updated_user = result.scalar_one_or_none()
                if not updated_user:
                    await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
                await session.commit()
                return db_user_to_proto(updated_user)
            except Exception as e:
                await session.rollback()
                print(f"UpdateUser error: {e}")
                traceback.print_exc()
                await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")


  
    # Read an existing Todo
    # def GetUser(self, request, context):
    #     db = SessionLocal()
    #     todo = db.query(Todo).filter(Todo.id == request.id).first()
    #     db.close()
    #     if todo:
    #         return todo_pb2.Todo(
    #             id=todo.id,
    #             title=todo.title,
    #             description=todo.description,
    #             done=todo.done
    #         )
    #     else:
    #         context.set_code(grpc.StatusCode.NOT_FOUND)
    #         context.set_details("Todo not found")
    #         return todo_pb2.Todo()

    # # Update an existing Todo
    # def UpdateUser(self, request, context):
    #     db = SessionLocal()
    #     todo = db.query(Todo).filter(Todo.id == request.id).first()
    #     if todo:
    #         todo.title = request.title
    #         todo.description = request.description
    #         todo.done = request.done
    #         db.add(todo)
    #         db.commit()
    #         db.refresh(todo)
    #         db.close()
    #         return todo_pb2.Todo(
    #             id=todo.id,
    #             title=todo.title,
    #             description=todo.description,
    #             done=todo.done
    #         )
    #     else:
    #         context.set_code(grpc.StatusCode.NOT_FOUND)
    #         context.set_details("Todo not found")
    #         return todo_pb2.Todo()

    # # Delete an existing Todo
    # def DeleteUser(self, request, context):
    #     db = SessionLocal()
    #     todo = db.query(Todo).filter(Todo.id == request.id).first()
    #     if todo:
    #         db.delete(todo)
    #         db.commit()
    #         db.close()
    #         return empty_pb2.Empty()
    #     else:
    #         context.set_code(grpc.StatusCode.NOT_FOUND)
    #         context.set_details("Todo not found")
    #         return empty_pb2.Empty()

    # # List all Todos
    # def SearchUsers(self, request, context):
    #     db = SessionLocal()
    #     todos = db.query(Todo).all()
    #     db.close()
    #     todo_list = [todo_pb2.Todo(
    #         id=todo.id,
    #         title=todo.title,
    #         description=todo.description,
    #         done=todo.done
    #     ) for todo in todos]
    #     return todo_pb2.TodoListResponse(todos=todo_list)
    

    # async def GetMyProfile(self, request, context):
    #     pass

    # async def UpdatePrivacy(self, request, context):
    #     pass
