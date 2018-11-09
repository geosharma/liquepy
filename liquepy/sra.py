import numpy as np
import pysra
import sfsimodels as sm


PA_TO_KPA = 0.001


def compute_pysra_tf(pysra_profile, pysra_freqs=None):

    if pysra_freqs is None:
        pysra_freqs = np.logspace(-0.7, 1.5, num=200)
    m = pysra.motion.Motion(freqs=pysra_freqs)
    outputs = pysra.output.OutputCollection(
        pysra.output.AccelTransferFunctionOutput(pysra_freqs, pysra.output.OutputLocation('outcrop', index=-1),
                                                 pysra.output.OutputLocation('outcrop', index=0)),
    )
    calc = pysra.propagation.LinearElasticCalculator()
    calc(m, pysra_profile, pysra_profile.location('outcrop', index=-1))
    outputs(calc)
    out_liq_tf = outputs[0].values
    return pysra_freqs, out_liq_tf


def vardanega_2013_to_modified_hyperbolic_parameters(i_p):
    a = 0.943  # Eq 22b
    j = 3.7  # Eq 23
    gamma_ref = j * (i_p / 1000)
    return gamma_ref, a


def sm_profile_to_pysra(sp, d_inc=None, target_height=1.0):
    """
    Converts a soil profile from sfsimodels into a soil profile for pysra

    Note: pysra uses kPa whereas sfsimodels uses Pa

    :param sp:
    :param d_inc:
    :param target_height:
    :return:
    """
    if d_inc is None:
        d_inc = np.ones(sp.n_layers) * target_height

    strains = np.logspace(-6, -1.5, num=30)

    layers = []
    cum_thickness = 0
    for i in range(sp.n_layers):

        sl = sp.layer(i + 1)
        thickness = sp.layer_height(i + 1)

        n_slices = int(thickness / d_inc[i])
        if i == sp.n_layers - 1:
            n_slices += 1  # add one more since it is applied at top of layer
        slice_thickness = float(thickness) / n_slices
        for j in range(n_slices):
            cum_thickness += slice_thickness
            rho = sl.unit_dry_weight / 9.8
            if hasattr(sl, "g_mod_at_v_eff_stress"):
                v_eff = sp.vertical_effective_stress(cum_thickness)
                g_mod = sl.g_mod_at_v_eff_stress(v_eff)
            else:
                g_mod = sl.g_mod
            if hasattr(sl, "g_mod_red"):
                g_mod *= sl.g_mod_red
            vs = np.sqrt(g_mod / rho)
            if cum_thickness > sp.gwl:
                unit_wt = sl.unit_sat_weight
            else:
                unit_wt = sl.unit_dry_weight
            if hasattr(sl, "darendeli"):
                assert isinstance(sp, sm.SoilProfile)
                s_v_eff = sp.vertical_effective_stress(cum_thickness)
                k0 = 1 - np.sin(np.radians(sl.phi))
                darendeli_sigma_m_eff = (s_v_eff * (1 + 2 * k0) / 3) * PA_TO_KPA  # Needs to be in kPa
                ip = sl.plasticity_index
                if ip is None:
                    ip = 0.0
                ip *= 100  # Input is in percentage
                pysra_sl = pysra.site.DarendeliSoilType(unit_wt, plas_index=ip, ocr=1,
                                                        stress_mean=darendeli_sigma_m_eff, strains=strains)
            elif hasattr(sl, "darendeli_sigma_m_eff"):
                ip = sl.plasticity_index
                if ip is None:
                    ip = 0.0
                ip *= 100  # Input is in percentage
                pysra_sl = pysra.site.DarendeliSoilType(unit_wt, plas_index=ip, ocr=1,
                                                        stress_mean=sl.darendeli_sigma_m_eff, strains=strains)
            elif hasattr(sl, "plasticity_index") and getattr(sl, "plasticity_index") is not None:
                i_p = sl.plasticity_index
                gamma_ref, curvature = vardanega_2013_to_modified_hyperbolic_parameters(i_p)
                name = "vardanega (2013) I_p = %.2f" % i_p
                pysra_sl = pysra.site.ModifiedHyperbolicSoilType(name, unit_wt, strain_ref=gamma_ref,
                                                                 curvature=curvature,
                                                                 damping_min=0.02,
                                                                 strains=strains)
            else:
                pysra_sl = pysra.site.SoilType(sl.name, unit_wt, None, sl.xi)
            lay = pysra.site.Layer(pysra_sl, slice_thickness, vs)
            layers.append(lay)

    profile = pysra.site.Profile(layers, wt_depth=sp.gwl)
    return profile


def compute_pysra_strain_compatible_profile(soil_profile, in_sig):
    m = pysra.motion.TimeSeriesMotion(filename=in_sig.label, description=None, time_step=in_sig.dt,
                                      accels=in_sig.values / 9.8)

    profile = sm_profile_to_pysra(soil_profile, d_inc=1.0 * np.ones(soil_profile.n_layers))

    layers = []
    calc = pysra.propagation.EquivalentLinearCalculator()
    calc(m, profile, profile.location('outcrop', depth=soil_profile.height))
    for depth in profile.depth:
        shear_vel0 = profile.location('outcrop', depth=depth).layer.initial_shear_vel
        shear_vel = profile.location('outcrop', depth=depth).layer.shear_vel
        unit_wt = profile.location('outcrop', depth=depth).layer.unit_wt
        damping = profile.location('outcrop', depth=depth).layer.damping
        slice_thickness = profile.location('outcrop', depth=depth).layer.thickness
        pysra_sl = pysra.site.SoilType("soil", unit_wt, None, damping)
        lay = pysra.site.Layer(pysra_sl, slice_thickness, shear_vel)
        layers.append(lay)

    strain_comp_profile = pysra.site.Profile(layers, wt_depth=soil_profile.gwl)

    return strain_comp_profile


def update_pysra_profile(pysra_profile, depths, xis=None, shear_vels=None):
    layers = []
    for depth in pysra_profile.depth:
        try:
            indy = depths.index(depth)
            if xis is not None:
                damping = xis[indy]
            else:
                damping = pysra_profile.location('outcrop', depth=depth).layer.damping
            if shear_vels is not None:
                shear_vel0 = shear_vels[indy]
            else:
                shear_vel0 = pysra_profile.location('outcrop', depth=depth).layer.initial_shear_vel
        except ValueError:
            shear_vel0 = pysra_profile.location('outcrop', depth=depth).layer.initial_shear_vel
            damping = pysra_profile.location('outcrop', depth=depth).layer.damping

        unit_wt = pysra_profile.location('outcrop', depth=depth).layer.unit_wt
        slice_thickness = pysra_profile.location('outcrop', depth=depth).layer.thickness

        pysra_sl = pysra.site.SoilType("soil", unit_wt, None, damping)
        lay = pysra.site.Layer(pysra_sl, slice_thickness, shear_vel0)
        layers.append(lay)

    new_profile = pysra.site.Profile(layers, wt_depth=pysra_profile.wt_depth)

    return new_profile
