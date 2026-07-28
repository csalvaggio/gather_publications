from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Member, PublicationCandidate, ReportingPeriod


class Source(ABC):
    name: str

    @abstractmethod
    def discover(self, member: Member, period: ReportingPeriod) -> list[PublicationCandidate]:
        raise NotImplementedError
