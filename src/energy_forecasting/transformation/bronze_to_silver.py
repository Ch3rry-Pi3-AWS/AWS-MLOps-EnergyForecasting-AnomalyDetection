"""Helpers for Bronze-to-Silver transformation jobs.

The initial transformation helpers are intentionally small. Their main role is
to keep naming and partition path generation consistent before the Glue-based
transformation layer is added in full.

Examples
--------
>>> build_partition_path("weather", "2026-03-24")
'weather/dt=2026-03-24/'
"""


def build_partition_path(dataset_name: str, partition_date: str) -> str:
    """
    Build a deterministic partition path for transformed outputs.

    Parameters
    ----------
    dataset_name : str
        Logical dataset name, for example `energy_demand`.
    partition_date : str
        Partition date in ISO-style form such as `2026-03-24`.

    Returns
    -------
    str
        Partition path in the form `<dataset>/dt=<date>/`.

    Notes
    -----
    The returned path matches a common data-lake partitioning convention and
    keeps Bronze-to-Silver outputs predictable for both downstream jobs and
    ad hoc inspection.

    Examples
    --------
    >>> build_partition_path("energy_demand", "2026-03-24")
    'energy_demand/dt=2026-03-24/'
    """

    return f"{dataset_name}/dt={partition_date}/"
