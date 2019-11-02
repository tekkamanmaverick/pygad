__all__ = ['Gamma_HI', 'Rahmati_fGamma_HI', 'Rahmati_HI_mass', 'UVB_data']

import numpy as np
from .. import gadget
from .. import physics
from ..units import UnitQty


def Gamma_HI(z, UVB=gadget.general['UVB']):
    '''
    Look up the Gamma for HI in the UVB_data tables for a given redshift with
    interpolation.
    '''
    uvb = UVB_data[UVB]
    return np.interp(np.log10(z + 1.), uvb['logz'], uvb['gH0'])


def sigHI(z, UVB=gadget.general['UVB']):
    '''
    Calculate the characteristic self-shielding density (in units in cm^2).

    Done by an eyeball fitting formulat for the values of Rahmati+ (2013), Table
    2.

    Args:
        z (float):  The redshift to calculate fGamma_HI at.
        UVB (str):  The name of the UV background as named in `cloudy.UVB`.
                    Defaults to the value of the UVB in the `gadget.cfg`.

    Returns:
        sigHI (float):  The characteristic self-shielding density
                        (in units in cm^2).
    '''
    # calculate the characteristic self-shielding density (in units in cm^2)
    if UVB == 'FG11':
        # TODO: this is a bit off...
        sigHI = 3.27e-18 * (1. + z) ** (-0.2)
    elif UVB == 'HM01':
        # good fit for z<~5
        sigHI = 2.31e-18 + 0.96e-18 * (1. + z) ** (-1.18)
    elif UVB == 'HM12':
        # from Romeel formula for gizmo simulation code
        # (seems to match Rahmati 2013 table 2 values pretty well)
        sigHI = 2.67e-18 * (1.+z)**(-0.018)
    else:
        raise ValueError('HI cross section not known for UVB "%s"!' % UVB)
    return sigHI


def Rahmati_fGamma_HI(z, nH, T, fbaryon, UVB=gadget.general['UVB'],
                      flux_factor=None, subs=None):
    '''
    The fraction of the photoionising background that is not self-shielded as with
    the fitting formula of Rahmati et al. (2013) (formula (14)).

    Args:
        z (float):          The redshift to calculate fGamma_HI at.
        nH (UnitQty):       The Hydrogen number densities. Default units are cm**-3.
        T (UnitQty):        The temperatures. Default units are K.
        fbaryon (float):    The cosmic baryon fraction.
        UVB (str):          The name of the UV background as named in
                            `cloudy.UVB`. Defaults to the value of the UVB in the
                            `gadget.cfg`.
        flux_factor (float):Adjust the UVB by this factor (assume a optically thin
                            limit and scale down the densities during the look-up
                            by this factor).
                            Note `sigHI` is not adjusted!
        subs (dict, Snap):  Used for substitutions in unit conversions (c.f.
                            `UnitArr.convert_to`).

    Returns:
        fGamma_HI (UnitArr):   The HI mass block for the gas (within `s`).
    '''
    # formula numbers are those of Rahmati et al. (2013)

    if flux_factor is None:
        from ..snapshot import derived
        flux_factor = derived.iontable['flux_factor']

    # interpolate Gamma_HI from the UV background radiation table for the current
    # redshift (formula 3)
    _Gamma_HI = float(flux_factor) * Gamma_HI(z, UVB)
    # calculate the characteristic self-shielding density (in units in cm^2)
    _sigHI = sigHI(z, UVB)  # TODO: might change with the flux factor as well!
    # formula (13), the T4^0.17 dependecy gets factored in later:
    nHss_gamma = 6.73e-3 * (_sigHI / 2.49e-18) ** (-2. / 3.) * (fbaryon / 0.17) ** (-1. / 3.) \
                 * (_Gamma_HI * 1e12) ** (2. / 3.)

    # prepare the blocks needed
    T = UnitQty(T, 'K', subs=subs)
    nH = UnitQty(nH, 'cm**-3', subs=subs)
    # calculatation is done unitless
    T = T.view(np.ndarray)
    nH = nH.view(np.ndarray)

    # formula (13):
    nHss = nHss_gamma * (T / 1e4) ** 0.17  # in cm^-3
    nH_nHss = nH / nHss
    # formula (14):
    fGamma_HI = 0.98 * (1. + (nH_nHss) ** (1.64)) ** (-2.28) + 0.02 * (1. + nH_nHss) ** (-0.84)

    return fGamma_HI


