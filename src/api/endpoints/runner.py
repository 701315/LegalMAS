from fastapi import APIRouter, HTTPException

from db.uow import db_uow
from engine.runner import Runner

router = APIRouter(prefix="/runner", tags=["runner"])


@router.post("/runs")
async def run_deal(deal_id: str):
    try:
        async with db_uow() as uow:
            runner = Runner(uow)
            result = await runner.run_deal(deal_id)
        return {"status": "completed", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
