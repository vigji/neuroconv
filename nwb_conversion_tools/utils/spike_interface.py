import uuid
from datetime import datetime
import warnings
import numpy as np
import distutils.version
from pathlib import Path
from typing import Union

import spikeextractors as se
import pynwb

from hdmf.data_utils import DataChunkIterator
from hdmf.backends.hdf5.h5_utils import H5DataIO
from .json_schema import dict_deep_update

PathType = Union[str, Path, None]
ArrayType = Union[list, np.ndarray]


def list_get(li: list, idx: int, default):
    """Safe index retrieval from list."""
    try:
        return li[idx]
    except IndexError:
        return default


def set_dynamic_table_property(dynamic_table, row_ids, property_name, values, index=False,
                               default_value=np.nan, table=False, description='no description'):
    if not isinstance(row_ids, list) or not all(isinstance(x, int) for x in row_ids):
        raise TypeError("'ids' must be a list of integers")
    ids = list(dynamic_table.id[:])
    if any([i not in ids for i in row_ids]):
        raise ValueError("'ids' contains values outside the range of existing ids")
    if not isinstance(property_name, str):
        raise TypeError("'property_name' must be a string")
    if len(row_ids) != len(values) and index is False:
        raise ValueError("'ids' and 'values' should be lists of same size")

    if index is False:
        if property_name in dynamic_table:
            for (row_id, value) in zip(row_ids, values):
                dynamic_table[property_name].data[ids.index(row_id)] = value
        else:
            col_data = [default_value] * len(ids)  # init with default val
            for (row_id, value) in zip(row_ids, values):
                col_data[ids.index(row_id)] = value
            dynamic_table.add_column(
                name=property_name,
                description=description,
                data=col_data,
                index=index,
                table=table
            )
    else:
        if property_name in dynamic_table:
            # TODO
            raise NotImplementedError
        else:
            dynamic_table.add_column(
                name=property_name,
                description=description,
                data=values,
                index=index,
                table=table
            )


def check_module(nwbfile, name: str, description: str = None):
    """
    Check if processing module exists. If not, create it. Then return module.

    Parameters
    ----------
    nwbfile: pynwb.NWBFile
    name: str
    description: str | None (optional)

    Returns
    -------
    pynwb.module
    """
    assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile"
    if name in nwbfile.modules:
        return nwbfile.modules[name]
    else:
        if description is None:
            description = name
        return nwbfile.create_processing_module(name, description)


def get_nwb_metadata(recording: se.RecordingExtractor, metadata: dict = None):
    """
    Return default metadata for all recording fields.
    
    Parameters
    ----------
    recording: RecordingExtractor
    metadata: dict
        metadata info for constructing the nwb file (optional).
    """
    metadata = dict(
        NWBFile=dict(
            session_description="Auto-generated by NwbRecordingExtractor without description.",
            identifier=str(uuid.uuid4()),
            session_start_time=datetime(1970, 1, 1)
        ),
        Ecephys=dict(
            Device=[
                dict(
                    name="Device",
                    description="no description"
                )
            ],
            ElectrodeGroup=[
                dict(
                    name=str(gn),
                    description="no description",
                    location="unknown",
                    device="Device"
                ) for gn in np.unique(recording.get_channel_groups())
            ]
        )
    )
    return metadata


def add_devices(
    recording: se.RecordingExtractor, 
    nwbfile=None, 
    metadata: dict = None
):
    """
    Auxiliary static method for nwbextractor.

    Adds device information to nwbfile object.
    Will always ensure nwbfile has at least one device, but multiple
    devices within the metadata list will also be created.

    Parameters
    ----------
    recording: RecordingExtractor
    nwbfile: NWBFile
        nwb file to which the recording information is to be added
    metadata: dict
        metadata info for constructing the nwb file (optional).
        Should be of the format
            metadata['Ecephys']['Device'] = [{'name': my_name,
                                                'description': my_description}, ...]

    Missing keys in an element of metadata['Ecephys']['Device'] will be auto-populated with defaults.
    """
    if nwbfile is not None:
        assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile"
    defaults = dict(
        name="Device",
        description="Ecephys probe."
    )
    if metadata is None or 'Device' not in metadata['Ecephys']:
        metadata = dict(
            Ecephys=dict(
                Device=[defaults]
            )
        )
    if metadata is None:
        metadata = dict() 

    if 'Ecephys' not in metadata:
        metadata['Ecephys'] = dict()

    if 'Device' not in metadata['Ecephys']:
        metadata['Ecephys']['Device'] = [defaults]

    for dev in metadata['Ecephys']['Device']:
        if dev.get('name', defaults['name']) not in nwbfile.devices:
            nwbfile.create_device(**dict(defaults, **dev))


