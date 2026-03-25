"""Definitions for the public data sources used by ingestion workloads.

The project starts with two external source families:

- public electricity market or balancing data
- public weather data used as an explanatory feature source

The helper objects in this module provide a typed and readable way to keep
those source definitions together.

Examples
--------
>>> [source.name for source in default_sources()]
['elexon-bmrs', 'open-meteo']
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicSource:
    """
    Represent a public API or file source used by the platform.

    Attributes
    ----------
    name : str
        Short identifier for the source.
    base_url : str
        Base URL used when constructing requests.
    cadence_minutes : int
        Expected ingestion cadence in minutes.

    Examples
    --------
    >>> source = PublicSource(name="open-meteo", base_url="https://api.open-meteo.com", cadence_minutes=30)
    >>> source.name
    'open-meteo'
    """

    name: str
    base_url: str
    cadence_minutes: int


def default_sources() -> list[PublicSource]:
    """
    Return the initial public sources used by the project.

    Returns
    -------
    list[PublicSource]
        Default public sources for the first ingestion implementation.

    Notes
    -----
    The list is deliberately short at the start of the project so the
    ingestion layer stays understandable while the infrastructure matures.

    Examples
    --------
    >>> [source.base_url for source in default_sources()]
    ['https://data.elexon.co.uk', 'https://api.open-meteo.com']
    """

    # The electricity source provides grid or market-facing demand signals.
    # The weather source provides exogenous context for forecasting models.
    return [
        PublicSource(
            name="elexon-bmrs",
            base_url="https://data.elexon.co.uk",
            cadence_minutes=30,
        ),
        PublicSource(
            name="open-meteo",
            base_url="https://api.open-meteo.com",
            cadence_minutes=30,
        ),
    ]