def Rahmati_HI_mass(s, UVB=gadget.general['UVB'], flux_factor=None):
    '''
    Estimate the HI mass with the fitting formula from Rahmati et al. (2013).

    Args:
        s (Snap):               The (gas-particles sub-)snapshot to use.
        UVB (str):              The name of the UV background as named in
                                `cloudy.UVB`. Defaults to the value of the UVB in
                                the `gadget.cfg`.
        flux_factor (float):    Adjust the UVB by this factor (assume a optically
                                thin limit and scale down the densities during the
                                look-up by this factor).
                                (Note: `sigHI` is not adjusted!)

    Returns:
        HI (UnitArr):   The HI mass block for the gas (within `s`).
    '''
    if flux_factor is None:
        from ..snapshot import derived
        flux_factor = derived.iontable['flux_factor']

    T = s.gas['temp'].in_units_of('K')
    nH = s.gas['nH'].in_units_of('cm**-3', subs=s)

    fgamma_HI = Rahmati_fGamma_HI(s.redshift, nH=nH, T=T,
                                  fbaryon=s.cosmology.Omega_b / s.cosmology.Omega_m,
                                  UVB=UVB, flux_factor=flux_factor, subs=s)

    # calculatation is done unitless
    T = T.view(np.ndarray)
    nH = nH.view(np.ndarray)

    _Gamma_HI = float(flux_factor) * Gamma_HI(s.redshift, UVB)
    l = 315614. / T
    alpha_A = 1.269e-13 * l ** 1.503 / (1. + (l / 0.522) ** 0.47) ** 1.923  # in cm^3/s
    # Collisional ionization Gamma_Col = Lambda_T*(1-eta)*n (Theuns et al., 1998)
    Lambda_T = 1.17e-10 * np.sqrt(T) * np.exp(-157809 / T) / (1 + np.sqrt(T / 1e5))  # in cm^3/s

    # fitting (formula A8):
    A = alpha_A + Lambda_T
    B = 2. * alpha_A + _Gamma_HI * fgamma_HI / nH + Lambda_T
    C = alpha_A
    det = B ** 2 - 4. * A * C
    fHI = (B - np.sqrt(det)) / (2. * A)
    fHI[det < 0] = 0.0

    return fHI * s.gas['H']