def add_electrode_groups(
    recording: se.RecordingExtractor, 
    nwbfile=None, 
    metadata: dict = None
):
    """
    Auxiliary static method for nwbextractor.

    Adds electrode group information to nwbfile object.
    Will always ensure nwbfile has at least one electrode group.
    Will auto-generate a linked device if the specified name does not exist in the nwbfile.

    Parameters
    ----------
    recording: RecordingExtractor
    nwbfile: NWBFile
        nwb file to which the recording information is to be added
    metadata: dict
        metadata info for constructing the nwb file (optional).
        Should be of the format
            metadata['Ecephys']['ElectrodeGroup'] = [{'name': my_name,
                                                        'description': my_description,
                                                        'location': electrode_location,
                                                        'device_name': my_device_name}, ...]

    Missing keys in an element of metadata['Ecephys']['ElectrodeGroup'] will be auto-populated with defaults.

    Group names set by RecordingExtractor channel properties will also be included with passed metadata,
    but will only use default description and location.
    """
    if nwbfile is not None:
        assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile"
    if len(nwbfile.devices) == 0:
        add_devices(recording, nwbfile)
    if metadata is None:
        metadata = dict()

    if 'Ecephys' not in metadata:
        metadata['Ecephys'] = dict()

    defaults = [
        dict(
            name=str(group_id),
            description="no description",
            location="unknown",
            device=[i.name for i in nwbfile.devices.values()][0]
        )
        for group_id in np.unique(recording.get_channel_groups())
    ]

    if 'ElectrodeGroup' not in metadata['Ecephys']:
        metadata['Ecephys']['ElectrodeGroup'] = defaults

    assert all([isinstance(x, dict) for x in metadata['Ecephys']['ElectrodeGroup']]), \
        "Expected metadata['Ecephys']['ElectrodeGroup'] to be a list of dictionaries!"

    for grp in metadata['Ecephys']['ElectrodeGroup']:
        if grp.get('name', defaults[0]['name']) not in nwbfile.electrode_groups:
            device_name = grp.get('device', defaults[0]['device'])
            if device_name not in nwbfile.devices:
                new_device = dict(
                    Ecephys=dict(
                        Device=dict(
                            name=device_name
                        )
                    )
                )
                add_devices(recording, nwbfile, metadata=new_device)
                warnings.warn(f"Device \'{device_name}\' not detected in "
                              "attempted link to electrode group! Automatically generating.")
            electrode_group_kwargs = dict(defaults[0], **grp)
            electrode_group_kwargs.update(device=nwbfile.devices[device_name])
            nwbfile.create_electrode_group(**electrode_group_kwargs)

    if not nwbfile.electrode_groups:
        device_name = list(nwbfile.devices.keys())[0]
        device = nwbfile.devices[device_name]
        if len(nwbfile.devices) > 1:
            warnings.warn("More than one device found when adding electrode group "
                          f"via channel properties: using device \'{device_name}\'. To use a "
                          "different device, indicate it the metadata argument.")

        electrode_group_kwargs = dict(defaults[0])
        electrode_group_kwargs.update(device=device)
        for grp_name in np.unique(recording.get_channel_groups()).tolist():
            electrode_group_kwargs.update(name=str(grp_name))
            nwbfile.create_electrode_group(**electrode_group_kwargs)


