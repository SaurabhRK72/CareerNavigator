import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    CareerRole as CareerRoleModel,
    Job,
    JobSkill,
    LearningResource as LearningResourceModel,
    LearningRoadmap,
    RoadmapMilestone as RoadmapMilestoneModel,
    Skill,
)
from backend.app.schemas.careers import (
    CareerRecommendation,
    CareerRecommendationsResponse,
    CareerRoleSummary,
    LearningResource,
    LearningRoadmapRequest,
    LearningRoadmapResponse,
    RoadmapMilestone,
    SkillGapItem,
    SkillGapResponse,
    SkillMatch,
    SkillLevel,
    StudentProfileInput,
)
from backend.app.services.jobs import load_skill_dictionary

ROLE_CATALOG_PATH = Path(__file__).parent.parent / "data" / "career_roles.json"
RESOURCE_CATALOG_PATH = (
    Path(__file__).parent.parent / "data" / "learning_resources.json"
)
SCORE_METHOD = (
    "Weighted skill coverage: matched requirement weight divided by total "
    "role requirement weight; a below-target self-reported skill contributes 50%."
)
SCORE_DISCLAIMER = (
    "This score measures overlap with this project's encoded role requirements. "
    "It is not a probability of getting hired."
)
_LEVEL_RANK = {"beginner": 1, "intermediate": 2, "advanced": 3}
_RESOURCE_LAST_VERIFIED = "2026-10-13"


class RoleSkill(BaseModel):
    name: str
    weight: int = Field(ge=1, le=10)
    minimum_level: SkillLevel


class CareerRole(BaseModel):
    id: str
    name: str
    description: str
    interests: list[str]
    skills: list[RoleSkill]


def load_role_catalog() -> list[CareerRole]:
    payload = _read_json(ROLE_CATALOG_PATH, "career role")
    if not isinstance(payload, dict) or not isinstance(payload.get("roles"), list):
        raise RuntimeError("The career role catalog must contain a roles list.")
    roles = [CareerRole.model_validate(item) for item in payload["roles"]]
    if len({role.id for role in roles}) != len(roles):
        raise RuntimeError("The career role catalog contains duplicate IDs.")
    return roles


def load_learning_resources() -> dict[str, LearningResource]:
    payload = _read_json(RESOURCE_CATALOG_PATH, "learning resource")
    if not isinstance(payload, dict) or not isinstance(
        payload.get("resources"), list
    ):
        raise RuntimeError(
            "The learning resource catalog must contain a resources list."
        )
    resources: dict[str, LearningResource] = {}
    for item in payload["resources"]:
        resource = LearningResource(
            title=item["title"],
            provider=item["provider"],
            url=item["url"],
            resource_type=item["resource_type"],
            last_verified=_RESOURCE_LAST_VERIFIED,
        )
        resources[item["skill"].casefold()] = resource
    return resources


def get_career_roles() -> list[CareerRoleSummary]:
    return [
        CareerRoleSummary(
            id=role.id,
            name=role.name,
            description=role.description,
            required_skill_count=len(role.skills),
        )
        for role in load_role_catalog()
    ]


def recommend_careers(
    profile: StudentProfileInput,
    limit: int = 5,
) -> CareerRecommendationsResponse:
    canonical_skills, unknown_skills = _normalize_profile_skills(profile)
    roles = load_role_catalog()
    preferred_ids = {
        value.casefold().replace(" ", "-") for value in profile.preferred_roles
    }
    preferred_names = {value.casefold() for value in profile.preferred_roles}
    matching_preferences = [
        role
        for role in roles
        if role.id.casefold() in preferred_ids
        or role.name.casefold() in preferred_names
    ]
    eligible_roles = matching_preferences or roles
    recommendations = [
        _score_role(role, canonical_skills, profile)
        for role in eligible_roles
    ]
    recommendations.sort(
        key=lambda result: (-result.match_score, result.role_name.casefold())
    )
    return CareerRecommendationsResponse(
        scoring_method=SCORE_METHOD,
        score_disclaimer=SCORE_DISCLAIMER,
        recommendations=recommendations[:limit],
        unknown_profile_skills=unknown_skills,
    )


