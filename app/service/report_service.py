from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from model.report import Report
from schemas.report import ReportCreate


async def create_report(db: AsyncSession, user_id: UUID, dados: ReportCreate) -> Report:
    report = Report(
        reporter_id=user_id,
        target_type=dados.target_type.value,
        target_id=dados.target_id,
        reason=dados.reason,
        description=dados.description,
        contact_email=dados.contact_email,
    )
    db.add(report)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você já denunciou este item",
        )
    await db.refresh(report)
    return report


async def list_my_reports(db: AsyncSession, user_id: UUID) -> list[Report]:
    result = await db.execute(
        select(Report)
        .where(Report.reporter_id == user_id)
        .order_by(Report.created_at.desc())
    )
    return list(result.scalars().all())
