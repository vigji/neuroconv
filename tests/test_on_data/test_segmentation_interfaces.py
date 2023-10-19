from unittest import TestCase

from neuroconv.datainterfaces import (
    CaimanSegmentationInterface,
    CnmfeSegmentationInterface,
    ExtractSegmentationInterface,
    Suite2pSegmentationInterface,
)
from neuroconv.tools.testing.data_interface_mixins import (
    SegmentationExtractorInterfaceTestMixin,
)

try:
    from .setup_paths import OPHYS_DATA_PATH, OUTPUT_PATH
except ImportError:
    from setup_paths import OPHYS_DATA_PATH, OUTPUT_PATH


class TestCaimanSegmentationInterface(SegmentationExtractorInterfaceTestMixin, TestCase):
    data_interface_cls = CaimanSegmentationInterface
    interface_kwargs = dict(
        file_path=str(OPHYS_DATA_PATH / "segmentation_datasets" / "caiman" / "caiman_analysis.hdf5")
    )
    save_directory = OUTPUT_PATH


class TestCnmfeSegmentationInterface(SegmentationExtractorInterfaceTestMixin, TestCase):
    data_interface_cls = CnmfeSegmentationInterface
    interface_kwargs = dict(
        file_path=str(
            OPHYS_DATA_PATH / "segmentation_datasets" / "cnmfe" / "2014_04_01_p203_m19_check01_cnmfeAnalysis.mat"
        )
    )
    save_directory = OUTPUT_PATH


class TestExtractSegmentationInterface(SegmentationExtractorInterfaceTestMixin, TestCase):
    data_interface_cls = ExtractSegmentationInterface
    interface_kwargs = [
        dict(
            file_path=str(
                OPHYS_DATA_PATH
                / "segmentation_datasets"
                / "extract"
                / "2014_04_01_p203_m19_check01_extractAnalysis.mat"
            ),
            sampling_frequency=15.0,  # typically provided by user
        ),
        dict(
            file_path=str(OPHYS_DATA_PATH / "segmentation_datasets" / "extract" / "extract_public_output.mat"),
            sampling_frequency=15.0,  # typically provided by user
        ),
    ]
    save_directory = OUTPUT_PATH

    def test_extract_segmentation_interface_non_default_output_struct_name(self):
        """Test that the value for 'output_struct_name' is propagated to the extractor level
        where an error is raised."""
        file_path = OPHYS_DATA_PATH / "segmentation_datasets" / "extract" / "extract_public_output.mat"
        with self.assertRaisesRegex(AssertionError, "Output struct name 'not_output' not found in file."):
            ExtractSegmentationInterface(
                file_path=str(file_path),
                sampling_frequency=15.0,
                output_struct_name="not_output",
            )


class TestSuite2pSegmentationInterface(SegmentationExtractorInterfaceTestMixin, TestCase):
    data_interface_cls = Suite2pSegmentationInterface
    interface_kwargs = [
        dict(
            folder_path=str(OPHYS_DATA_PATH / "segmentation_datasets" / "suite2p"),
            channel_name="chan1",
            plane_name="plane0",
        ),
        dict(
            folder_path=str(OPHYS_DATA_PATH / "segmentation_datasets" / "suite2p"),
            channel_name="chan2",
            plane_name="plane0",
        ),
    ]
    save_directory = OUTPUT_PATH

    @classmethod
    def setUpClass(cls) -> None:
        plane_suffices = ["Chan1Plane0", "Chan2Plane0"]
        cls.imaging_plane_names = ["ImagingPlane" + plane_suffix for plane_suffix in plane_suffices]
        cls.plane_segmentation_names = ["PlaneSegmentation" + plane_suffix for plane_suffix in plane_suffices]
        # cls.segmentation_images_names = ["SegmentationImages" + plane for plane in cls.plane_segmentation_names]
        cls.chan1_trace_names = [
            trace + "PlaneSegmentationChan1Plane0" for trace in ["RoiResponseSeries", "Neuropil", "Deconvolved"]
        ]
        cls.chan2_trace_names = [trace + "PlaneSegmentationChan2Plane0" for trace in ["RoiResponseSeries", "Neuropil"]]

    def check_extracted_metadata(self, metadata: dict):
        """Check extracted metadata is adjusted correctly for each plane and channel combination."""
        self.assertEqual(metadata["Ophys"]["ImagingPlane"][0]["name"], self.imaging_plane_names[self.case])
        plane_segmentation_metadata = metadata["Ophys"]["ImageSegmentation"]["plane_segmentations"][0]
        self.assertEqual(plane_segmentation_metadata["name"], self.plane_segmentation_names[self.case])
        traces_metadata = metadata["Ophys"]["Fluorescence"]["roi_response_series"]
        for trace_ind, trace_metadata in enumerate(traces_metadata):
            trace_names = self.chan1_trace_names if self.case == 0 else self.chan2_trace_names
            self.assertEqual(trace_metadata["name"], trace_names[trace_ind])
