"""Minimal service-status endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def root():
    return {"status": "Brokr API activa", "version": "4.8"}


@router.get("/ping")
def ping():
    return {"ok": True}