def add_electrodes(
    recording: se.RecordingExtractor, 
    nwbfile=None, 
    metadata: dict = None,
    write_scaled: bool = True,
    exclude: tuple = ()
):
    """
    Auxiliary static method for nwbextractor.

    Adds channels from recording object as electrodes to nwbfile object.

    Parameters
    ----------
    recording: RecordingExtractor
    nwbfile: NWBFile
        nwb file to which the recording information is to be added
    metadata: dict
        metadata info for constructing the nwb file (optional).
        Should be of the format
            metadata['Ecephys']['Electrodes'] = [{'name': my_name,
                                                    'description': my_description,
                                                    'data': [my_electrode_data]}, ...]
        where each dictionary corresponds to a column in the Electrodes table and [my_electrode_data] is a list in
        one-to-one correspondence with the nwbfile electrode ids and RecordingExtractor channel ids.
    write_scaled: bool (optional, defaults to True)
        If True, writes the scaled traces (return_scaled=True)
    exclude: tuple
        TODO - Add description

    Missing keys in an element of metadata['Ecephys']['ElectrodeGroup'] will be auto-populated with defaults
    whenever possible.

    If 'my_name' is set to one of the required fields for nwbfile
    electrodes (id, x, y, z, imp, loccation, filtering, group_name),
    then the metadata will override their default values.

    Setting 'my_name' to metadata field 'group' is not supported as the linking to
    nwbfile.electrode_groups is handled automatically; please specify the string 'group_name' in this case.

    If no group information is passed via metadata, automatic linking to existing electrode groups,
    possibly including the default, will occur.
    """
    if nwbfile is not None:
        assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile"
    if nwbfile.electrode_groups is None or len(nwbfile.electrode_groups) == 0:
        se.NwbRecordingExtractor.add_electrode_groups(recording, nwbfile, metadata)
    # For older versions of pynwb, we need to manually add these columns
    if distutils.version.LooseVersion(pynwb.__version__) < '1.3.0':
        if nwbfile.electrodes is None or 'rel_x' not in nwbfile.electrodes.colnames:
            nwbfile.add_electrode_column('rel_x', 'x position of electrode in electrode group')
        if nwbfile.electrodes is None or 'rel_y' not in nwbfile.electrodes.colnames:
            nwbfile.add_electrode_column('rel_y', 'y position of electrode in electrode group')

    defaults = dict(
        x=np.nan,
        y=np.nan,
        z=np.nan,
        # There doesn't seem to be a canonical default for impedence, if missing.
        # The NwbRecordingExtractor follows the -1.0 convention, other scripts sometimes use np.nan
        imp=-1.0,
        location="unknown",
        filtering="none",
        group_name="0"
    )
    if metadata is None:
        metadata = dict(Ecephys=dict())

    if 'Ecephys' not in metadata:
        metadata['Ecephys'] = dict()

    if 'Electrodes' not in metadata['Ecephys']:
        metadata['Ecephys']['Electrodes'] = []

    assert all([isinstance(x, dict) and set(x.keys()) == set(['name', 'description', 'data'])
                and isinstance(x['data'], list) for x in metadata['Ecephys']['Electrodes']]), \
        "Expected metadata['Ecephys']['Electrodes'] to be a list of dictionaries!"
    assert all([x['name'] != 'group' for x in metadata['Ecephys']['Electrodes']]), \
        "Passing metadata field 'group' is deprecated; pass group_name instead!"

    if nwbfile.electrodes is None:
        nwb_elec_ids = []
    else:
        nwb_elec_ids = nwbfile.electrodes.id.data[:]

    elec_columns = {}  # name: description
    property_names = set()
    for chan_id in recording.get_channel_ids():
        for i in recording.get_channel_property_names(channel_id=chan_id):
            property_names.add(i)
    for prop in property_names:
        if prop not in ['gain', 'offset', 'location', 'name'] + list(exclude):
            # property 'gain' should not be in the NWB electrodes_table
            # property 'brain_area' of RX channels corresponds to 'location' of NWB electrodes
            # property 'offset' should not be in the NWB electrodes_table as not officially supported by schema v2.2.5

            data = []
            for chan_id in recording.get_channel_ids():
                if prop in recording.get_channel_property_names(channel_id=chan_id):
                    data.append(recording.get_channel_property(channel_id=chan_id, property_name=prop))
                else:
                    if len(data) > 0 and isinstance(data[-1], str):
                        data.append('')
                    elif len(data) > 0:
                        data.append(np.nan)
            prop = 'location' if prop == 'brain_area' else prop
            prop = 'group_name' if prop == 'group' else prop
            elec_columns[prop] = dict(description=prop, data=data)

    for x in metadata['Ecephys']['Electrodes']:
        name = x.pop('name')
        if name not in elec_columns:
            elec_columns[name] = dict(description=name)
        if 'description' in x:
            elec_columns[name]['description'] = x['description']
        if 'data' in x:
            assert len(x['data']) == recording.get_num_channels()
            elec_columns[name]['data'] = x['data']

    for name, dat in elec_columns.items():
        if 'data' not in dat and name not in defaults:
            raise ValueError(f"no data for electrode column {name}")

    for name, des_dict in elec_columns.items():
        if name not in defaults:
            nwbfile.add_electrode_column(name=name, description=des_dict['description'])

    for j, channel_id in enumerate(recording.get_channel_ids()):
        if channel_id not in nwb_elec_ids:
            electrode_kwargs = dict(defaults)
            electrode_kwargs.update(id=channel_id)

            # recording.get_channel_locations defaults to np.nan if there are none
            location = recording.get_channel_locations(channel_ids=channel_id)[0]
            if all([not np.isnan(loc) for loc in location]):
                # property 'location' of RX channels corresponds to rel_x and rel_ y of NWB electrodes
                electrode_kwargs.update(
                    dict(
                        rel_x=float(location[0]),
                        rel_y=float(location[1])
                    )
                )

            for name, desc in elec_columns.items():
                if name == 'group_name':
                    group_name = str(list_get(desc['data'], j, defaults['group_name']))
                    if group_name not in nwbfile.electrode_groups:
                        warnings.warn(f"Electrode group for electrode {channel_id} was not "
                                      "found in the nwbfile! Automatically adding.")
                        missing_group_metadata = dict(
                            Ecephys=dict(
                                ElectrodeGroup=[dict(
                                    name=group_name,
                                    description="no description",
                                    location="unknown",
                                    device="Device"
                                )]
                            )
                        )
                        se.NwbRecordingExtractor.add_electrode_groups(recording, nwbfile, missing_group_metadata)
                    electrode_kwargs.update(
                        dict(
                            group=nwbfile.electrode_groups[group_name],
                            group_name=group_name
                        )
                    )
                elif 'data' in desc:
                    electrode_kwargs[name] = desc['data'][j]

            if not any([x.get('name', '') == 'group_name' for x in metadata['Ecephys']['Electrodes']]):
                group_id = recording.get_channel_groups(channel_ids=channel_id)[0]
                if str(group_id) in nwbfile.electrode_groups:
                    electrode_kwargs.update(
                        dict(
                            group=nwbfile.electrode_groups[str(group_id)],
                            group_name=str(group_id)
                        )
                    )
                else:
                    warnings.warn("No metadata was passed specifying the electrode group for "
                                  f"electrode {channel_id}, and the internal recording channel group was "
                                  f"assigned a value (str({group_id})) not present as electrode "
                                  "groups in the NWBFile! Electrode will not be added.")
                    continue

            nwbfile.add_electrode(**electrode_kwargs)
    assert nwbfile.electrodes is not None, \
        "Unable to form electrode table! Check device, electrode group, and electrode metadata."


