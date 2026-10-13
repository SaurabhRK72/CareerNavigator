from typing import Literal

from pydantic import BaseModel, Field, field_validator

SkillLevel = Literal["beginner", "intermediate", "advanced"]


class StudentSkillInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    level: SkillLevel = "intermediate"


class StudentProfileInput(BaseModel):
    technical_skills: list[StudentSkillInput] = Field(default_factory=list, max_length=100)
    education: str | None = Field(default=None, max_length=200)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    interests: list[str] = Field(default_factory=list, max_length=30)
    preferred_location: str | None = Field(default=None, max_length=100)
    preferred_roles: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("interests", "preferred_roles")
    @classmethod
    def trim_non_empty_values(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class CareerRoleSummary(BaseModel):
    id: str
    name: str
    description: str
    required_skill_count: int


class SkillMatch(BaseModel):
    name: str
    weight: int
    required_level: SkillLevel
    student_level: SkillLevel | None


class CareerRecommendation(BaseModel):
    role_id: str
    role_name: str
    description: str
    match_score: float
    matching_skills: list[SkillMatch]
    partial_skills: list[SkillMatch]
    missing_skills: list[SkillMatch]
    explanation: str
    preference_note: str | None


class CareerRecommendationsResponse(BaseModel):
    scoring_method: str
    score_disclaimer: str
    recommendations: list[CareerRecommendation]
    unknown_profile_skills: list[str]


class SkillGapItem(BaseModel):
    skill: str
    status: Literal["possessed", "partial", "missing"]
    student_level: SkillLevel | None
    required_level: SkillLevel
    role_weight: int
    market_demand_percentage: float | None
    priority_score: float
    explanation: str


class SkillGapResponse(BaseModel):
    role_id: str
    role_name: str
    match_score: float
    possessed: list[SkillGapItem]
    partial: list[SkillGapItem]
    missing: list[SkillGapItem]
    priority_gaps: list[SkillGapItem]
    market_demand_available: bool
    market_demand_note: str


class LearningResource(BaseModel):
    title: str
    provider: str
    url: str
    resource_type: str
    last_verified: str


class RoadmapMilestone(BaseModel):
    week: int
    skill: str
    why_it_matters: str
    goal: str
    practice_task: str
    mini_project: str
    resource: LearningResource | None


class LearningRoadmapRequest(BaseModel):
    profile: StudentProfileInput
    role_id: str = Field(min_length=1, max_length=80)
    weekly_study_hours: int = Field(default=5, ge=1, le=40)


class LearningRoadmapResponse(BaseModel):
    roadmap_id: int | None = None
    role_id: str
    role_name: str
    generated_at: str
    total_weeks: int
    weekly_study_hours: int
    milestones: list[RoadmapMilestone]
    resource_note: str