UVB_data = {
    'FG11':{
        'logz':np.array([0.   ,  0.005,  0.01 ,  0.015,  0.02 ,  0.025,  0.03 ,  0.035,
                         0.04 ,  0.045,  0.05 ,  0.055,  0.06 ,  0.065,  0.07 ,  0.075,
                         0.08 ,  0.085,  0.09 ,  0.095,  0.1  ,  0.105,  0.11 ,  0.115,
                         0.12 ,  0.125,  0.13 ,  0.135,  0.14 ,  0.145,  0.15 ,  0.155,
                         0.16 ,  0.165,  0.17 ,  0.175,  0.18 ,  0.185,  0.19 ,  0.195,
                         0.2  ,  0.205,  0.21 ,  0.215,  0.22 ,  0.225,  0.23 ,  0.235,
                         0.24 ,  0.245,  0.25 ,  0.255,  0.26 ,  0.265,  0.27 ,  0.275,
                         0.28 ,  0.285,  0.29 ,  0.295,  0.3  ,  0.305,  0.31 ,  0.315,
                         0.32 ,  0.325,  0.33 ,  0.335,  0.34 ,  0.345,  0.35 ,  0.355,
                         0.36 ,  0.365,  0.37 ,  0.375,  0.38 ,  0.385,  0.39 ,  0.395,
                         0.4  ,  0.405,  0.41 ,  0.415,  0.42 ,  0.425,  0.43 ,  0.435,
                         0.44 ,  0.445,  0.45 ,  0.455,  0.46 ,  0.465,  0.47 ,  0.475,
                         0.48 ,  0.485,  0.49 ,  0.495,  0.5  ,  0.505,  0.51 ,  0.515,
                         0.52 ,  0.525,  0.53 ,  0.535,  0.54 ,  0.545,  0.55 ,  0.555,
                         0.56 ,  0.565,  0.57 ,  0.575,  0.58 ,  0.585,  0.59 ,  0.595,
                         0.6  ,  0.605,  0.61 ,  0.615,  0.62 ,  0.625,  0.63 ,  0.635,
                         0.64 ,  0.645,  0.65 ,  0.655,  0.66 ,  0.665,  0.67 ,  0.675,
                         0.68 ,  0.685,  0.69 ,  0.695,  0.7  ,  0.705,  0.71 ,  0.715,
                         0.72 ,  0.725,  0.73 ,  0.735,  0.74 ,  0.745,  0.75 ,  0.755,
                         0.76 ,  0.765,  0.77 ,  0.775,  0.78 ,  0.785,  0.79 ,  0.795,
                         0.8  ,  0.805,  0.81 ,  0.815,  0.82 ,  0.825,  0.83 ,  0.835,
                         0.84 ,  0.845,  0.85 ,  0.855,  0.86 ,  0.865,  0.87 ,  0.875,
                         0.88 ,  0.885,  0.89 ,  0.895,  0.9  ,  0.905,  0.91 ,  0.915,
                         0.92 ,  0.925,  0.93 ,  0.935,  0.94 ,  0.945,  0.95 ,  0.955,
                         0.96 ,  0.965,  0.97 ,  0.975,  0.98 ,  0.985,  0.99 ,  0.995,
                         1.   ,  1.005,  1.01 ,  1.015,  1.02 ,  1.025,  1.03 ,  1.035,
                         1.04 ,  1.045,  1.05 ,  1.055,  1.06 ,  1.065,  1.07]),
        'gH0':np.array([3.76244000e-14,   3.83213000e-14,   3.90303000e-14,
                        4.01290000e-14,   4.16007000e-14,   4.31222000e-14,
                        4.47007000e-14,   4.63453000e-14,   4.80462000e-14,
                        4.98113000e-14,   5.16490000e-14,   5.35503000e-14,
                        5.55239000e-14,   5.75769000e-14,   5.97016000e-14,
                        6.19076000e-14,   6.42009000e-14,   6.65751000e-14,
                        6.90410000e-14,   7.16025000e-14,   7.42548000e-14,
                        7.70100000e-14,   7.98695000e-14,   8.28307000e-14,
                        8.59068000e-14,   8.90972000e-14,   9.24012000e-14,
                        9.58331000e-14,   9.94039000e-14,   1.03087000e-13,
                        1.06911000e-13,   1.10885000e-13,   1.14984000e-13,
                        1.19226000e-13,   1.23641000e-13,   1.28194000e-13,
                        1.32903000e-13,   1.37801000e-13,   1.42848000e-13,
                        1.48065000e-13,   1.53480000e-13,   1.59057000e-13,
                        1.64817000e-13,   1.70784000e-13,   1.76923000e-13,
                        1.83257000e-13,   1.89805000e-13,   1.96533000e-13,
                        2.03467000e-13,   2.10616000e-13,   2.17951000e-13,
                        2.25498000e-13,   2.33258000e-13,   2.41203000e-13,
                        2.49362000e-13,   2.57724000e-13,   2.66267000e-13,
                        2.75018000e-13,   2.83999000e-13,   2.93102000e-13,
                        3.02401000e-13,   3.11903000e-13,   3.21502000e-13,
                        3.31240000e-13,   3.41165000e-13,   3.51160000e-13,
                        3.61251000e-13,   3.71488000e-13,   3.81738000e-13,
                        3.92027000e-13,   4.02401000e-13,   4.12718000e-13,
                        4.22998000e-13,   4.33286000e-13,   4.43424000e-13,
                        4.53438000e-13,   4.63352000e-13,   4.73011000e-13,
                        4.82441000e-13,   4.91671000e-13,   5.00591000e-13,
                        5.09267000e-13,   5.17733000e-13,   5.25902000e-13,
                        5.33842000e-13,   5.41633000e-13,   5.48998000e-13,
                        5.56077000e-13,   5.62935000e-13,   5.69306000e-13,
                        5.75296000e-13,   5.80996000e-13,   5.86202000e-13,
                        5.90973000e-13,   5.95411000e-13,   5.99308000e-13,
                        6.02729000e-13,   6.05783000e-13,   6.08265000e-13,
                        6.10246000e-13,   6.11843000e-13,   6.12855000e-13,
                        6.13357000e-13,   6.13477000e-13,   6.13017000e-13,
                        6.12060000e-13,   6.10742000e-13,   6.08870000e-13,
                        6.06530000e-13,   6.03867000e-13,   6.00695000e-13,
                        5.97115000e-13,   5.93252000e-13,   5.88951000e-13,
                        5.84315000e-13,   5.79553000e-13,   5.74327000e-13,
                        5.68850000e-13,   5.63301000e-13,   5.57385000e-13,
                        5.51270000e-13,   5.45110000e-13,   5.38750000e-13,
                        5.32273000e-13,   5.25828000e-13,   5.19261000e-13,
                        5.12652000e-13,   5.06142000e-13,   4.99581000e-13,
                        4.93041000e-13,   4.86655000e-13,   4.80274000e-13,
                        4.73961000e-13,   4.67838000e-13,   4.61761000e-13,
                        4.55782000e-13,   4.50010000e-13,   4.44306000e-13,
                        4.38712000e-13,   4.33323000e-13,   4.28006000e-13,
                        4.22791000e-13,   4.17762000e-13,   4.12791000e-13,
                        4.07901000e-13,   4.03235000e-13,   3.98514000e-13,
                        3.93836000e-13,   3.89305000e-13,   3.84682000e-13,
                        3.80033000e-13,   3.75380000e-13,   3.70629000e-13,
                        3.65741000e-13,   3.60711000e-13,   3.55487000e-13,
                        3.50126000e-13,   3.44716000e-13,   3.39250000e-13,
                        3.33815000e-13,   3.28484000e-13,   3.23176000e-13,
                        3.17893000e-13,   3.12648000e-13,   3.07359000e-13,
                        3.02040000e-13,   2.96708000e-13,   2.91291000e-13,
                        2.85810000e-13,   2.80289000e-13,   2.74664000e-13,
                        2.68965000e-13,   2.63257000e-13,   2.57409000e-13,
                        2.51476000e-13,   2.45535000e-13,   2.39468000e-13,
                        2.33338000e-13,   2.27174000e-13,   2.20960000e-13,
                        2.14712000e-13,   2.08469000e-13,   2.02191000e-13,
                        1.95911000e-13,   1.89667000e-13,   1.83417000e-13,
                        1.77197000e-13,   1.71041000e-13,   1.64910000e-13,
                        1.58837000e-13,   1.52855000e-13,   1.46927000e-13,
                        1.41081000e-13,   1.35349000e-13,   1.29695000e-13,
                        1.24146000e-13,   1.18727000e-13,   1.13406000e-13,
                        1.07857000e-13,   1.00976000e-13,   9.28557000e-14,
                        8.37879000e-14,   7.40917000e-14,   6.40348000e-14,
                        5.39463000e-14,   4.41478000e-14,   3.48885000e-14,
                        2.64282000e-14,   1.89767000e-14,   1.26822000e-14,
                        7.64449000e-15,   3.90686000e-15,   1.45165000e-15,
                        2.10205000e-16,   0.00000000e+00])
    },
    'HM12':{
        'logz':np.array([0     , 0.005 , 0.01  , 0.015 , 0.02  , 0.025 , 0.03  , 0.035 ,
                         0.04  , 0.045 , 0.05  , 0.055 , 0.06  , 0.065 , 0.07  , 0.075 ,
                         0.08  , 0.085 , 0.09  , 0.095 , 0.1   , 0.105 , 0.11  , 0.115 ,
                         0.12  , 0.125 , 0.13  , 0.135 , 0.14  , 0.145 , 0.15  , 0.155 ,
                         0.16  , 0.165 , 0.17  , 0.175 , 0.18  , 0.185 , 0.19  , 0.195 ,
                         0.2   , 0.205 , 0.21  , 0.215 , 0.22  , 0.225 , 0.23  , 0.235 ,
                         0.24  , 0.245 , 0.25  , 0.255 , 0.26  , 0.265 , 0.27  , 0.275 , 
                         0.28  , 0.285 , 0.29  , 0.295 , 0.3   , 0.305 , 0.31  , 0.315 ,
                         0.32  , 0.325 , 0.33  , 0.335 , 0.34  , 0.345 , 0.35  , 0.355 ,
                         0.36  , 0.365 , 0.37  , 0.375 , 0.38  , 0.385 , 0.39  , 0.395 ,
                         0.4   , 0.405 , 0.41  , 0.415 , 0.42  , 0.425 , 0.43  , 0.435 ,
                         0.44  , 0.445 , 0.45  , 0.455 , 0.46  , 0.465 , 0.47  , 0.475 ,
                         0.48  , 0.485 , 0.49  , 0.495 , 0.5   , 0.505 , 0.51  , 0.515 ,
                         0.52  , 0.525 , 0.53  , 0.535 , 0.54  , 0.545 , 0.55  , 0.555 ,
                         0.56  , 0.565 , 0.57  , 0.575 , 0.58  , 0.585 , 0.59  , 0.595 ,
                         0.6   , 0.605 , 0.61  , 0.615 , 0.62  , 0.625 , 0.63  , 0.635 ,
                         0.64  , 0.645 , 0.65  , 0.655 , 0.66  , 0.665 , 0.67  , 0.675 ,
                         0.68  , 0.685 , 0.69  , 0.695 , 0.7   , 0.705 , 0.71  , 0.715 ,
                         0.72  , 0.725 , 0.73  , 0.735 , 0.74  , 0.745 , 0.75  ,0.755 ,
                         0.76  , 0.765 , 0.77  , 0.775 , 0.78  , 0.785 , 0.79  , 0.795 ,
                         0.8   , 0.805 , 0.81  , 0.815 , 0.82  , 0.825 , 0.83  , 0.835 ,
                         0.84  , 0.845 , 0.85  , 0.855 , 0.86  , 0.865 , 0.87  , 0.875 ,
                         0.88  , 0.885 , 0.89  , 0.895 , 0.9   , 0.905 , 0.91  , 0.915 ,
                         0.92  , 0.925 , 0.93  , 0.935 , 0.94  , 0.945 , 0.95  , 0.955 ,
                         0.96  , 0.965 , 0.97  , 0.975 , 0.98  , 0.985 , 0.99  , 0.995 ,
                         1     , 1.005 , 1.01  , 1.015 , 1.02  , 1.025 , 1.03  , 1.035 ,
                         1.04  , 1.045 , 1.05  , 1.055 , 1.06  , 1.065 , 1.07  , 1.075 ,
                         1.08  , 1.085 , 1.09  , 1.095 , 1.1   , 1.105 , 1.11  , 1.115 ,
                         1.12  , 1.125 , 1.13  , 1.135 , 1.14  , 1.145 , 1.15  , 1.155 ,
                         1.16  , 1.165 , 1.17  , 1.175 , 1.18  , 1.185 , 1.19  , 1.195 , 
                         1.2   , 1.205]),
        'gH0':np.array([2.25e-14, 2.38e-14, 2.51e-14, 
                        2.64e-14, 2.79e-14, 2.94e-14, 
                        3.10e-14, 3.26e-14, 3.44e-14, 
                        3.63e-14, 3.82e-14, 4.03e-14, 
                        4.24e-14, 4.47e-14, 4.70e-14, 
                        4.95e-14, 5.22e-14, 5.49e-14, 
                        5.78e-14, 6.08e-14, 6.40e-14, 
                        6.73e-14, 7.08e-14, 7.44e-14, 
                        7.82e-14, 8.22e-14, 8.64e-14, 
                        9.08e-14, 9.54e-14, 1.00e-13, 
                        1.05e-13, 1.10e-13, 1.16e-13, 
                        1.22e-13, 1.28e-13, 1.34e-13, 
                        1.40e-13, 1.47e-13, 1.54e-13, 
                        1.61e-13, 1.69e-13, 1.77e-13, 
                        1.85e-13, 1.94e-13, 2.03e-13, 
                        2.12e-13, 2.22e-13, 2.32e-13, 
                        2.42e-13, 2.53e-13, 2.64e-13, 
                        2.76e-13, 2.88e-13, 3.00e-13, 
                        3.13e-13, 3.26e-13, 3.39e-13, 
                        3.53e-13, 3.67e-13, 3.82e-13, 
                        3.97e-13, 4.12e-13, 4.28e-13, 
                        4.44e-13, 4.60e-13, 4.77e-13, 
                        4.93e-13, 5.11e-13, 5.28e-13, 
                        5.46e-13, 5.64e-13, 5.82e-13, 
                        6.00e-13, 6.18e-13, 6.35e-13, 
                        6.53e-13, 6.71e-13, 6.88e-13, 
                        7.05e-13, 7.22e-13, 7.38e-13, 
                        7.54e-13, 7.70e-13, 7.86e-13, 
                        8.01e-13, 8.15e-13, 8.30e-13, 
                        8.43e-13, 8.56e-13, 8.69e-13, 
                        8.81e-13, 8.92e-13, 9.02e-13, 
                        9.11e-13, 9.20e-13, 9.28e-13, 
                        9.35e-13, 9.40e-13, 9.45e-13, 
                        9.49e-13, 9.53e-13, 9.55e-13, 
                        9.55e-13, 9.55e-13, 9.54e-13, 
                        9.52e-13, 9.49e-13, 9.45e-13, 
                        9.41e-13, 9.35e-13, 9.28e-13, 
                        9.21e-13, 9.12e-13, 9.03e-13, 
                        8.94e-13, 8.83e-13, 8.72e-13, 
                        8.61e-13, 8.49e-13, 8.36e-13, 
                        8.24e-13, 8.10e-13, 7.97e-13, 
                        7.83e-13, 7.69e-13, 7.55e-13, 
                        7.41e-13, 7.27e-13, 7.13e-13, 
                        6.99e-13, 6.85e-13, 6.71e-13, 
                        6.57e-13, 6.44e-13, 6.31e-13, 
                        6.18e-13, 6.05e-13, 5.93e-13, 
                        5.81e-13, 5.69e-13, 5.57e-13, 
                        5.46e-13, 5.36e-13, 5.25e-13, 
                        5.15e-13, 5.06e-13, 4.96e-13, 
                        4.88e-13, 4.79e-13, 4.72e-13, 
                        4.64e-13, 4.57e-13, 4.50e-13, 
                        4.43e-13, 4.37e-13, 4.31e-13, 
                        4.25e-13, 4.18e-13, 4.10e-13, 
                        4.01e-13, 3.90e-13, 3.77e-13, 
                        3.63e-13, 3.48e-13, 3.32e-13, 
                        3.16e-13, 2.99e-13, 2.83e-13, 
                        2.68e-13, 2.53e-13, 2.38e-13, 
                        2.24e-13, 2.10e-13, 1.97e-13, 
                        1.84e-13, 1.72e-13, 1.60e-13, 
                        1.49e-13, 1.38e-13, 1.28e-13, 
                        1.19e-13, 1.10e-13, 1.01e-13, 
                        9.35e-14, 8.62e-14, 7.93e-14, 
                        7.29e-14, 6.70e-14, 6.15e-14, 
                        5.63e-14, 5.16e-14, 4.73e-14, 
                        4.32e-14, 3.95e-14, 3.61e-14, 
                        3.30e-14, 3.01e-14, 2.74e-14, 
                        2.50e-14, 2.28e-14, 2.07e-14, 
                        1.89e-14, 1.72e-14, 1.56e-14, 
                        1.42e-14, 1.29e-14, 1.17e-14, 
                        1.06e-14, 9.65e-15, 8.76e-15, 
                        7.94e-15, 7.20e-15, 6.53e-15, 
                        5.91e-15, 5.36e-15, 4.86e-15, 
                        4.42e-15, 4.03e-15, 3.68e-15, 
                        3.37e-15, 3.07e-15, 2.78e-15, 
                        2.48e-15, 2.20e-15, 1.92e-15, 
                        1.68e-15, 1.47e-15, 1.29e-15, 
                        1.14e-15, 1.00e-15, 8.83e-16, 
                        7.77e-16, 6.82e-16, 5.97e-16, 
                        5.22e-16, 4.57e-16, 3.99e-16, 
                        3.50e-16, 3.09e-16, 2.74e-16, 
                        2.41e-16, 0])
    },
    'HM01':{
        'logz':np.array([ 0.   ,  0.005,  0.01 ,  0.015,  0.02 ,  0.025,  0.03 ,  0.035,
                          0.04 ,  0.045,  0.05 ,  0.055,  0.06 ,  0.065,  0.07 ,  0.075,
                          0.08 ,  0.085,  0.09 ,  0.095,  0.1  ,  0.105,  0.11 ,  0.115,
                          0.12 ,  0.125,  0.13 ,  0.135,  0.14 ,  0.145,  0.15 ,  0.155,
                          0.16 ,  0.165,  0.17 ,  0.175,  0.18 ,  0.185,  0.19 ,  0.195,
                          0.2  ,  0.205,  0.21 ,  0.215,  0.22 ,  0.225,  0.23 ,  0.235,
                          0.24 ,  0.245,  0.25 ,  0.255,  0.26 ,  0.265,  0.27 ,  0.275,
                          0.28 ,  0.285,  0.29 ,  0.295,  0.3  ,  0.305,  0.31 ,  0.315,
                          0.32 ,  0.325,  0.33 ,  0.335,  0.34 ,  0.345,  0.35 ,  0.355,
                          0.36 ,  0.365,  0.37 ,  0.375,  0.38 ,  0.385,  0.39 ,  0.395,
                          0.4  ,  0.405,  0.41 ,  0.415,  0.42 ,  0.425,  0.43 ,  0.435,
                          0.44 ,  0.445,  0.45 ,  0.455,  0.46 ,  0.465,  0.47 ,  0.475,
                          0.48 ,  0.485,  0.49 ,  0.495,  0.5  ,  0.505,  0.51 ,  0.515,
                          0.52 ,  0.525,  0.53 ,  0.535,  0.54 ,  0.545,  0.55 ,  0.555,
                          0.56 ,  0.565,  0.57 ,  0.575,  0.58 ,  0.585,  0.59 ,  0.595,
                          0.6  ,  0.605,  0.61 ,  0.615,  0.62 ,  0.625,  0.63 ,  0.635,
                          0.64 ,  0.645,  0.65 ,  0.655,  0.66 ,  0.665,  0.67 ,  0.675,
                          0.68 ,  0.685,  0.69 ,  0.695,  0.7  ,  0.705,  0.71 ,  0.715,
                          0.72 ,  0.725,  0.73 ,  0.735,  0.74 ,  0.745,  0.75 ,  0.755,
                          0.76 ,  0.765,  0.77 ,  0.775,  0.78 ,  0.785,  0.79 ,  0.795,
                          0.8  ,  0.805,  0.81 ,  0.815,  0.82 ,  0.825,  0.83 ,  0.835,
                          0.84 ,  0.845,  0.85 ,  0.855,  0.86 ,  0.865,  0.87 ,  0.875,
                          0.88 ,  0.885,  0.89 ,  0.895,  0.9  ,  0.905,  0.91 ,  0.915,
                          0.92 ,  0.925,  0.93 ,  0.935,  0.94 ,  0.945,  0.95 ,  0.955,
                          0.96 ,  0.965,  0.97 ,  0.975,  0.98 ,  0.985,  0.99 ,  0.995,
                          1.   ,  1.005,  1.01 ,  1.015,  1.02 ,  1.025]),
        'gH0':np.array([  8.28784000e-14,   8.65433000e-14,   9.02811000e-14,
                          9.41251000e-14,   9.81104000e-14,   1.02271000e-13,
                          1.06612000e-13,   1.11131000e-13,   1.15821000e-13,
                          1.20678000e-13,   1.25704000e-13,   1.30910000e-13,
                          1.36303000e-13,   1.41896000e-13,   1.47694000e-13,
                          1.53702000e-13,   1.59921000e-13,   1.66356000e-13,
                          1.73012000e-13,   1.79894000e-13,   1.87011000e-13,
                          1.94370000e-13,   2.01977000e-13,   2.09838000e-13,
                          2.17958000e-13,   2.26339000e-13,   2.34989000e-13,
                          2.43912000e-13,   2.53117000e-13,   2.62610000e-13,
                          2.72399000e-13,   2.82487000e-13,   2.92879000e-13,
                          3.03577000e-13,   3.14584000e-13,   3.25908000e-13,
                          3.37558000e-13,   3.49544000e-13,   3.61876000e-13,
                          3.74561000e-13,   3.87603000e-13,   4.01004000e-13,
                          4.14768000e-13,   4.28897000e-13,   4.43392000e-13,
                          4.58252000e-13,   4.73479000e-13,   4.89074000e-13,
                          5.05052000e-13,   5.21425000e-13,   5.38209000e-13,
                          5.55417000e-13,   5.73056000e-13,   5.91130000e-13,
                          6.09645000e-13,   6.28605000e-13,   6.48015000e-13,
                          6.67878000e-13,   6.88199000e-13,   7.08980000e-13,
                          7.30218000e-13,   7.51905000e-13,   7.74031000e-13,
                          7.96587000e-13,   8.19575000e-13,   8.43009000e-13,
                          8.66903000e-13,   8.91274000e-13,   9.16105000e-13,
                          9.41330000e-13,   9.66876000e-13,   9.92660000e-13,
                          1.01861000e-12,   1.04469000e-12,   1.07084000e-12,
                          1.09702000e-12,   1.12318000e-12,   1.14925000e-12,
                          1.17514000e-12,   1.20078000e-12,   1.22608000e-12,
                          1.25093000e-12,   1.27521000e-12,   1.29880000e-12,
                          1.32155000e-12,   1.34338000e-12,   1.36420000e-12,
                          1.38392000e-12,   1.40244000e-12,   1.41966000e-12,
                          1.43543000e-12,   1.44962000e-12,   1.46210000e-12,
                          1.47274000e-12,   1.48150000e-12,   1.48834000e-12,
                          1.49322000e-12,   1.49611000e-12,   1.49701000e-12,
                          1.49591000e-12,   1.49284000e-12,   1.48782000e-12,
                          1.48092000e-12,   1.47222000e-12,   1.46181000e-12,
                          1.44980000e-12,   1.43627000e-12,   1.42133000e-12,
                          1.40506000e-12,   1.38759000e-12,   1.36906000e-12,
                          1.34963000e-12,   1.32947000e-12,   1.30878000e-12,
                          1.28766000e-12,   1.26620000e-12,   1.24446000e-12,
                          1.22252000e-12,   1.20050000e-12,   1.17855000e-12,
                          1.15685000e-12,   1.13557000e-12,   1.11484000e-12,
                          1.09467000e-12,   1.07503000e-12,   1.05589000e-12,
                          1.03721000e-12,   1.01885000e-12,   1.00067000e-12,
                          9.82487000e-13,   9.64160000e-13,   9.45706000e-13,
                          9.27205000e-13,   9.08741000e-13,   8.90401000e-13,
                          8.72211000e-13,   8.54165000e-13,   8.36258000e-13,
                          8.18484000e-13,   8.00848000e-13,   7.83370000e-13,
                          7.66072000e-13,   7.48974000e-13,   7.32092000e-13,
                          7.15433000e-13,   6.98999000e-13,   6.82798000e-13,
                          6.66833000e-13,   6.51107000e-13,   6.35625000e-13,
                          6.20388000e-13,   6.05401000e-13,   5.90670000e-13,
                          5.76200000e-13,   5.61998000e-13,   5.48069000e-13,
                          5.34419000e-13,   5.21050000e-13,   5.07966000e-13,
                          4.95168000e-13,   4.82655000e-13,   4.70422000e-13,
                          4.58462000e-13,   4.46770000e-13,   4.35342000e-13,
                          4.24182000e-13,   4.13290000e-13,   4.02669000e-13,
                          3.92316000e-13,   3.82229000e-13,   3.72404000e-13,
                          3.62836000e-13,   3.53519000e-13,   3.44446000e-13,
                          3.35612000e-13,   3.27007000e-13,   3.18626000e-13,
                          3.10474000e-13,   3.02556000e-13,   2.94881000e-13,
                          2.87449000e-13,   2.80242000e-13,   2.73233000e-13,
                          2.66451000e-13,   2.59753000e-13,   2.53224000e-13,
                          2.46920000e-13,   2.40902000e-13,   2.35224000e-13,
                          2.29796000e-13,   2.24404000e-13,   2.18817000e-13,
                          2.12799000e-13,   2.06554000e-13,   2.00857000e-13,
                          1.96568000e-13,   1.94595000e-13,   1.94443000e-13,
                          1.92787000e-13,   1.85759000e-13,   1.69223000e-13,
                          1.40359000e-13,   1.01064000e-13,   5.43188000e-14,
                          3.32714000e-15,   0.00000000e+00])
    }
}