def analyze_skill_gaps(
    profile: StudentProfileInput,
    role_id: str,
    session: Session | None = None,
) -> SkillGapResponse:
    role = _get_role(role_id)
    canonical_skills, _ = _normalize_profile_skills(profile)
    market_demand = (
        get_market_skill_percentages(session)
        if session is not None
        else {}
    )
    possessions: list[SkillGapItem] = []
    partials: list[SkillGapItem] = []
    missing: list[SkillGapItem] = []

    for requirement in role.skills:
        student_level = canonical_skills.get(requirement.name.casefold())
        if student_level is None:
            status: Literal["possessed", "partial", "missing"] = "missing"
        elif _LEVEL_RANK[student_level] < _LEVEL_RANK[requirement.minimum_level]:
            status = "partial"
        else:
            status = "possessed"

        demand = market_demand.get(requirement.name.casefold())
        priority = round(
            requirement.weight * (1 + demand / 100)
            if demand is not None
            else float(requirement.weight),
            2,
        )
        item = SkillGapItem(
            skill=requirement.name,
            status=status,
            student_level=student_level,
            required_level=requirement.minimum_level,
            role_weight=requirement.weight,
            market_demand_percentage=demand,
            priority_score=priority,
            explanation=_gap_explanation(
                status,
                requirement.weight,
                demand,
            ),
        )
        if status == "possessed":
            possessions.append(item)
        elif status == "partial":
            partials.append(item)
        else:
            missing.append(item)

    profile_score = _weighted_profile_score(role, canonical_skills)
    priority_gaps = sorted(
        [*partials, *missing],
        key=lambda item: (-item.priority_score, item.skill.casefold()),
    )
    has_market_data = bool(market_demand)
    return SkillGapResponse(
        role_id=role.id,
        role_name=role.name,
        match_score=profile_score,
        possessed=possessions,
        partial=partials,
        missing=missing,
        priority_gaps=priority_gaps,
        market_demand_available=has_market_data,
        market_demand_note=(
            "Gap priorities combine role importance and percentage of stored "
            "unique job postings mentioning each skill."
            if has_market_data
            else "No market demand was available; gaps are prioritized by role "
            "importance only."
        ),
    )


def create_learning_roadmap(
    request: LearningRoadmapRequest,
    session: Session | None = None,
) -> LearningRoadmapResponse:
    role = _get_role(request.role_id)
    gaps = analyze_skill_gaps(request.profile, role.id, session)
    resources = load_learning_resources()
    milestones: list[RoadmapMilestone] = []

    for week, gap in enumerate(gaps.priority_gaps, start=1):
        resource = resources.get(gap.skill.casefold())
        milestones.append(
            RoadmapMilestone(
                week=week,
                skill=gap.skill,
                why_it_matters=(
                    f"{gap.skill} is a {role.name} requirement "
                    f"(role importance {gap.role_weight}/10). "
                    + (
                        f"It appeared in {gap.market_demand_percentage:.2f}% "
                        "of stored job postings."
                        if gap.market_demand_percentage is not None
                        else "Market demand could not be calculated yet."
                    )
                ),
                goal=_weekly_goal(gap.skill, request.weekly_study_hours),
                practice_task=_practice_task(gap.skill),
                mini_project=_mini_project(gap.skill, role.name),
                resource=resource,
            )
        )

    return LearningRoadmapResponse(
        role_id=role.id,
        role_name=role.name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_weeks=len(milestones),
        weekly_study_hours=request.weekly_study_hours,
        milestones=milestones,
        resource_note=(
            "Only cataloged resource URLs are shown. Verify availability and "
            "suitability before following a resource."
        ),
    )


def persist_learning_roadmap(
    session: Session,
    roadmap: LearningRoadmapResponse,
) -> int:
    role = session.scalar(
        select(CareerRoleModel).where(CareerRoleModel.slug == roadmap.role_id)
    )
    if role is None:
        raise LookupError(
            "Career role reference data is missing. Run "
            "`python -m backend.app.db.init_db` to seed the role catalog."
        )
    record = LearningRoadmap(
        role_id=role.id,
        weekly_study_hours=roadmap.weekly_study_hours,
    )
    session.add(record)
    session.flush()
    for item in roadmap.milestones:
        resource_id = None
        if item.resource:
            resource = session.scalar(
                select(LearningResourceModel).where(
                    LearningResourceModel.title == item.resource.title,
                    LearningResourceModel.provider == item.resource.provider,
                )
            )
            resource_id = resource.id if resource else None
        session.add(
            RoadmapMilestoneModel(
                roadmap_id=record.id,
                week=item.week,
                skill_name=item.skill,
                why_it_matters=item.why_it_matters,
                goal=item.goal,
                practice_task=item.practice_task,
                mini_project=item.mini_project,
                resource_id=resource_id,
            )
        )
    session.commit()
    return record.id


def get_market_skill_percentages(session: Session) -> dict[str, float]:
    total_jobs = session.scalar(select(func.count(Job.id))) or 0
    if not total_jobs:
        return {}
    rows = session.execute(
        select(
            func.lower(Skill.name),
            func.count(func.distinct(JobSkill.job_id)),
        )
        .join(JobSkill, JobSkill.skill_id == Skill.id)
        .group_by(func.lower(Skill.name))
    ).all()
    return {
        name: round(count * 100 / total_jobs, 2)
        for name, count in rows
    }


