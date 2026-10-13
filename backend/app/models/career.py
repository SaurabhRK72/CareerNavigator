from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class CareerRoleSkill(Base):
    __tablename__ = "career_role_skills"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("career_roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_level: Mapped[str] = mapped_column(String(20), nullable=False)


class CareerRole(Base):
    __tablename__ = "career_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    interests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class StudentSkill(Base):
    __tablename__ = "student_skills"

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    education: Mapped[str | None] = mapped_column(String(200))
    experience_years: Mapped[float | None] = mapped_column(Float)
    interests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    preferred_location: Mapped[str | None] = mapped_column(String(100))
    preferred_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class LearningResource(Base):
    __tablename__ = "learning_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    provider: Mapped[str] = mapped_column(String(150), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningRoadmap(Base):
    __tablename__ = "learning_roadmaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="SET NULL")
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("career_roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    weekly_study_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    milestones: Mapped[list["RoadmapMilestone"]] = relationship(
        back_populates="roadmap",
        cascade="all, delete-orphan",
        order_by="RoadmapMilestone.week",
    )


class RoadmapMilestone(Base):
    __tablename__ = "roadmap_milestones"
    __table_args__ = (
        UniqueConstraint("roadmap_id", "week", name="uq_roadmap_week"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    roadmap_id: Mapped[int] = mapped_column(
        ForeignKey("learning_roadmaps.id", ondelete="CASCADE"),
        nullable=False,
    )
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    practice_task: Mapped[str] = mapped_column(Text, nullable=False)
    mini_project: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_resources.id", ondelete="SET NULL")
    )
    completed: Mapped[bool] = mapped_column(default=False, nullable=False)
    roadmap: Mapped[LearningRoadmap] = relationship(back_populates="milestones")
