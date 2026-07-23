import os
from datetime import datetime, timedelta, timezone

import jwt
from ariadne import MutationType, QueryType, make_executable_schema
from flask import session

JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-jwt-secret')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_DAYS = 30

type_defs = """
    type User {
        id: ID!
        name: String!
        email: String!
        preferences: String
    }

    type AuthPayload {
        token: String!
        user: User!
    }

    type Query {
        me: User
    }

    type Mutation {
        signup(name: String!, email: String!, password: String!, preferences: String): AuthPayload!
        login(email: String!, password: String!): AuthPayload!
    }
"""

query = QueryType()
mutation = MutationType()


def issue_token(user):
    payload = {
        'sub': str(user.id),
        'exp': datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_context_value(request):
    from app import User

    user = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[len('Bearer '):]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = User.query.get(int(payload['sub']))
        except (jwt.PyJWTError, ValueError):
            user = None
    elif session.get('user_id'):
        user = User.query.get(session['user_id'])
    return {'user': user}


def require_user(info):
    user = info.context.get('user')
    if not user:
        raise Exception('Not authenticated')
    return user


@query.field('me')
def resolve_me(_, info):
    return info.context.get('user')


@mutation.field('signup')
def resolve_signup(_, info, name, email, password, preferences=None):
    from app import User, db

    if User.query.filter_by(email=email).first():
        raise Exception('An account with that email already exists.')
    user = User(name=name, email=email, preferences=preferences)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return {'token': issue_token(user), 'user': user}


@mutation.field('login')
def resolve_login(_, info, email, password):
    from app import User

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        raise Exception('Invalid email or password.')
    return {'token': issue_token(user), 'user': user}


schema = make_executable_schema(type_defs, query, mutation)
