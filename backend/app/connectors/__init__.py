from .adzuna import AdzunaConnector
from .apec import ApecConnector
from .base import Connector, ConnectorResult, RawOffer
from .france_travail import FranceTravailConnector
from .hellowork import HelloWorkConnector
from .jsearch import JSearchConnector
from .wttj import WTTJConnector

ALL_CONNECTORS: list[Connector] = [
    FranceTravailConnector(),
    AdzunaConnector(),
    JSearchConnector(),
    WTTJConnector(),
    ApecConnector(),
    HelloWorkConnector(),
]

__all__ = [
    "ALL_CONNECTORS",
    "Connector",
    "ConnectorResult",
    "RawOffer",
]
