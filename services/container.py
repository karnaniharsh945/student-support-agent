"""Service container: builds and wires the application services (simple dependency injection)."""
from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from database.connection import Database
from services.memory import MemoryService
from services.policy_retrieval import PolicyRetriever
from services.records import FeeService, ScholarshipService, SupportRequestService
from services.tracing import TraceService


@dataclass
class Services:
    settings: Settings
    db: Database
    fees: FeeService
    scholarships: ScholarshipService
    support: SupportRequestService
    memory: MemoryService
    policy: PolicyRetriever
    tracer: TraceService


def build_services(settings: Settings, db: Database | None = None) -> Services:
    db = db or Database(settings.database_url)
    return Services(
        settings=settings, db=db, fees=FeeService(db), scholarships=ScholarshipService(db),
        support=SupportRequestService(db), memory=MemoryService(db),
        policy=PolicyRetriever(settings.policy_path), tracer=TraceService(db))
