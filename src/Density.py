import numpy as np
from scipy import interpolate
from src.utils import check


class Density:
    """
    A probability density that can be evaluated anywhere

    Parameters
    ----------

    grid: (1D np.array)

        The grid points at which the field values are defined. Must be the same
        the same shape as field.

    field_values: (1D np.array)

        The values of the field used to computed this density.

    values: (1D np.array)

        The values of the density itself at the grid points

    min_value: (float >= 0)

        The minimum allowable value of the probability density.

    interpolation_method (str):
        The method used to interpolate between gridpoints.

    Attributes
    ----------

    field_values:
        See above.

    grid:
        See above.

    grid_spacing: (float)
        The spacing between neighboring gridpoints.

    values: (1D np.array)
        The values of the probability density at all grid points.

    bounding_box:
        The domain in which the density is nonzero.

    """

    def __init__(self, grid, values=None, field_values=None,
                 interpolation_method='cubic', min_value=1E-20):

        # Set grid
        self.grid = grid

        # Make sure field_values or values are specified
        check((values is not None) or (field_values is not None),
              'Either values or field_values must be specified.')

        # Make sure min_value is valid
        min_value = float(min_value)
        check(min_value >= 0, 'min_value must be >= 0')

        # If field_values are specified, work with these
        if field_values is not None:
            check(len(field_values) == len(self.grid),
                  'field_values must be the same length as grid.')
            self.field_values = field_values
            self.values = np.exp(-self.field_values)

        # Otherwise work with values
        else:
            check(len(values) == len(self.grid),
                  'values must be the same length as grid.')
            self.values = values
            self.values[values <= min_value] = min_value
            self.field_values = -np.log(values)

        # Compute grid spacing
        self.grid_spacing = (grid[-1]-grid[0])/(len(grid)-1)

        # Compute bounding box
        self.bounding_box = [self.grid[0] - self.grid_spacing/2,
                             self.grid[-1] + self.grid_spacing/2]

        # Compute normalization constant and normalize values
        self.Z = np.sum(self.grid_spacing * self.values)
        self.values /= self.Z

        # Interpolate using extended grid and extended phi
        self.field = interpolate.interp1d(self.grid,
                                          self.field_values,
                                          kind=interpolation_method,
                                          bounds_error=False,
                                          fill_value='extrapolate',
                                          assume_sorted=True)

    def __call__(self, *args, **kwargs):
        """
        Same as evaluate()
        """

        return self.evaluate(*args, **kwargs)

    def evaluate(self, xs):
        """
        Evaluates the probability density at specified positions.

        Note: self(xs) can be used instead of self.evaluate(xs).

        Parameters
        ----------

        xs: (np.array)
            Locations at which to evaluate the density.

        Returns
        -------

        (np.array)
            Values of the density at the specified positions. Values at
            positions outside the bounding box are evaluated to zero.

        """

        values = np.exp(-self.field(xs)) / self.Z
        zero_indices = (xs < self.bounding_box[0]) | \
                       (xs > self.bounding_box[1])
        values[zero_indices] = 0.0
        return values

    def sample(self, num_samples, num_gridpoints=None, seed=None):
        """
        Samples the probability density

        Parameters
        ----------

        num_samples: (int > 0)
            Number of data points to sample.

        num_gridpoints: (int >= 2)
            Number of grid points on which to sample. Defaults to number of
            grid points used to create the density.

        Returns
        -------

        sample, (np.array)
            Sampled x values.

        """

        num_samples = int(num_samples)
        check(num_samples > 0, 'num_samples = %d must be > 0.' % num_samples)

        if num_gridpoints is None:

            # Choose grid used to create density
            xs = self.grid

        else:

            # Validate num_gridpoints
            num_gridpoints = int(num_gridpoints)
            check(num_gridpoints >= 2,
                  'num_gridpoints == %d must be >= 2' % num_gridpoints)

            # Set grid
            xmin = self.bounding_box[0] - self.grid_spacing/2
            xmax = self.bounding_box[1] + self.grid_spacing/2
            xs = np.linspace(xmin, xmax, num_gridpoints)

        # Compute normalized distribution
        Qs = self.evaluate(xs)
        Qs /= sum(Qs)

        # Set seed if provided
        if seed is not None:
            np.random.seed(seed)

        # Draw samples with replacement
        sample = np.random.choice(xs, size=num_samples, p=Qs, replace=True)

        # Return samples to user
        return sample
