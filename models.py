from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(255))
    password_hash = Column(String(255))
    full_name = Column(String(255))
    role = Column(String(50), default='job_seeker')
    cover_image_url = Column(String(255), nullable=True)
    headline = Column(String(150), nullable=True)
    bio = Column(Text, nullable=True)
    phone_number = Column(String(20), nullable=True)
    show_phone_publicly = Column(Boolean, default=False)
    social_links = Column(JSON, default={})
    cv_url = Column(String(255), nullable=True)
    skills = Column(JSON, default=[])
    profile_views = Column(Integer, default=0)


class PortfolioItem(Base):
    __tablename__ = 'portfolio_items'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(120), nullable=False)
    description = Column(Text)
    project_url = Column(String(255))
    image_url = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)


class Experience(Base):
    __tablename__ = 'experiences'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    company_name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=True)
    is_current = Column(Boolean, default=False)
    description = Column(Text)


class Education(Base):
    __tablename__ = 'education'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    institution = Column(String(120), nullable=False)
    degree = Column(String(100), nullable=False)
    field_of_study = Column(String(100))
    start_year = Column(String(10))
    end_year = Column(String(10))


class SkillEndorsement(Base):
    __tablename__ = 'skill_endorsements'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    endorser_id = Column(Integer, ForeignKey('users.id'))
    skill_name = Column(String(50), nullable=False)