def add_electrical_series(
    recording: se.RecordingExtractor,
    nwbfile=None,
    metadata: dict = None,
    buffer_mb: int = 500,
    use_times: bool = False,
    write_as: str = 'raw',
    es_key: str = None,
    write_scaled: bool = False
):
    """
    Auxiliary static method for nwbextractor.

    Adds traces from recording object as ElectricalSeries to nwbfile object.

    Parameters
    ----------
    recording: RecordingExtractor
    nwbfile: NWBFile
        nwb file to which the recording information is to be added
    metadata: dict
        metadata info for constructing the nwb file (optional).
        Should be of the format
            metadata['Ecephys']['ElectricalSeries'] = {'name': my_name,
                                                        'description': my_description}
    buffer_mb: int (optional, defaults to 500MB)
        maximum amount of memory (in MB) to use per iteration of the
        DataChunkIterator (requires traces to be memmap objects)
    use_times: bool (optional, defaults to False)
        If True, the times are saved to the nwb file using recording.frame_to_time(). If False (defualut),
        the sampling rate is used.
    write_as: str (optional, defaults to 'raw')
        How to save the traces data in the nwb file. Options: 
        - 'raw' will save it in acquisition
        - 'processed' will save it as FilteredEphys, in a processing module
        - 'lfp' will save it as LFP, in a processing module
    es_key: str (optional)
        Key in metadata dictionary containing metadata info for the specific electrical series
    write_scaled: bool (optional, defaults to True)
        If True, writes the scaled traces (return_scaled=True)

    Missing keys in an element of metadata['Ecephys']['ElectrodeGroup'] will be auto-populated with defaults
    whenever possible.
    """
    if nwbfile is not None:
        assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile!"

    assert buffer_mb > 10, "'buffer_mb' should be at least 10MB to ensure data can be chunked!"

    if not nwbfile.electrodes:
        add_electrodes(recording, nwbfile, metadata)

    assert write_as in ['raw', 'processed', 'lfp'], \
        f"'write_as' should be 'raw', 'processed' or 'lfp', but intead received value {write_as}"

    if write_as == 'raw':
        eseries_kwargs = dict(
            name="ElectricalSeries_raw",
            description="Raw acquired data",
            comments="Generated from SpikeInterface::NwbRecordingExtractor"
        )
    elif write_as == 'processed':
        eseries_kwargs = dict(
            name="ElectricalSeries_processed",
            description="Processed data",
            comments="Generated from SpikeInterface::NwbRecordingExtractor"
        )
        # Check for existing processing module and data interface
        ecephys_mod = check_module(
            nwbfile=nwbfile,
            name='ecephys',
            description="Intermediate data from extracellular electrophysiology recordings, e.g., LFP."
        )
        if 'Processed' not in ecephys_mod.data_interfaces:
            ecephys_mod.add(pynwb.ecephys.FilteredEphys(name='Processed'))
    elif write_as == 'lfp':
        eseries_kwargs = dict(
            name="ElectricalSeries_lfp",
            description="Processed data - LFP",
            comments="Generated from SpikeInterface::NwbRecordingExtractor"
        )
        # Check for existing processing module and data interface
        ecephys_mod = check_module(
            nwbfile=nwbfile,
            name='ecephys',
            description="Intermediate data from extracellular electrophysiology recordings, e.g., LFP."
        )
        if 'LFP' not in ecephys_mod.data_interfaces:
            ecephys_mod.add(pynwb.ecephys.LFP(name='LFP'))

    # If user passed metadata info, overwrite defaults
    if metadata is not None and 'Ecephys' in metadata and es_key is not None:
        assert es_key in metadata['Ecephys'], f"metadata['Ecephys'] dictionary does not contain key '{es_key}'"
        eseries_kwargs.update(metadata['Ecephys'][es_key])

    # Check for existing names in nwbfile
    if write_as == 'raw':
        assert eseries_kwargs['name'] not in nwbfile.acquisition, \
            f"Raw ElectricalSeries '{eseries_kwargs['name']}' is already written in the NWBFile!"
    elif write_as == 'processed':
        assert eseries_kwargs['name'] not in nwbfile.processing['ecephys'].data_interfaces['Processed'].electrical_series, \
            f"Processed ElectricalSeries '{eseries_kwargs['name']}' is already written in the NWBFile!"
    elif write_as == 'lfp':
        assert eseries_kwargs['name'] not in nwbfile.processing['ecephys'].data_interfaces['LFP'].electrical_series, \
            f"LFP ElectricalSeries '{eseries_kwargs['name']}' is already written in the NWBFile!"

    # Electrodes table region
    channel_ids = recording.get_channel_ids()
    table_ids = [list(nwbfile.electrodes.id[:]).index(id) for id in channel_ids]
    electrode_table_region = nwbfile.create_electrode_table_region(
        region=table_ids,
        description="electrode_table_region"
    )
    eseries_kwargs.update(electrodes=electrode_table_region)

    # channels gains - for RecordingExtractor, these are values to cast traces to uV.
    # For nwb, the conversions (gains) cast the data to Volts.
    # To get traces in Volts we take data*channel_conversion*conversion.
    channel_conversion = recording.get_channel_gains()
    channel_offset = recording.get_channel_offsets()
    unsigned_coercion = channel_offset / channel_conversion
    if not np.all([x.is_integer() for x in unsigned_coercion]):
        raise NotImplementedError(
            "Unable to coerce underlying unsigned data type to signed type, which is currently required for NWB "
            "Schema v2.2.5! Please specify 'write_scaled=True'."
        )
    elif np.any(unsigned_coercion != 0):
        warnings.warn(
            "NWB Schema v2.2.5 does not officially support channel offsets. The data will be converted to a signed "
            "type that does not use offsets."
        )
        unsigned_coercion = unsigned_coercion.astype(int)
    if write_scaled:
        eseries_kwargs.update(conversion=1e-6)
    else:
        if len(np.unique(channel_conversion)) == 1:  # if all gains are equal
            eseries_kwargs.update(conversion=channel_conversion[0] * 1e-6)
        else:
            eseries_kwargs.update(conversion=1e-6)
            eseries_kwargs.update(channel_conversion=channel_conversion)

    if isinstance(recording.get_traces(end_frame=5, return_scaled=write_scaled), np.memmap) \
            and np.all(channel_offset == 0):
        n_bytes = np.dtype(recording.get_dtype()).itemsize
        buffer_size = int(buffer_mb * 1e6) // (recording.get_num_channels() * n_bytes)
        ephys_data = DataChunkIterator(
            data=recording.get_traces(return_scaled=write_scaled).T,  # nwb standard is time as zero axis
            buffer_size=buffer_size
        )
    else:
        def data_generator(recording, channels_ids, unsigned_coercion, write_scaled):
            for i, ch in enumerate(channels_ids):
                data = recording.get_traces(channel_ids=[ch], return_scaled=write_scaled)
                if not write_scaled:
                    data_dtype_name = data.dtype.name
                    if data_dtype_name.startswith("uint"):
                        data_dtype_name = data_dtype_name[1:]  # Retain memory of signed data type
                    data = data + unsigned_coercion[i]
                    data = data.astype(data_dtype_name)
                yield data.flatten()
        ephys_data = DataChunkIterator(
            data=data_generator(
                recording=recording,
                channels_ids=channel_ids,
                unsigned_coercion=unsigned_coercion,
                write_scaled=write_scaled
            ),
            iter_axis=1,  # nwb standard is time as zero axis
            maxshape=(recording.get_num_frames(), recording.get_num_channels())
        )

    eseries_kwargs.update(data=H5DataIO(ephys_data, compression="gzip"))
    if not use_times:
        eseries_kwargs.update(
            starting_time=recording.frame_to_time(0),
            rate=float(recording.get_sampling_frequency())
        )
    else:
        eseries_kwargs.update(
            timestamps=H5DataIO(
                recording.frame_to_time(np.arange(recording.get_num_frames())),
                compression="gzip"
            )
        )

    # Add ElectricalSeries to nwbfile object
    es = pynwb.ecephys.ElectricalSeries(**eseries_kwargs)
    if write_as == 'raw':
        nwbfile.add_acquisition(es)
    elif write_as == 'processed':
        ecephys_mod.data_interfaces['Processed'].add_electrical_series(es)
    elif write_as == 'lfp':
        ecephys_mod.data_interfaces['LFP'].add_electrical_series(es)
        

