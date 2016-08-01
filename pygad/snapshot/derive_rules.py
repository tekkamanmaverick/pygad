'''
Definition of more complicated derived blocks. May be changed bu user.

A function for a derived block shall return the derived block with units as a
`UnitArr` and shall have an attribute `_deps` that is a set of the names of its
direct dependencies, i.e. the blocks it needs directly to calculate the derived
one from.
'''
__all__ = ['calc_temps', 'age_from_form', 'calc_x_ray_lum', 'calc_HI_mass']

from .. import environment
from ..units import UnitArr, UnitScalar, UnitError
import numpy as np
from .. import physics
from .. import gadget
from .. import data
from fractions import Fraction
from multiprocessing import Pool, cpu_count
import warnings
import gc

def calc_temps(u, XH=0.76, ne=0.0, XZ=None, f=3, subs=None):
    '''
    Calculate the block of temperatures form internal energy.

    This function calculates the temperatures from the internal energy using the
    ideal gas law,
        U = f/2 N k_b T
    and calculating an average particle mass from XH, ne, and XZ.

    Args:
        u (UnitQty):            The (mass-)specific internal energies.
        XH (float, array-like): The Hydrogen *mass* fraction(s). It can be either
                                a constant value or one for each particle
                                (H/mass).
        ne (float, array-like): The number of electrons per atom(!).
        XZ (iterable):          The metal mass fraction(s) and their atomic weight
                                in atomic units. Each element of this iterable
                                shall be a tuple of mass fraction (which can be an
                                array with fractions for each particle) at first
                                position and atomic weight (a single float) at
                                second postion.
                                The Helium mass fractions is always the remaining
                                mass:  1.0 - XH - sum(XZ[:,0]).
        f (float):              The (effective) degrees of freedom.
        subs (dict, Snap):      Substitutions used for conversion into Kelvin.
                                (c.f. `UnitArr.convert_to`)

    Returns:
        T (UnitArr):            The temperatures for the particles (in K if
                                possible).
    '''
    tmp = XH/1.008
    XHe = 1.0 - XH
    if XZ is not None:
        for X, m in XZ:
            tmp += X/float(m)
            XHe -= X
    tmp += XHe/4.003

    # assuming `ne` is the mean number of electrons per atom:
    #av_m = physics.m_u / (tmp * (1.0 + ne))
    # as in Gadget (where XZ=None, though): `ne` are the electrons per Hydrogen
    # atom:
    av_m = physics.m_u / (tmp + ne*XH)

    # solving:  U = f/2 N k_b T
    # which is:  u = f/2 N/M k_b T
    T = u / (f/2.) * av_m / physics.kB
    try:
        T.convert_to('K', subs=subs)
    except UnitError as ue:
        import sys
        print >> sys.stderr, 'WARNING: in "calc_temps":\n%s' % ue
    gc.collect()
    return T
calc_temps._deps = set()

def _z2Gyr_vec(arr, cosmo):
    '''Needed to pickle cosmo.lookback_time_in_Gyr for Pool().apply_async.'''
    return np.vectorize(cosmo.lookback_time_in_Gyr)(arr)
def age_from_form(form, subs, cosmic_time=None, cosmo=None, units='Gyr', parallel=None):
    '''
    Calculate ages from formation time.

    Args:
        form (UnitArr):     The formation times to convert. Has to be UnitArr with
                            appropiate units, i.e. '*_form' or a time unit.
        subs (dict, Snap):  Subsitution for unit convertions. See e.g.
                            `UnitArr.convert_to` for more information.
        cosmic_time (UnitScalar):
                            The current cosmic time. If None and subs is a
                            snapshot, it defaults to subs.time.
        cosmo (FLRWCosmo):  A cosmology to use for conversions. If None and subs
                            is a snapshot, the cosmology of that snapshot is used.
        units (str, Unit):  The units to return the ages in. If None, the return
                            value still has correct units, you just do not have
                            control over them.
        parallel (bool):    If units are converted from Gyr (or some other time
                            unit) to z_form / a_form, one can choose to use
                            multiple threads. By default, the function chooses
                            automatically whether to perform in parallel or not.

    Returns:
        ages (UnitArr):     The ages.

    Examples:
        >>> cosmo = physics.Planck2013()
        >>> age_from_form(UnitArr([0.001, 0.1, 0.5, 0.9], 'a_form'),
        ...               subs={'a':0.9, 'z':physics.a2z(0.9)},
        ...               cosmo=cosmo)
        UnitArr([ 12.30493079,  11.75687265,   6.44278561,   0.        ], units="Gyr")
        >>> age_from_form(UnitArr([10.0, 1.0, 0.5, 0.1], 'z_form'),
        ...               subs={'a':0.9, 'z':physics.a2z(0.9)},
        ...               cosmo=cosmo)
        UnitArr([ 11.82987008,   6.44278561,   3.70734788,  -0.13772577], units="Gyr")
        >>> age_from_form(UnitArr([-2.0, 0.0, 1.0], '(ckpc h_0**-1) / (km/s)'),
        ...               cosmic_time='2.1 Gyr',
        ...               subs={'a':0.9, 'z':physics.a2z(0.9), 'h_0':cosmo.h_0},
        ...               cosmo=cosmo,
        ...               units='Myr')
        UnitArr([ 4697.05769369,  2100.        ,   801.47115316], units="Myr")
    '''
    from ..snapshot.snapshot import _Snap
    if subs is None:
        subs = {}
    elif isinstance(subs, _Snap):
        snap, subs = subs, {}
        subs['a'] = snap.scale_factor
        subs['z'] = snap.redshift
        subs['h_0'] = snap.cosmology.h_0
        if cosmo is None:
            cosmo = snap.cosmology
        if cosmic_time is None:
            cosmic_time = UnitScalar(snap.time, gadget.get_block_units('AGE '),
                                     subs=subs)

    form = form.copy().view(UnitArr)

    if str(form.units).endswith('_form]'):
        # (a ->) z -> Gyr (-> time_units)
        if form.units == 'a_form':
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                form.setfield(np.vectorize(physics.a2z)(form), dtype=form.dtype)
        form.units = 'z_form'

        if environment.allow_parallel_conversion and (
                parallel or (parallel is None and len(form) > 1000)):
            N_threads = cpu_count()
            chunk = [[i*len(form)/N_threads, (i+1)*len(form)/N_threads]
                        for i in xrange(N_threads)]
            p = Pool(N_threads)
            res = [None] * N_threads
            with warnings.catch_warnings():
                # warnings.catch_warnings doesn't work in parallel
                # environment...
                warnings.simplefilter("ignore") # for _z2Gyr_vec
                for i in xrange(N_threads):
                    res[i] = p.apply_async(_z2Gyr_vec,
                                (form[chunk[i][0]:chunk[i][1]], cosmo))
            for i in xrange(N_threads):
                form[chunk[i][0]:chunk[i][1]] = res[i].get()
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore") # for _z2Gyr_vec
                form.setfield(_z2Gyr_vec(form,cosmo), dtype=form.dtype)
        form.units = 'Gyr'
        # from present day ages (lookback time) to actual current ages
        form -= cosmo.lookback_time(subs['z'])

    else:
        # 't_form' -> actual age
        cosmic_time = UnitScalar(cosmic_time, form.units, subs=subs)
        form = cosmic_time - form

    if units is not None:
        form.convert_to(units, subs=subs)

    return form
