"""Unit tests for the DatasetInfo Pydantic model."""
from io import StringIO
from unittest.mock import patch

import numpy as np

from neuroconv.tools.nwb_helpers import 


def MockHDF5DatasetConfig() -> DatasetInfo:
    return DatasetInfo(
        object_id="abc123",
        location="TestParent/data",
        full_shape=(2, 4),
        dtype=np.dtype("int16"),
    )


def test_dataset_info_print():
    """Test the printout display of a Dataset modellooks nice."""
    dataset_info = MockDatasetInfo()

    with patch("sys.stdout", new=StringIO()) as out:
        print(dataset_info)

    expected_print = """
TestParent/data
---------------
  maxshape: (2, 4)
  dtype: int16
"""
    assert out.getvalue() == expected_print


def test_dataset_info_repr():
    """Test the programmatic repr of a Dataset model is more dataclass-like."""
    dataset_info = MockDatasetInfo()

    # Important to keep the `repr` unmodified for appearance inside iterables of DatasetInfo objects
    expected_repr = (
        "DatasetInfo(object_id='abc123', location='TestParent/data', full_shape=(2, 4), dtype=dtype('int16'))"
    )
    assert repr(dataset_info) == expected_repr


def test_dataset_info_hashability():
    dataset_info = MockDatasetInfo()

    test_dict = {dataset_info: True}  # Technically this alone would raise an error if it didn't work...
    assert test_dict[dataset_info] is True  # ... but asserting this for good measure.