def add_epochs(
    recording: se.RecordingExtractor, 
    nwbfile=None,
    metadata: dict = None
):
    """
    Auxiliary static method for nwbextractor.
    Adds epochs from recording object to nwbfile object.

    Parameters
    ----------
    recording: RecordingExtractor
    nwbfile: NWBFile
        nwb file to which the recording information is to be added
    metadata: dict
        metadata info for constructing the nwb file (optional).
    """
    if nwbfile is not None:
        assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile"

    # add/update epochs
    for epoch_name in recording.get_epoch_names():
        epoch = recording.get_epoch_info(epoch_name)
        if nwbfile.epochs is None:
            nwbfile.add_epoch(
                start_time=recording.frame_to_time(epoch['start_frame']),
                stop_time=recording.frame_to_time(epoch['end_frame'] - 1),
                tags=epoch_name
            )
        else:
            if [epoch_name] in nwbfile.epochs['tags'][:]:
                ind = nwbfile.epochs['tags'][:].index([epoch_name])
                nwbfile.epochs['start_time'].data[ind] = recording.frame_to_time(epoch['start_frame'])
                nwbfile.epochs['stop_time'].data[ind] = recording.frame_to_time(epoch['end_frame'])
            else:
                nwbfile.add_epoch(
                    start_time=recording.frame_to_time(epoch['start_frame']),
                    stop_time=recording.frame_to_time(epoch['end_frame']),
                    tags=epoch_name
                )