age_from_form._deps = set(['form_time'])

def calc_x_ray_lum(s, lumtable, **kwargs):
    '''
    Wrapping `x_ray_luminosity` for derived blocks.
    
    Args:
        s (Snap):           The snapshot to use.
        lumtable (str):     The filename of the XSPEC emission table to use.
        **kwargs:           Further arguments passed to `x_ray_luminosity`.

    Returns:
        lx (UnitArr):       X-ray luminosities of the gas particles.
    '''
    from ..analysis import x_ray_luminosity
    return x_ray_luminosity(s, lumtable=lumtable, **kwargs)
calc_x_ray_lum._deps = set(['Z', 'ne', 'H', 'rho', 'mass', 'temp'])

def calc_HI_mass(s, UVB=gadget.general['UVB']):
    '''
    Estimate the HI mass with the fitting formula from Rahmati et al. (2013).

    Args:
        s (Snap):       The (gas-particles sub-)snapshot to use.
        UVB (str):      The name of the UV background as named in `data.UVB`.
                        Defaults to the value of the UVB in the `gadget.cfg`.

    Returns:
        HI (UnitArr):   The HI mass block for the gas (within `s`).
    '''
    uvb     = data.UVB[UVB]
    z       = s.redshift
    fbaryon = s.cosmology.Omega_b / s.cosmology.Omega_m

    # interpolate Gamma_HI from the UV background radiation table for the current
    # redshift (TODO: which formula of the paper? formula 1 or 3?)
    # formula numbers are those of Rahmati et al. (2013)
    Gamma_HI = np.interp(np.log10(z+1.),
                         uvb['logz'], uvb['gH0'])
    # calculate the characteristic self-shielding density
    sigHI      = 3.27e-18 * (1.+z)**(-0.2)  # units in cm^2
    # formula (13), the T4^0.17 dependecy gets factored in later:
    nHss_gamma = 6.73e-3 * (sigHI/2.49e-18)**(-2./3.) * (fbaryon/0.17)**(-1./3.) \
            * (Gamma_HI*1e12)**(2./3.)

    # prepare the blocks needed
    T     = s.gas['temp'].in_units_of('K')
    rhoH  = s.gas['rho'] * s.gas['H']/s.gas['mass'] / physics.m_H
    rhoH.convert_to('cm**-3', subs=s)
    # calculatation is done unitless
    T     = T.view(np.ndarray)
    rhoH  = rhoH.view(np.ndarray)

    # formula (13):
    nHss = nHss_gamma * (T/1e4)**0.17   # in cm^-3
    # formula (14):
    fgamma_HI = 0.98 * (1.+(rhoH/nHss)**(1.64))**(-2.28) + 0.02*(1.+rhoH/nHss)**(-0.84)
    l         = 315614. / T
    alpha_A   = 1.269e-13 * l**1.503 / (1.+(l/0.522)**0.47)**1.923          # in cm^3/s
    # Collisional ionization Gamma_Col = Lambda_T*(1-eta)*n (Theuns et al., 1998)
    Lambda_T  = 1.17e-10*np.sqrt(T)*np.exp(-157809/T)/(1+np.sqrt(T/1e5))    # in cm^3/s
    
    # fitting (formula A8):
    A = alpha_A + Lambda_T
    B = 2.*alpha_A + Gamma_HI*fgamma_HI/rhoH + Lambda_T
    C = alpha_A
    det = B**2 - 4.*A*C
    fHI = (B - np.sqrt(det)) / (2.*A)
    fHI[ det<0 ] = 0.0

    return fHI * s.gas['H']
calc_HI_mass._deps = set(['temp'])

