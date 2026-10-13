from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app import models  # noqa: F401 - register ORM models on Base
from backend.app.models import (
    CareerRole as CareerRoleModel,
    CareerRoleSkill,
    LearningResource as LearningResourceModel,
    Skill,
)
from backend.app.services.careers import load_learning_resources, load_role_catalog
from backend.app.services.jobs import load_skill_dictionary


def seed_reference_data(session: Session) -> None:
    skills_by_name: dict[str, Skill] = {}
    for definition in load_skill_dictionary():
        skill = session.scalar(select(Skill).where(Skill.name == definition.name))
        if skill is None:
            skill = Skill(
                name=definition.name,
                category=definition.category,
                aliases=definition.aliases,
            )
            session.add(skill)
        else:
            skill.category = definition.category
            skill.aliases = definition.aliases
        skills_by_name[definition.name] = skill

    session.flush()
    roles_by_slug: dict[str, CareerRoleModel] = {}
    for definition in load_role_catalog():
        role = session.scalar(
            select(CareerRoleModel).where(CareerRoleModel.slug == definition.id)
        )
        if role is None:
            role = CareerRoleModel(
                slug=definition.id,
                name=definition.name,
                description=definition.description,
                interests=definition.interests,
            )
            session.add(role)
        else:
            role.name = definition.name
            role.description = definition.description
            role.interests = definition.interests
        roles_by_slug[definition.id] = role

    session.flush()
    for definition in load_role_catalog():
        role = roles_by_slug[definition.id]
        for requirement in definition.skills:
            skill = skills_by_name.get(requirement.name)
            if skill is None:
                continue
            link = session.get(CareerRoleSkill, (role.id, skill.id))
            if link is None:
                session.add(
                    CareerRoleSkill(
                        role_id=role.id,
                        skill_id=skill.id,
                        weight=requirement.weight,
                        minimum_level=requirement.minimum_level,
                    )
                )
            else:
                link.weight = requirement.weight
                link.minimum_level = requirement.minimum_level

    for skill_name, definition in load_learning_resources().items():
        skill = skills_by_name.get(skill_name.title())
        if skill is None:
            skill = next(
                (
                    candidate
                    for name, candidate in skills_by_name.items()
                    if name.casefold() == skill_name
                ),
                None,
            )
        if skill is None:
            continue
        resource = session.scalar(
            select(LearningResourceModel).where(
                LearningResourceModel.title == definition.title,
                LearningResourceModel.provider == definition.provider,
            )
        )
        if resource is None:
            session.add(
                LearningResourceModel(
                    skill_id=skill.id,
                    title=definition.title,
                    provider=definition.provider,
                    url=definition.url,
                    resource_type=definition.resource_type,
                    last_verified_at=datetime.fromisoformat(
                        definition.last_verified
                    ).replace(tzinfo=timezone.utc),
                )
            )
        else:
            resource.skill_id = skill.id
            resource.url = definition.url
            resource.resource_type = definition.resource_type
            resource.last_verified_at = datetime.fromisoformat(
                definition.last_verified
            ).replace(tzinfo=timezone.utc)


def main() -> None:
    if engine is None:
        raise SystemExit(
            "Database is not configured. Set CAREERCOMPASS_DATABASE_URL "
            "before initializing the database."
        )

    try:
        Base.metadata.create_all(bind=engine)
        with Session(engine) as session:
            with session.begin():
                seed_reference_data(session)
    except SQLAlchemyError as exc:
        raise SystemExit(f"Could not initialize database: {exc}") from exc
    print("CareerNavigator database tables and reference data are ready.")


if __name__ == "__main__":
    main()