def _score_role(
    role: CareerRole,
    skills: dict[str, SkillLevel],
    profile: StudentProfileInput,
) -> CareerRecommendation:
    matching: list[SkillMatch] = []
    partial: list[SkillMatch] = []
    missing: list[SkillMatch] = []
    weighted_coverage = 0.0
    total_weight = sum(item.weight for item in role.skills)
    for requirement in role.skills:
        level = skills.get(requirement.name.casefold())
        item = SkillMatch(
            name=requirement.name,
            weight=requirement.weight,
            required_level=requirement.minimum_level,
            student_level=level,
        )
        if level is None:
            missing.append(item)
        elif _LEVEL_RANK[level] < _LEVEL_RANK[requirement.minimum_level]:
            partial.append(item)
            weighted_coverage += requirement.weight * 0.5
        else:
            matching.append(item)
            weighted_coverage += requirement.weight

    score = round(weighted_coverage * 100 / total_weight, 1) if total_weight else 0
    explanation = (
        f"{len(matching)} requirement(s) meet the encoded level, "
        f"{len(partial)} are partial, and {len(missing)} are not listed. "
        f"The weighted coverage score is {score:.1f}%."
    )
    if profile.education:
        explanation += " Education is recorded as context and does not change the score."
    if profile.experience_years is not None:
        explanation += " Experience is recorded as context and does not change the score."
    preference_note = None
    if profile.preferred_location:
        preference_note = (
            "Preferred location is recorded, but role requirements are not "
            "location-specific."
        )
    if profile.interests:
        preference_note = (
            (preference_note + " " if preference_note else "")
            + "Interests are shown as context and do not change the score."
        )
    preferred_ids = {
        value.casefold().replace(" ", "-") for value in profile.preferred_roles
    }
    preferred_names = {value.casefold() for value in profile.preferred_roles}
    if profile.preferred_roles and not (
        role.id.casefold() in preferred_ids
        or role.name.casefold() in preferred_names
    ):
        preference_note = (
            (preference_note + " " if preference_note else "")
            + "No preferred role matched this catalog, so available roles were "
            "ranked instead."
        )
    return CareerRecommendation(
        role_id=role.id,
        role_name=role.name,
        description=role.description,
        match_score=score,
        matching_skills=matching,
        partial_skills=partial,
        missing_skills=missing,
        explanation=explanation,
        preference_note=preference_note,
    )


def _weighted_profile_score(
    role: CareerRole,
    skills: dict[str, SkillLevel],
) -> float:
    total_weight = sum(item.weight for item in role.skills)
    coverage = 0.0
    for requirement in role.skills:
        level = skills.get(requirement.name.casefold())
        if level is None:
            continue
        coverage += requirement.weight * (
            0.5
            if _LEVEL_RANK[level] < _LEVEL_RANK[requirement.minimum_level]
            else 1
        )
    return round(coverage * 100 / total_weight, 1) if total_weight else 0


def _normalize_profile_skills(
    profile: StudentProfileInput,
) -> tuple[dict[str, SkillLevel], list[str]]:
    dictionary = load_skill_dictionary()
    aliases: dict[str, str] = {}
    for definition in dictionary:
        for name in (definition.name, *definition.aliases):
            aliases[name.casefold()] = definition.name

    normalized: dict[str, SkillLevel] = {}
    unknown: list[str] = []
    for item in profile.technical_skills:
        value = item.name.strip().casefold()
        name = aliases.get(value)
        if name is None:
            if item.name.strip() not in unknown:
                unknown.append(item.name.strip())
            continue
        key = name.casefold()
        existing = normalized.get(key)
        if existing is None or _LEVEL_RANK[item.level] > _LEVEL_RANK[existing]:
            normalized[key] = item.level
    return normalized, unknown


def _get_role(role_id: str) -> CareerRole:
    role_key = role_id.strip().casefold()
    for role in load_role_catalog():
        if role.id.casefold() == role_key or role.name.casefold() == role_key:
            return role
    raise KeyError(f"Unknown career role: {role_id}")


def _gap_explanation(
    status: str,
    weight: int,
    demand: float | None,
) -> str:
    role_note = f"Role importance is {weight}/10."
    demand_note = (
        f" Observed market demand is {demand:.2f}% of stored unique postings."
        if demand is not None
        else ""
    )
    if status == "possessed":
        return f"Your reported level meets the role requirement. {role_note}"
    if status == "partial":
        return (
            f"You report this skill below the role's target level. "
            f"{role_note}{demand_note}"
        )
    return (
        f"This skill is not listed in your profile. {role_note}{demand_note}"
    )


def _weekly_goal(skill: str, study_hours: int) -> str:
    return (
        f"Spend about {study_hours} hour(s) exploring {skill}, learn its core "
        "concepts, and write a short summary in your own words."
    )


def _practice_task(skill: str) -> str:
    return (
        f"Complete a small guided exercise using {skill}; save the steps, "
        "result, and one reflection about what was difficult."
    )


def _mini_project(skill: str, role_name: str) -> str:
    return (
        f"Create a small {role_name} portfolio artifact demonstrating {skill}. "
        "Include a README, sample input/output, and limitations."
    )


def _read_json(path: Path, description: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Could not read the {description} catalog at {path}.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"The {description} catalog at {path} is invalid JSON.") from exc
