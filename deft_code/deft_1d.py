#!/usr/local/bin/python -W ignore
import os.path
import re
import scipy as sp
import numpy as np
import sys
import time
from scipy.interpolate import interp1d

# Import deft-related code
from deft_code import deft_core
from deft_code import utils
from deft_code import laplacian
from deft_code import maxent

# Import error handling
from deft_code.utils import DeftError

class Results(): pass;

# Draws a probability distribution from the bilateral Laplacian prior
# You have to manually specify coefficients of nonconstant kernel components
# if alpha > 1
def sample_from_deft_1d_prior(template_data, ell, G=100, alpha=3, 
    bbox=[-np.Inf, np.Inf], periodic=False):

    # Create Laplacian
    if periodic:
        Delta = laplacian.Laplacian('1d_periodic', alpha, G, 1.0)
    else:
        Delta = laplacian.Laplacian('1d_bilateral', alpha, G, 1.0)

    # Get histogram counts and grid centers
    counts, bin_centers = utils.histogram_counts_1d(template_data, G, 
        bbox=bbox)
    R = 1.*counts/np.sum(counts)

    # Get other information agout grid
    bbox, h, bin_edges = utils.grid_info_from_bin_centers_1d(bin_centers)

    # Draw coefficients for other components of phi
    kernel_dim = Delta._kernel_dim
    kernel_basis = Delta._eigenbasis[:,:kernel_dim]
    rowspace_basis = Delta._eigenbasis[:,kernel_dim:]
    rowspace_eigenvalues = ell**(2*alpha) * h**(-2*alpha) * \
        np.array(Delta._eigenvalues[kernel_dim:]) 

    # Keep drawing coefficients until phi_rowspace is not minimized
    # at either extreme
    while True:

        # Draw coefficients for rowspace coefficients
        while True:
            rowspace_coeffs = \
                np.random.randn(G-kernel_dim)/np.sqrt(2.*rowspace_eigenvalues)

            # Construct rowspace phi
            rowspace_coeffs_col = np.mat(rowspace_coeffs).T
            rowspace_basis_mat = np.mat(rowspace_basis)
            phi_rowspace = rowspace_basis_mat*rowspace_coeffs_col

            #if not min(phi_rowspace) in phi_rowspace[[0,-1]]:
            break

        if kernel_dim == 1:
            phi_kernel = sp.zeros(phi_rowspace.shape)
            break

        # Construct full phi so that distribution mateches moments of R
        phi_kernel, success = maxent.compute_maxent_field(R, kernel_basis, 
            phi0=phi_rowspace, geo_dist_tollerance=1.0E-10)

        if success:
            break
        else:
            print('Maxent failure! Trying to sample again.')

    phi_rowspace = np.array(phi_rowspace).ravel()
    phi_kernel = np.array(phi_kernel).ravel()
    phi = phi_kernel + phi_rowspace

    # Return Q
    Q = utils.field_to_prob(phi)/h
    R = R/h
    return bin_centers, Q, R

# Gets a handle to the data file, be it a system file or stdin
def get_data_file_handle(data_file_name):
    # Get data input file
    if data_file_name == 'stdin':
        data_file_handle = sys.stdin
        assert data_file_handle, 'Failed to open standard input.'

    else:
        # Verify that input file exists and that we have permission to read it
        assert os.path.isfile(data_file_name)

        # Open data file
        data_file_handle = open(data_file_name,'r')
        assert data_file_handle, 'Failed to open "%s"'%data_file_name

    # Return a handle to the data file
    return data_file_handle


# Loads data. Does requisite error checking
#### WARNING! Still need to modify to prevent reading too much information
def load_data(data_file_handle, MAX_NUM_DATA=1E6):

    # Read in data file. Discard all commented lines commented with '#' or '/'
    data_lines = [l.strip() for l in data_file_handle.readlines() if len(l) > 0 and not l[0] in ['#','/']]

    # Remove all non-numeric entities from lines, and form into one long string
    pattern = '[^0-9\-\+\.]|\-[^0-9\.]|\+[^0-9\.]|[^0-9]\.[^0-9]' # Removes all non-valid numbers
    data_string = ' '.join([re.sub(pattern, ' ', l) for l in data_lines])

    # Parse numbers from data_string
    data = sp.array([float(d) for d in data_string.split()])
    
    # Return data to user. 
    return data


#
# The main DEFT algorithm in 1D.
#