def add_all_to_nwbfile(
    recording: se.RecordingExtractor,
    nwbfile=None,
    buffer_mb: int = 500,
    use_times: bool = False,
    metadata: dict = None,
    write_as: str = 'raw',
    es_key: str = None,
    write_scaled: bool = False
):
    """
    Auxiliary static method for nwbextractor.

    Adds all recording related information from recording object and metadata to the nwbfile object.

    Parameters
    ----------
    recording: RecordingExtractor
    nwbfile: NWBFile
        nwb file to which the recording information is to be added
    buffer_mb: int (optional, defaults to 500MB)
        maximum amount of memory (in MB) to use per iteration of the
        DataChunkIterator (requires traces to be memmap objects)
    use_times: bool
        If True, the times are saved to the nwb file using recording.frame_to_time(). If False (defualut),
        the sampling rate is used.
    metadata: dict
        metadata info for constructing the nwb file (optional).
        Check the auxiliary function docstrings for more information
        about metadata format.
    write_as: str (optional, defaults to 'raw')
        How to save the traces data in the nwb file. Options: 
        - 'raw' will save it in acquisition
        - 'processed' will save it as FilteredEphys, in a processing module
        - 'lfp' will save it as LFP, in a processing module
    es_key: str (optional)
        Key in metadata dictionary containing metadata info for the specific electrical series
    write_scaled: bool (optional, defaults to True)
        If True, writes the scaled traces (return_scaled=True)
    """
    if nwbfile is not None:
        assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile"

    add_devices(
        recording=recording,
        nwbfile=nwbfile,
        metadata=metadata
    )

    add_electrode_groups(
        recording=recording,
        nwbfile=nwbfile,
        metadata=metadata
    )
    
    add_electrodes(
        recording=recording,
        nwbfile=nwbfile,
        metadata=metadata,
        write_scaled=write_scaled
    )
    
    add_electrical_series(
        recording=recording,
        nwbfile=nwbfile,
        buffer_mb=buffer_mb,
        use_times=use_times,
        metadata=metadata,
        write_as=write_as,
        es_key=es_key,
        write_scaled=write_scaled
    )

    add_epochs(
        recording=recording,
        nwbfile=nwbfile,
        metadata=metadata
    )


