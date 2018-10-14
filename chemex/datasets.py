"""The dataset module contains the code for handling the experimental data."""
import configparser
import copy
import importlib
import operator
import pathlib
import sys

import numpy as np

from chemex import util
from chemex.experiments import base_profile


class DataSet:
    """DataSet class for handling experimental data."""

    def __init__(self, other=None):
        self.dataset = []
        self.chisq_ref = 1e32

        if isinstance(other, DataSet):
            self.dataset = copy.deepcopy(other.dataset)

        elif isinstance(other, base_profile.BaseProfile):
            self.dataset.append(other)

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, key):
        return self.dataset[key]

    def __iter__(self):
        for some_data in self.dataset:
            yield some_data

    def __add__(self, other):
        data_sum = DataSet(self)
        data_sum.dataset.extend(other.data)
        return data_sum

    def __radd__(self, other):
        return self.__add__(other)

    def __iadd__(self, other):
        self.dataset.extend(other.data)
        return self

    @property
    def ndata(self):
        return sum(len(profile) for profile in self.dataset)

    def append(self, profile):
        """Append data to an exisiting dataset."""
        if not isinstance(profile, base_profile.BaseProfile):
            raise TypeError
        self.dataset.append(profile)

    def calculate_residuals(self, params, verbose=True, threshold=1e-3):
        """Calculate the residuals."""

        residuals = np.concatenate(
            [profile.calculate_residuals(params) for profile in self.dataset]
        )

        if verbose:
            chisq = sum(residuals ** 2)

            change = (chisq - self.chisq_ref) / self.chisq_ref

            if change < -threshold:
                nvarys = len([param for param in params.values() if param.vary])
                redchi = chisq / (self.ndata - nvarys)

                print(f"  * {chisq:.3e} / {redchi:.3e}")

                self.chisq_ref = chisq

        return residuals

    def write_to(self, params, path):
        """Write experimental and fitted profiles to a file."""
        datasets = dict()

        for profile in self.dataset:
            experiment_name = profile.experiment_name
            datasets.setdefault(experiment_name, list()).append(profile)

        for experiment_name, data in datasets.items():

            filename = path / experiment_name
            filename = filename.with_suffix(".dat")

            print(f"  * {filename}")

            with filename.open("w") as f:
                for profile in sorted(data, key=operator.attrgetter("peak")):
                    f.write(profile.print_profile(params=params))

    def add_dataset_from_file(self, filename, model=None, included=None, excluded=None):
        """Add profiles from a file to the dataset."""

        if model is None:
            model = "2st.pb_kex"

        print("{:<45s} ".format(str(filename)), end="")

        # Get the directory of the input file
        working_dir = filename.parent

        # Parse the experiment configuration file
        config = util.read_cfg_file(filename)

        try:
            # Read the experiment information
            details = dict(config.items("experiment"))
            experiment_type = details["type"]
            experiment_class = experiment_type.split(".")[0]

            # Read the experimental parameters
            details.update(
                {
                    key.lower(): val
                    for key, val in config.items("experimental_parameters")
                }
            )

            # Read the profile information (name, filename)
            filenames = {key.lower(): val for key, val in config.items("data")}

        except configparser.NoSectionError as error:
            sys.exit(f"    Reading aborted: {error}")

        except KeyError as error:
            sys.exit(
                "\nIn the section 'experiment' of {}, '{}' must be provided!".format(
                    filename, error
                )
            )

        try:
            # Read (optional) additional parameters
            details.update(
                {key.lower(): val for key, val in config.items("extra_parameters")}
            )

        except configparser.NoSectionError:
            pass

        path = pathlib.Path(details.get("path", "."))
        path = util.normalize_path(working_dir, path)

        try:
            reading = importlib.import_module(
                ".".join(["chemex.experiments", experiment_class, "reading"])
            )

        except ImportError:
            sys.exit(
                "The experiment '{}', referred in '{}' is not implemented.".format(
                    experiment_type, filename
                )
            )

        profiles = reading.read_profiles(
            path, filenames, details, model, included, excluded
        )

        self.dataset.extend(profiles)

        print("{:<25s} {:<25d}".format(experiment_type, len(profiles)))

        return profiles

    def make_bs_dataset(self):
        """Create a new dataset to run a bootstrap simulation."""

        data_bs = DataSet()

        for profile in self.dataset:
            data_bs.append(profile.make_bs_profile())

        return data_bs

    def make_mc_dataset(self, params):
        """Create a new dataset to run a Monte-Carlo simulation."""

        data_mc = DataSet()

        for profile in self.dataset:
            data_mc.append(profile.make_mc_profile(params=params))

        return data_mc


def read_data(args):
    """Read experimental setup and data."""
    util.header1("Reading Experimental Data")

    data = DataSet()

    model = res_incl = res_excl = None

    if "model" in args:
        model = args.model

    if "res_incl" in args:
        res_incl = args.res_incl

    if "res_excl" in args:
        res_excl = args.res_excl

    if args.experiments:
        print(("{:<45s} {:<25s} {:<25s}".format("File Name", "Experiment", "Profiles")))
        print(("{:<45s} {:<25s} {:<25s}".format("---------", "----------", "--------")))

        for filename in args.experiments:
            filename_ = pathlib.Path(filename)
            data.add_dataset_from_file(filename_, model, res_incl, res_excl)

    if not data.dataset:
        sys.exit("\nNo data to fit!\n")

    return data