def run(obj):

    # Extract information from Deft1D object
    data = obj.data
    G = obj.num_grid_points
    alpha = obj.alpha
    bbox = obj.bounding_box
    periodic = obj.periodic
    Z_eval = obj.Z_evaluation_method
    num_Z_samples = obj.num_samples_for_Z
    DT_MAX = obj.max_t_step
    print_t = obj.print_t
    tollerance = obj.tolerance
    resolution = obj.resolution
    deft_seed = obj.seed
    num_pt_samples = obj.num_posterior_samples
    fix_t_at_t_star = obj.sample_only_at_l_star
    max_log_evidence_ratio_drop = obj.max_log_evidence_ratio_drop

    # Start clock
    start_time = time.clock()

    # If deft_seed is specified, set it
    if not (deft_seed is None):
        np.random.seed(deft_seed)
    else:
        np.random.seed(None)
        
    # Create Laplacian
    laplacian_start_time = time.clock()
    if periodic:
        op_type = '1d_periodic'
    else:
        op_type = '1d_bilateral'
    Delta = laplacian.Laplacian(op_type, alpha, G)
    laplacian_compute_time = time.clock() - laplacian_start_time
    if print_t:
        print('Laplacian computed de novo in %f sec.'%laplacian_compute_time)

    # Get histogram counts and grid centers
    counts, bin_centers = utils.histogram_counts_1d(data, G, bbox)
    N = sum(counts)

    # Get other information about grid
    bbox, h, bin_edges = utils.grid_info_from_bin_centers_1d(bin_centers)

    # Compute initial t
    t_start = min(0.0, sp.log(N)-2.0*alpha*sp.log(alpha/h))
    if t_start < -10.0:
        t_start /= 2
    #print('t_start = %.2f' % t_start)
    if print_t:
        print('t_start = %0.2f' % t_start)
    
    # Do DEFT density estimation
    core_results = deft_core.run(counts, Delta, Z_eval, num_Z_samples, t_start, DT_MAX, print_t,
                                 tollerance, resolution, num_pt_samples, fix_t_at_t_star,max_log_evidence_ratio_drop)

    # Fill in results
    copy_start_time = time.clock()
    results = core_results # Get all results from deft_core

    # Normalize densities properly
    results.h = h 
    results.L = G*h
    results.R /= h
    results.Q_star /= h
    results.l_star = h*(sp.exp(-results.t_star)*N)**(1/(2.*alpha))
    for p in results.map_curve.points:
        p.Q /= h
    if not (num_pt_samples == 0):
        results.Q_samples /= h

    # Get 1D-specific information
    results.bin_centers = bin_centers
    results.bin_edges = bin_edges
    results.periodic = periodic
    results.alpha = alpha
    results.bbox = bbox
    results.Delta = Delta
    copy_compute_time = time.clock() - copy_start_time

    # Create interpolated phi_star and Q_star. Need to extend grid to boundaries first
    extended_xgrid = sp.zeros(G+2)
    extended_xgrid[1:-1] = bin_centers
    extended_xgrid[0] = bbox[0] - h/2
    extended_xgrid[-1] = bbox[1] + h/2
    
    extended_phi_star = sp.zeros(G+2)
    extended_phi_star[1:-1] = results.phi_star
    extended_phi_star[0] = results.phi_star[0]
    extended_phi_star[-1] = results.phi_star[-1]

    phi_star_func = interp1d(extended_xgrid, extended_phi_star, kind='cubic')
    Z = sp.sum(h*sp.exp(-results.phi_star))
    #Q_star_func = lambda(x): sp.exp(-phi_star_func(x))/Z
    Q_star_func = lambda x: sp.exp(-phi_star_func(x)) / Z
    results.Q_star_func = Q_star_func

    # XXX REMOVE
    # Compute differential entropy in bits
    entropy_start_time = time.clock()
    if not (num_pt_samples == 0):
        entropies = np.zeros(num_pt_samples)
        for i in range(results.Q_samples.shape[1]):
            Q = results.Q_samples[:,i].ravel()
            entropy = -sp.sum(h*Q*sp.log2(Q + utils.TINY_FLOAT64))
            #for j in range(G):
            #    entropy += -results.h*Q[j]*sp.log2(Q[j] + utils.TINY_FLOAT64)
            entropies[i] = entropy

        # Compute mean and variance of the differential entropy
        results.entropies = entropies
        results.e_mean = np.mean(entropies)
        results.e_std = np.std(entropies)
        results.entropy_compute_time = time.clock() - entropy_start_time
    # XXX

    # Record execution time
    results.copy_compute_time = copy_compute_time
    results.laplacian_compute_time = laplacian_compute_time
    results.deft_1d_compute_time = time.clock()-start_time

    return results