def write_recording(
    recording: se.RecordingExtractor,
    save_path: PathType = None,
    overwrite: bool = False,
    nwbfile=None,
    buffer_mb: int = 500,
    use_times: bool = False,
    metadata: dict = None,
    write_as: str = 'raw',
    es_key: str = None,
    write_scaled: bool = False
):
    """
    Primary method for writing a RecordingExtractor object to an NWBFile.

    Parameters
    ----------
    recording: RecordingExtractor
    save_path: PathType
        Required if an nwbfile is not passed. Must be the path to the nwbfile
        being appended, otherwise one is created and written.
    overwrite: bool
        If using save_path, whether or not to overwrite the NWBFile if it already exists.
    nwbfile: NWBFile
        Required if a save_path is not specified. If passed, this function
        will fill the relevant fields within the nwbfile. E.g., calling
        spikeextractors.NwbRecordingExtractor.write_recording(
            my_recording_extractor, my_nwbfile
        )
        will result in the appropriate changes to the my_nwbfile object.
    buffer_mb: int (optional, defaults to 500MB)
        maximum amount of memory (in MB) to use per iteration of the
        DataChunkIterator (requires traces to be memmap objects)
    use_times: bool
        If True, the times are saved to the nwb file using recording.frame_to_time(). If False (defualut),
        the sampling rate is used.
    metadata: dict
        metadata info for constructing the nwb file (optional). Should be
        of the format
            metadata['Ecephys'] = {}
        with keys of the forms
            metadata['Ecephys']['Device'] = [{'name': my_name,
                                                'description': my_description}, ...]
            metadata['Ecephys']['ElectrodeGroup'] = [{'name': my_name,
                                                        'description': my_description,
                                                        'location': electrode_location,
                                                        'device': my_device_name}, ...]
            metadata['Ecephys']['Electrodes'] = [{'name': my_name,
                                                    'description': my_description,
                                                    'data': [my_electrode_data]}, ...]
            metadata['Ecephys']['ElectricalSeries'] = {'name': my_name,
                                                        'description': my_description}
    write_as: str (optional, defaults to 'raw')
        How to save the traces data in the nwb file. Options: 
        - 'raw' will save it in acquisition
        - 'processed' will save it as FilteredEphys, in a processing module
        - 'lfp' will save it as LFP, in a processing module
    es_key: str (optional)
        Key in metadata dictionary containing metadata info for the specific electrical series
    write_scaled: bool (optional, defaults to True)
        If True, writes the scaled traces (return_scaled=True)
    """

    if nwbfile is not None:
        assert isinstance(nwbfile, pynwb.NWBFile), "'nwbfile' should be of type pynwb.NWBFile"

    assert distutils.version.LooseVersion(pynwb.__version__) >= '1.3.3', \
        "'write_recording' not supported for version < 1.3.3. Run pip install --upgrade pynwb"

    assert save_path is None or nwbfile is None, \
        "Either pass a save_path location, or nwbfile object, but not both!"

    # Update any previous metadata with user passed dictionary
    if hasattr(recording, 'nwb_metadata'):
        metadata = dict_deep_update(recording.nwb_metadata, metadata)
    elif metadata is None:
        # If not NWBRecording, make metadata from information available on Recording
        metadata = get_nwb_metadata(recording=recording)

    if nwbfile is None:
        if Path(save_path).is_file() and not overwrite:
            read_mode = 'r+'
        else:
            read_mode = 'w'

        with pynwb.NWBHDF5IO(str(save_path), mode=read_mode) as io:
            if read_mode == 'r+':
                nwbfile = io.read()
            else:
                # Default arguments will be over-written if contained in metadata
                nwbfile_kwargs = dict(
                    session_description="Auto-generated by NwbRecordingExtractor without description.",
                    identifier=str(uuid.uuid4()),
                    session_start_time=datetime(1970, 1, 1)
                )
                if metadata is not None and 'NWBFile' in metadata:
                    nwbfile_kwargs.update(metadata['NWBFile'])
                nwbfile = pynwb.NWBFile(**nwbfile_kwargs)

            add_all_to_nwbfile(
                recording=recording,
                nwbfile=nwbfile,
                buffer_mb=buffer_mb,
                metadata=metadata,
                use_times=use_times,
                write_as=write_as,
                es_key=es_key,
                write_scaled=write_scaled
            )

            # Write to file
            io.write(nwbfile)
    else:
        add_all_to_nwbfile(
            recording=recording,
            nwbfile=nwbfile,
            buffer_mb=buffer_mb,
            use_times=use_times,
            metadata=metadata,
            write_as=write_as,
            es_key=es_key,
            write_scaled=write_scaled
        )
